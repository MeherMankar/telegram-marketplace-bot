import asyncio
import logging
import json
import zipfile
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import os

logger = logging.getLogger(__name__)

class ComplianceService:
    def __init__(self, db_connection):
        self.db = db_connection
        self.gdpr_retention_days = 2555  # 7 years
        self.audit_retention_days = 2555  # 7 years
    
    async def handle_data_export_request(self, user_id: int, request_type: str = "full") -> Dict[str, Any]:
        """Handle GDPR data export request"""
        try:
            export_data = {}
            
            # User profile data
            user = await self.db.users.find_one({'user_id': user_id})
            if user:
                # Remove sensitive fields
                user_data = {k: v for k, v in user.items() if k not in ['_id', 'password_hash']}
                export_data['profile'] = user_data
            
            # Account data
            accounts = await self.db.accounts.find({'user_id': user_id}).to_list(None)
            export_data['accounts'] = [
                {k: v for k, v in acc.items() if k not in ['_id', 'session_data']}
                for acc in accounts
            ]
            
            # Transaction history
            transactions = await self.db.transactions.find({
                '$or': [
                    {'buyer_id': user_id},
                    {'seller_id': user_id}
                ]
            }).to_list(None)
            export_data['transactions'] = [
                {k: v for k, v in trans.items() if k != '_id'}
                for trans in transactions
            ]
            
            # Support tickets
            tickets = await self.db.support_tickets.find({'user_id': user_id}).to_list(None)
            export_data['support_tickets'] = [
                {k: v for k, v in ticket.items() if k != '_id'}
                for ticket in tickets
            ]
            
            # Security logs
            security_logs = await self.db.security_logs.find({'user_id': user_id}).to_list(None)
            export_data['security_logs'] = [
                {k: v for k, v in log.items() if k != '_id'}
                for log in security_logs
            ]
            
            # Create export file
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            export_filename = f"user_data_export_{user_id}_{timestamp}.json"
            export_path = f"exports/{export_filename}"
            
            os.makedirs('exports', exist_ok=True)
            
            with open(export_path, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            # Log the export request
            await self.db.compliance_logs.insert_one({
                'user_id': user_id,
                'action': 'data_export',
                'request_type': request_type,
                'export_file': export_path,
                'timestamp': datetime.utcnow(),
                'status': 'completed'
            })
            
            return {
                'success': True,
                'export_file': export_path,
                'data_categories': list(export_data.keys()),
                'total_records': sum(len(v) if isinstance(v, list) else 1 for v in export_data.values())
            }
            
        except Exception as e:
            logger.error(f"Error handling data export request: {e}")
            return {'success': False, 'error': str(e)}
    
    async def handle_data_deletion_request(self, user_id: int, deletion_type: str = "full") -> Dict[str, Any]:
        """Handle GDPR data deletion request"""
        try:
            deleted_records = {}
            
            if deletion_type == "full":
                # Delete user profile
                user_result = await self.db.users.delete_one({'user_id': user_id})
                deleted_records['user_profile'] = user_result.deleted_count
                
                # Delete accounts (but keep anonymized records for business purposes)
                accounts_result = await self.db.accounts.update_many(
                    {'user_id': user_id},
                    {
                        '$set': {
                            'user_id': 0,  # Anonymize
                            'phone': 'DELETED',
                            'username': 'DELETED',
                            'session_data': 'DELETED',
                            'deleted_at': datetime.utcnow()
                        }
                    }
                )
                deleted_records['accounts_anonymized'] = accounts_result.modified_count
                
                # Anonymize transactions (keep for financial records)
                trans_result = await self.db.transactions.update_many(
                    {'$or': [{'buyer_id': user_id}, {'seller_id': user_id}]},
                    {
                        '$set': {
                            'buyer_id': 0 if deletion_type == "full" else user_id,
                            'seller_id': 0 if deletion_type == "full" else user_id,
                            'anonymized_at': datetime.utcnow()
                        }
                    }
                )
                deleted_records['transactions_anonymized'] = trans_result.modified_count
                
                # Delete support tickets
                tickets_result = await self.db.support_tickets.delete_many({'user_id': user_id})
                deleted_records['support_tickets'] = tickets_result.deleted_count
                
                # Delete security logs older than retention period
                retention_cutoff = datetime.utcnow() - timedelta(days=90)  # Keep recent for security
                security_result = await self.db.security_logs.delete_many({
                    'user_id': user_id,
                    'timestamp': {'$lt': retention_cutoff}
                })
                deleted_records['security_logs'] = security_result.deleted_count
                
                # Delete user security settings
                security_settings_result = await self.db.user_security.delete_one({'user_id': user_id})
                deleted_records['security_settings'] = security_settings_result.deleted_count
                
            elif deletion_type == "partial":
                # Only delete non-essential data
                await self.db.users.update_one(
                    {'user_id': user_id},
                    {
                        '$unset': {
                            'email': '',
                            'first_name': '',
                            'last_name': '',
                            'bio': ''
                        },
                        '$set': {'data_minimized': True}
                    }
                )
                deleted_records['profile_data_minimized'] = 1
            
            # Log the deletion request
            await self.db.compliance_logs.insert_one({
                'user_id': user_id,
                'action': 'data_deletion',
                'deletion_type': deletion_type,
                'deleted_records': deleted_records,
                'timestamp': datetime.utcnow(),
                'status': 'completed'
            })
            
            return {
                'success': True,
                'deletion_type': deletion_type,
                'deleted_records': deleted_records,
                'total_deleted': sum(deleted_records.values())
            }
            
        except Exception as e:
            logger.error(f"Error handling data deletion request: {e}")
            return {'success': False, 'error': str(e)}
    
    async def generate_audit_trail(self, start_date: datetime, end_date: datetime, 
                                 user_id: Optional[int] = None) -> Dict[str, Any]:
        """Generate comprehensive audit trail"""
        try:
            audit_data = {}
            
            # Base query
            date_query = {
                'timestamp': {'$gte': start_date, '$lte': end_date}
            }
            
            if user_id:
                date_query['user_id'] = user_id
            
            # Admin actions
            admin_actions = await self.db.admin_actions.find(date_query).to_list(None)
            audit_data['admin_actions'] = [
                {
                    'action_id': str(action['_id']),
                    'admin_id': action['admin_id'],
                    'action_type': action['action_type'],
                    'target_id': action.get('target_id'),
                    'details': action.get('details', {}),
                    'timestamp': action['timestamp'].isoformat()
                }
                for action in admin_actions
            ]
            
            # User registrations
            user_query = {'created_at': {'$gte': start_date, '$lte': end_date}}
            if user_id:
                user_query['user_id'] = user_id
            
            user_registrations = await self.db.users.find(user_query).to_list(None)
            audit_data['user_registrations'] = [
                {
                    'user_id': user['user_id'],
                    'username': user.get('username', 'N/A'),
                    'registration_date': user['created_at'].isoformat(),
                    'user_type': user.get('user_type', 'regular')
                }
                for user in user_registrations
            ]
            
            # Account uploads
            upload_query = {'upload_date': {'$gte': start_date, '$lte': end_date}}
            if user_id:
                upload_query['user_id'] = user_id
            
            account_uploads = await self.db.accounts.find(upload_query).to_list(None)
            audit_data['account_uploads'] = [
                {
                    'account_id': str(acc['_id']),
                    'user_id': acc['user_id'],
                    'phone': acc.get('phone', 'N/A'),
                    'country': acc.get('country', 'N/A'),
                    'upload_date': acc['upload_date'].isoformat(),
                    'verification_status': acc.get('verification_status', 'pending')
                }
                for acc in account_uploads
            ]
            
            # Transactions
            trans_query = {'created_at': {'$gte': start_date, '$lte': end_date}}
            if user_id:
                trans_query['$or'] = [{'buyer_id': user_id}, {'seller_id': user_id}]
            
            transactions = await self.db.transactions.find(trans_query).to_list(None)
            audit_data['transactions'] = [
                {
                    'transaction_id': str(trans['_id']),
                    'buyer_id': trans['buyer_id'],
                    'seller_id': trans.get('seller_id'),
                    'amount': trans['amount'],
                    'status': trans['status'],
                    'payment_method': trans.get('payment_method'),
                    'created_at': trans['created_at'].isoformat()
                }
                for trans in transactions
            ]
            
            # Security events
            security_events = await self.db.security_logs.find(date_query).to_list(None)
            audit_data['security_events'] = [
                {
                    'event_id': str(event['_id']),
                    'user_id': event['user_id'],
                    'activity_type': event['activity_type'],
                    'suspicious_score': event.get('suspicious_score', 0),
                    'timestamp': event['timestamp'].isoformat(),
                    'status': event.get('status', 'logged')
                }
                for event in security_events
            ]
            
            # Compliance actions
            compliance_actions = await self.db.compliance_logs.find(date_query).to_list(None)
            audit_data['compliance_actions'] = [
                {
                    'action_id': str(action['_id']),
                    'user_id': action['user_id'],
                    'action': action['action'],
                    'timestamp': action['timestamp'].isoformat(),
                    'status': action['status']
                }
                for action in compliance_actions
            ]
            
            # Generate audit file
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            audit_filename = f"audit_trail_{timestamp}.json"
            audit_path = f"audits/{audit_filename}"
            
            os.makedirs('audits', exist_ok=True)
            
            with open(audit_path, 'w') as f:
                json.dump({
                    'audit_period': {
                        'start_date': start_date.isoformat(),
                        'end_date': end_date.isoformat()
                    },
                    'generated_at': datetime.utcnow().isoformat(),
                    'user_filter': user_id,
                    'data': audit_data
                }, f, indent=2, default=str)
            
            # Create compressed version
            zip_path = f"{audit_path}.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(audit_path, audit_filename)
            
            return {
                'success': True,
                'audit_file': zip_path,
                'period': f"{start_date.date()} to {end_date.date()}",
                'total_events': sum(len(v) if isinstance(v, list) else 0 for v in audit_data.values()),
                'categories': list(audit_data.keys())
            }
            
        except Exception as e:
            logger.error(f"Error generating audit trail: {e}")
            return {'success': False, 'error': str(e)}
    
    async def check_data_retention_compliance(self) -> Dict[str, Any]:
        """Check and enforce data retention policies"""
        try:
            current_time = datetime.utcnow()
            retention_cutoff = current_time - timedelta(days=self.gdpr_retention_days)
            
            compliance_report = {
                'check_date': current_time.isoformat(),
                'retention_policy_days': self.gdpr_retention_days,
                'actions_taken': []
            }
            
            # Check old user data
            old_users = await self.db.users.find({
                'created_at': {'$lt': retention_cutoff},
                'last_activity': {'$lt': retention_cutoff}
            }).to_list(None)
            
            if old_users:
                # Archive old user data
                for user in old_users:
                    await self._archive_user_data(user['user_id'])
                
                compliance_report['actions_taken'].append(
                    f"Archived {len(old_users)} inactive user accounts"
                )
            
            # Check old security logs
            old_logs_count = await self.db.security_logs.count_documents({
                'timestamp': {'$lt': retention_cutoff}
            })
            
            if old_logs_count > 0:
                await self.db.security_logs.delete_many({
                    'timestamp': {'$lt': retention_cutoff}
                })
                
                compliance_report['actions_taken'].append(
                    f"Deleted {old_logs_count} old security log entries"
                )
            
            # Check old audit logs
            old_audit_count = await self.db.compliance_logs.count_documents({
                'timestamp': {'$lt': retention_cutoff}
            })
            
            if old_audit_count > 0:
                await self.db.compliance_logs.delete_many({
                    'timestamp': {'$lt': retention_cutoff}
                })
                
                compliance_report['actions_taken'].append(
                    f"Deleted {old_audit_count} old compliance log entries"
                )
            
            return compliance_report
            
        except Exception as e:
            logger.error(f"Error checking data retention compliance: {e}")
            return {'success': False, 'error': str(e)}
    
    async def generate_legal_document(self, document_type: str, version: str = "1.0") -> Dict[str, Any]:
        """Generate legal documents (Terms of Service, Privacy Policy, etc.)"""
        try:
            documents = {
                'terms_of_service': self._generate_terms_of_service(),
                'privacy_policy': self._generate_privacy_policy(),
                'data_processing_agreement': self._generate_dpa(),
                'cookie_policy': self._generate_cookie_policy()
            }
            
            if document_type not in documents:
                return {'success': False, 'error': 'Invalid document type'}
            
            document_content = documents[document_type]
            
            # Save document
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"{document_type}_v{version}_{timestamp}.txt"
            filepath = f"legal_documents/{filename}"
            
            os.makedirs('legal_documents', exist_ok=True)
            
            with open(filepath, 'w') as f:
                f.write(document_content)
            
            # Log document generation
            await self.db.legal_documents.insert_one({
                'document_type': document_type,
                'version': version,
                'filepath': filepath,
                'generated_at': datetime.utcnow(),
                'status': 'active'
            })
            
            return {
                'success': True,
                'document_type': document_type,
                'version': version,
                'filepath': filepath,
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating legal document: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _archive_user_data(self, user_id: int):
        """Archive user data for compliance"""
        try:
            # Move user data to archive collection
            user_data = await self.db.users.find_one({'user_id': user_id})
            if user_data:
                user_data['archived_at'] = datetime.utcnow()
                await self.db.archived_users.insert_one(user_data)
                await self.db.users.delete_one({'user_id': user_id})
            
            # Archive related data
            await self.db.archived_accounts.insert_many(
                await self.db.accounts.find({'user_id': user_id}).to_list(None)
            )
            await self.db.accounts.delete_many({'user_id': user_id})
            
        except Exception as e:
            logger.error(f"Error archiving user data for {user_id}: {e}")
    
    def _generate_terms_of_service(self) -> str:
        """Generate Terms of Service document"""
        return """
TERMS OF SERVICE - TELEGRAM ACCOUNT MARKETPLACE

Last Updated: {date}

1. ACCEPTANCE OF TERMS
By using this service, you agree to these terms.

2. SERVICE DESCRIPTION
This platform facilitates the buying and selling of Telegram accounts.

3. USER RESPONSIBILITIES
- Provide accurate information
- Comply with all applicable laws
- Respect other users' rights

4. PROHIBITED ACTIVITIES
- Fraudulent transactions
- Spam or abuse
- Violation of Telegram's terms

5. PAYMENT TERMS
- All sales are final
- Payments processed securely
- Disputes handled through support

6. PRIVACY
Your privacy is important. See our Privacy Policy.

7. LIMITATION OF LIABILITY
Service provided "as is" without warranties.

8. TERMINATION
We may terminate accounts for violations.

9. GOVERNING LAW
These terms are governed by applicable law.

10. CONTACT
For questions, contact our support team.
        """.format(date=datetime.utcnow().strftime('%Y-%m-%d'))
    
    def _generate_privacy_policy(self) -> str:
        """Generate Privacy Policy document"""
        return """
PRIVACY POLICY - TELEGRAM ACCOUNT MARKETPLACE

Last Updated: {date}

1. INFORMATION WE COLLECT
- Account information
- Transaction data
- Usage analytics
- Communication records

2. HOW WE USE INFORMATION
- Provide services
- Process transactions
- Improve platform
- Communicate with users

3. INFORMATION SHARING
We do not sell personal information.
Limited sharing for service provision.

4. DATA SECURITY
We implement security measures to protect data.

5. YOUR RIGHTS
- Access your data
- Request corrections
- Delete your account
- Data portability

6. COOKIES
We use cookies for functionality and analytics.

7. THIRD-PARTY SERVICES
Integration with payment processors and analytics.

8. INTERNATIONAL TRANSFERS
Data may be processed internationally.

9. RETENTION
Data retained as needed for services and compliance.

10. CONTACT
For privacy questions, contact our DPO.
        """.format(date=datetime.utcnow().strftime('%Y-%m-%d'))
    
    def _generate_dpa(self) -> str:
        """Generate Data Processing Agreement"""
        return """
DATA PROCESSING AGREEMENT

This agreement governs data processing activities.

1. DEFINITIONS
Standard GDPR definitions apply.

2. PROCESSING ACTIVITIES
- User account management
- Transaction processing
- Security monitoring
- Analytics

3. DATA CATEGORIES
- Personal identifiers
- Financial information
- Communication data
- Technical data

4. SECURITY MEASURES
- Encryption at rest and in transit
- Access controls
- Regular security audits
- Incident response procedures

5. DATA SUBJECT RIGHTS
Support for all GDPR rights.

6. BREACH NOTIFICATION
72-hour notification requirement.

7. AUDITS
Regular compliance audits.
        """
    
    def _generate_cookie_policy(self) -> str:
        """Generate Cookie Policy"""
        return """
COOKIE POLICY

We use cookies to enhance your experience.

1. WHAT ARE COOKIES
Small text files stored on your device.

2. TYPES OF COOKIES
- Essential cookies
- Analytics cookies
- Functional cookies

3. MANAGING COOKIES
You can control cookies through browser settings.

4. THIRD-PARTY COOKIES
Some cookies are set by third-party services.
        """