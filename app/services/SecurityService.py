import asyncio
import logging
import hashlib
import secrets
import pyotp
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import ipaddress
from collections import defaultdict

logger = logging.getLogger(__name__)

class SecurityService:
    def __init__(self, db_connection):
        self.db = db_connection
        self.failed_attempts = defaultdict(list)  # IP -> [timestamps]
        self.suspicious_activities = defaultdict(int)  # user_id -> count
    
    async def enable_2fa(self, user_id: int) -> Dict[str, Any]:
        """Enable two-factor authentication for a user"""
        try:
            # Generate secret key
            secret = pyotp.random_base32()
            
            # Create TOTP object
            totp = pyotp.TOTP(secret)
            
            # Generate QR code URL
            user = await self.db.users.find_one({'user_id': user_id})
            username = user.get('username', f'user_{user_id}') if user else f'user_{user_id}'
            
            qr_url = totp.provisioning_uri(
                name=username,
                issuer_name="Telegram Marketplace"
            )
            
            # Store secret (temporarily, until verified)
            await self.db.user_security.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        'temp_2fa_secret': secret,
                        '2fa_enabled': False,
                        'updated_at': datetime.utcnow()
                    }
                },
                upsert=True
            )
            
            return {
                'success': True,
                'secret': secret,
                'qr_url': qr_url,
                'backup_codes': self._generate_backup_codes()
            }
            
        except Exception as e:
            logger.error(f"Error enabling 2FA: {e}")
            return {'success': False, 'error': str(e)}
    
    async def verify_2fa_setup(self, user_id: int, token: str) -> Dict[str, Any]:
        """Verify 2FA setup with user-provided token"""
        try:
            security_data = await self.db.user_security.find_one({'user_id': user_id})
            if not security_data or not security_data.get('temp_2fa_secret'):
                return {'success': False, 'error': '2FA setup not initiated'}
            
            # Verify token
            totp = pyotp.TOTP(security_data['temp_2fa_secret'])
            if not totp.verify(token):
                return {'success': False, 'error': 'Invalid token'}
            
            # Enable 2FA permanently
            backup_codes = self._generate_backup_codes()
            
            await self.db.user_security.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        '2fa_secret': security_data['temp_2fa_secret'],
                        '2fa_enabled': True,
                        'backup_codes': backup_codes,
                        'updated_at': datetime.utcnow()
                    },
                    '$unset': {'temp_2fa_secret': ''}
                }
            )
            
            return {
                'success': True,
                '2fa_enabled': True,
                'backup_codes': backup_codes
            }
            
        except Exception as e:
            logger.error(f"Error verifying 2FA setup: {e}")
            return {'success': False, 'error': str(e)}
    
    async def verify_2fa_token(self, user_id: int, token: str) -> Dict[str, Any]:
        """Verify 2FA token for login"""
        try:
            security_data = await self.db.user_security.find_one({'user_id': user_id})
            if not security_data or not security_data.get('2fa_enabled'):
                return {'success': False, 'error': '2FA not enabled'}
            
            # Check if it's a backup code
            if token in security_data.get('backup_codes', []):
                # Remove used backup code
                await self.db.user_security.update_one(
                    {'user_id': user_id},
                    {'$pull': {'backup_codes': token}}
                )
                return {'success': True, 'method': 'backup_code'}
            
            # Verify TOTP token
            totp = pyotp.TOTP(security_data['2fa_secret'])
            if totp.verify(token):
                return {'success': True, 'method': 'totp'}
            
            return {'success': False, 'error': 'Invalid token'}
            
        except Exception as e:
            logger.error(f"Error verifying 2FA token: {e}")
            return {'success': False, 'error': str(e)}
    
    async def add_ip_whitelist(self, admin_id: int, ip_address: str, description: str = "") -> Dict[str, Any]:
        """Add IP address to admin whitelist"""
        try:
            # Validate IP address
            try:
                ipaddress.ip_address(ip_address)
            except ValueError:
                return {'success': False, 'error': 'Invalid IP address format'}
            
            # Check if IP already whitelisted
            existing = await self.db.ip_whitelist.find_one({'ip_address': ip_address})
            if existing:
                return {'success': False, 'error': 'IP address already whitelisted'}
            
            whitelist_entry = {
                'ip_address': ip_address,
                'description': description,
                'added_by': admin_id,
                'added_at': datetime.utcnow(),
                'is_active': True
            }
            
            await self.db.ip_whitelist.insert_one(whitelist_entry)
            
            return {'success': True, 'ip_address': ip_address}
            
        except Exception as e:
            logger.error(f"Error adding IP to whitelist: {e}")
            return {'success': False, 'error': str(e)}
    
    async def check_ip_whitelist(self, admin_id: int, ip_address: str) -> bool:
        """Check if admin IP is whitelisted"""
        try:
            # Check if IP whitelisting is enabled for this admin
            admin_security = await self.db.user_security.find_one({'user_id': admin_id})
            if not admin_security or not admin_security.get('ip_whitelist_enabled'):
                return True  # IP whitelisting not enabled
            
            # Check whitelist
            whitelist_entry = await self.db.ip_whitelist.find_one({
                'ip_address': ip_address,
                'is_active': True
            })
            
            return whitelist_entry is not None
            
        except Exception as e:
            logger.error(f"Error checking IP whitelist: {e}")
            return False
    
    async def detect_suspicious_activity(self, user_id: int, activity_type: str, 
                                       metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Detect and log suspicious activities"""
        try:
            # Define suspicious activity thresholds
            thresholds = {
                'rapid_uploads': 10,  # More than 10 uploads in 1 hour
                'failed_logins': 5,   # More than 5 failed logins in 1 hour
                'bulk_purchases': 5,  # More than 5 purchases in 1 hour
                'unusual_hours': True # Activity during unusual hours (2-6 AM)
            }
            
            current_time = datetime.utcnow()
            hour_ago = current_time - timedelta(hours=1)
            
            suspicious_score = 0
            reasons = []
            
            # Check rapid uploads
            if activity_type == 'upload':
                recent_uploads = await self.db.accounts.count_documents({
                    'user_id': user_id,
                    'upload_date': {'$gte': hour_ago}
                })
                
                if recent_uploads >= thresholds['rapid_uploads']:
                    suspicious_score += 30
                    reasons.append(f"Rapid uploads: {recent_uploads} in 1 hour")
            
            # Check failed logins
            elif activity_type == 'failed_login':
                self.failed_attempts[user_id].append(current_time)
                # Clean old attempts
                self.failed_attempts[user_id] = [
                    t for t in self.failed_attempts[user_id] 
                    if t > hour_ago
                ]
                
                if len(self.failed_attempts[user_id]) >= thresholds['failed_logins']:
                    suspicious_score += 40
                    reasons.append(f"Multiple failed logins: {len(self.failed_attempts[user_id])}")
            
            # Check bulk purchases
            elif activity_type == 'purchase':
                recent_purchases = await self.db.transactions.count_documents({
                    'buyer_id': user_id,
                    'created_at': {'$gte': hour_ago}
                })
                
                if recent_purchases >= thresholds['bulk_purchases']:
                    suspicious_score += 25
                    reasons.append(f"Bulk purchases: {recent_purchases} in 1 hour")
            
            # Check unusual hours (2-6 AM UTC)
            if 2 <= current_time.hour <= 6:
                suspicious_score += 10
                reasons.append("Activity during unusual hours")
            
            # Log suspicious activity
            if suspicious_score > 20:
                await self.db.security_logs.insert_one({
                    'user_id': user_id,
                    'activity_type': activity_type,
                    'suspicious_score': suspicious_score,
                    'reasons': reasons,
                    'metadata': metadata or {},
                    'timestamp': current_time,
                    'status': 'flagged' if suspicious_score > 50 else 'monitored'
                })
                
                # Auto-suspend if score is very high
                if suspicious_score > 70:
                    await self._auto_suspend_user(user_id, reasons)
            
            return {
                'is_suspicious': suspicious_score > 20,
                'suspicious_score': suspicious_score,
                'reasons': reasons,
                'action_taken': 'suspended' if suspicious_score > 70 else 'logged'
            }
            
        except Exception as e:
            logger.error(f"Error detecting suspicious activity: {e}")
            return {'is_suspicious': False, 'error': str(e)}
    
    async def get_security_logs(self, user_id: Optional[int] = None, 
                              hours: int = 24) -> List[Dict[str, Any]]:
        """Get security logs"""
        try:
            query = {
                'timestamp': {'$gte': datetime.utcnow() - timedelta(hours=hours)}
            }
            
            if user_id:
                query['user_id'] = user_id
            
            logs = await self.db.security_logs.find(query).sort('timestamp', -1).to_list(100)
            
            return [
                {
                    'user_id': log['user_id'],
                    'activity_type': log['activity_type'],
                    'suspicious_score': log['suspicious_score'],
                    'reasons': log['reasons'],
                    'timestamp': log['timestamp'].isoformat(),
                    'status': log['status']
                }
                for log in logs
            ]
            
        except Exception as e:
            logger.error(f"Error getting security logs: {e}")
            return []
    
    async def create_verification_level(self, user_id: int, level: str, 
                                      requirements: List[str]) -> Dict[str, Any]:
        """Create user verification level"""
        try:
            verification_levels = {
                'basic': ['phone_verified'],
                'standard': ['phone_verified', 'email_verified', 'profile_complete'],
                'premium': ['phone_verified', 'email_verified', 'profile_complete', 'document_verified'],
                'vip': ['phone_verified', 'email_verified', 'profile_complete', 'document_verified', '2fa_enabled']
            }
            
            if level not in verification_levels:
                return {'success': False, 'error': 'Invalid verification level'}
            
            # Check current user verification status
            user_verification = await self.db.user_verification.find_one({'user_id': user_id})
            if not user_verification:
                user_verification = {
                    'user_id': user_id,
                    'phone_verified': False,
                    'email_verified': False,
                    'profile_complete': False,
                    'document_verified': False,
                    '2fa_enabled': False,
                    'created_at': datetime.utcnow()
                }
                await self.db.user_verification.insert_one(user_verification)
            
            # Check if user meets requirements
            required_checks = verification_levels[level]
            met_requirements = []
            missing_requirements = []
            
            for requirement in required_checks:
                if user_verification.get(requirement, False):
                    met_requirements.append(requirement)
                else:
                    missing_requirements.append(requirement)
            
            # Update verification level if all requirements met
            if not missing_requirements:
                await self.db.user_verification.update_one(
                    {'user_id': user_id},
                    {
                        '$set': {
                            'verification_level': level,
                            'verified_at': datetime.utcnow()
                        }
                    }
                )
            
            return {
                'success': True,
                'verification_level': level if not missing_requirements else user_verification.get('verification_level', 'none'),
                'requirements_met': met_requirements,
                'missing_requirements': missing_requirements,
                'fully_verified': len(missing_requirements) == 0
            }
            
        except Exception as e:
            logger.error(f"Error creating verification level: {e}")
            return {'success': False, 'error': str(e)}
    
    def _generate_backup_codes(self, count: int = 10) -> List[str]:
        """Generate backup codes for 2FA"""
        codes = []
        for _ in range(count):
            code = secrets.token_hex(4).upper()
            codes.append(f"{code[:4]}-{code[4:]}")
        return codes
    
    async def _auto_suspend_user(self, user_id: int, reasons: List[str]):
        """Auto-suspend user for suspicious activity"""
        try:
            await self.db.users.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        'is_suspended': True,
                        'suspension_reason': 'Suspicious activity detected',
                        'suspension_details': reasons,
                        'suspended_at': datetime.utcnow()
                    }
                }
            )
            
            logger.warning(f"User {user_id} auto-suspended for suspicious activity: {reasons}")
            
        except Exception as e:
            logger.error(f"Error auto-suspending user {user_id}: {e}")
    
    async def generate_security_report(self) -> Dict[str, Any]:
        """Generate comprehensive security report"""
        try:
            # Get recent security events
            last_24h = datetime.utcnow() - timedelta(hours=24)
            last_7d = datetime.utcnow() - timedelta(days=7)
            
            # Suspicious activities in last 24h
            recent_suspicious = await self.db.security_logs.count_documents({
                'timestamp': {'$gte': last_24h},
                'suspicious_score': {'$gte': 20}
            })
            
            # Failed login attempts
            failed_logins = await self.db.security_logs.count_documents({
                'timestamp': {'$gte': last_24h},
                'activity_type': 'failed_login'
            })
            
            # Users with 2FA enabled
            users_with_2fa = await self.db.user_security.count_documents({
                '2fa_enabled': True
            })
            
            # IP whitelist entries
            whitelisted_ips = await self.db.ip_whitelist.count_documents({
                'is_active': True
            })
            
            # Suspended users
            suspended_users = await self.db.users.count_documents({
                'is_suspended': True
            })
            
            # Top suspicious activities
            top_suspicious = await self.db.security_logs.aggregate([
                {'$match': {'timestamp': {'$gte': last_7d}}},
                {'$group': {'_id': '$activity_type', 'count': {'$sum': 1}}},
                {'$sort': {'count': -1}},
                {'$limit': 5}
            ]).to_list(None)
            
            return {
                'report_generated_at': datetime.utcnow().isoformat(),
                'time_period': '24 hours',
                'security_metrics': {
                    'suspicious_activities_24h': recent_suspicious,
                    'failed_logins_24h': failed_logins,
                    'users_with_2fa': users_with_2fa,
                    'whitelisted_ips': whitelisted_ips,
                    'suspended_users': suspended_users
                },
                'top_suspicious_activities_7d': [
                    {'activity': item['_id'], 'count': item['count']}
                    for item in top_suspicious
                ],
                'security_recommendations': self._get_security_recommendations(
                    users_with_2fa, recent_suspicious, failed_logins
                )
            }
            
        except Exception as e:
            logger.error(f"Error generating security report: {e}")
            return {'error': str(e)}
    
    def _get_security_recommendations(self, users_with_2fa: int, 
                                    suspicious_activities: int, failed_logins: int) -> List[str]:
        """Get security recommendations based on current metrics"""
        recommendations = []
        
        if users_with_2fa < 10:
            recommendations.append("Encourage more users to enable 2FA")
        
        if suspicious_activities > 50:
            recommendations.append("Review and tighten suspicious activity detection rules")
        
        if failed_logins > 100:
            recommendations.append("Consider implementing CAPTCHA for login attempts")
        
        recommendations.append("Regularly review and update IP whitelist")
        recommendations.append("Monitor user verification levels and encourage upgrades")
        
        return recommendations