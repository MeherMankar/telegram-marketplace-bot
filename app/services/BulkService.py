import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime
from ..models.account import Account
from ..models.user import User
from ..utils.SessionImporter import SessionImporter
from ..services.VerificationService import VerificationService
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class BulkService:
    def __init__(self, db_connection, verification_service):
        self.db = db_connection
        self.verification_service = verification_service
        self.session_importer = SessionImporter()
    
    async def bulk_upload_accounts(self, user_id: int, session_files: List[Dict]) -> Dict[str, Any]:
        """Process multiple account uploads"""
        results = {
            'total': len(session_files),
            'successful': 0,
            'failed': 0,
            'errors': []
        }
        
        for i, session_data in enumerate(session_files):
            try:
                account_data = await self.session_importer.import_session(
                    session_data['content'], 
                    session_data['format']
                )
                
                verification_result = await self.verification_service.verify_account(account_data)
                
                if verification_result['is_valid']:
                    account = Account(
                        user_id=user_id,
                        phone=account_data['phone'],
                        username=account_data.get('username'),
                        country=account_data.get('country'),
                        creation_year=account_data.get('creation_year'),
                        session_data=account_data['session_data'],
                        verification_status='pending',
                        upload_date=utc_now()
                    )
                    
                    await self.db.accounts.insert_one(account.to_dict())
                    results['successful'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f"File {i+1}: {verification_result['reason']}")
                    
            except ValueError as e:
                results['failed'] += 1
                results['errors'].append(f"File {i+1}: Validation error - {str(e)}")
                logger.error(f"Bulk upload validation error for file {i+1}: {e}")
            except OSError as e:
                results['failed'] += 1
                results['errors'].append(f"File {i+1}: IO error - {str(e)}")
                logger.error(f"Bulk upload IO error for file {i+1}: {e}")
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"File {i+1}: {str(e)}")
                logger.error(f"Bulk upload error for file {i+1}: {e}", exc_info=True)
        
        return results
    
    async def bulk_approve_accounts(self, admin_id: int, account_ids: List[str], price: float) -> Dict[str, Any]:
        """Bulk approve multiple accounts"""
        results = {
            'total': len(account_ids),
            'successful': 0,
            'failed': 0
        }
        
        for account_id in account_ids:
            try:
                await self.db.accounts.update_one(
                    {'_id': account_id},
                    {
                        '$set': {
                            'verification_status': 'approved',
                            'price': price,
                            'approved_by': admin_id,
                            'approved_date': utc_now()
                        }
                    }
                )
                results['successful'] += 1
            except ValueError as e:
                results['failed'] += 1
                logger.error(f"Bulk approve validation error for {account_id}: {e}")
            except OSError as e:
                results['failed'] += 1
                logger.error(f"Bulk approve IO error for {account_id}: {e}")
            except Exception as e:
                results['failed'] += 1
                logger.error(f"Bulk approve error for {account_id}: {e}", exc_info=True)
        
        return results
    
    async def bulk_purchase_discount(self, user_id: int, account_ids: List[str]) -> Dict[str, Any]:
        """Calculate bulk purchase discount"""
        count = len(account_ids)
        
        if count >= 10:
            discount = 0.20
        elif count >= 5:
            discount = 0.15
        elif count >= 3:
            discount = 0.10
        else:
            discount = 0.0
        
        try:
            accounts = await self.db.accounts.find(
                {'_id': {'$in': account_ids}, 'verification_status': 'approved'}
            ).to_list(None)
            
            total_price = sum(acc['price'] for acc in accounts)
            discount_amount = total_price * discount
            final_price = total_price - discount_amount
            
            return {
                'total_accounts': count,
                'original_price': total_price,
                'discount_percent': discount * 100,
                'discount_amount': discount_amount,
                'final_price': final_price
            }
        except (ValueError, OSError) as e:
            logger.error(f"Bulk discount calculation error: {e}")
            return {'error': str(e)}
        except Exception as e:
            logger.error(f"Bulk discount calculation error: {e}", exc_info=True)
            return {'error': str(e)}
