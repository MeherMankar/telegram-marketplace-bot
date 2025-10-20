import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime
from ..models.account import Account
from ..models.user import User
from ..utils.SessionImporter import SessionImporter
from ..services.VerificationService import VerificationService

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
                # Import session
                account_data = await self.session_importer.import_session(
                    session_data['content'], 
                    session_data['format']
                )
                
                # Verify account
                verification_result = await self.verification_service.verify_account(account_data)
                
                if verification_result['is_valid']:
                    # Save to database
                    account = Account(
                        user_id=user_id,
                        phone=account_data['phone'],
                        username=account_data.get('username'),
                        country=account_data.get('country'),
                        creation_year=account_data.get('creation_year'),
                        session_data=account_data['session_data'],
                        verification_status='pending',
                        upload_date=datetime.utcnow()
                    )
                    
                    await self.db.accounts.insert_one(account.to_dict())
                    results['successful'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f"File {i+1}: {verification_result['reason']}")
                    
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"File {i+1}: {str(e)}")
                logger.error(f"Bulk upload error for file {i+1}: {e}")
        
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
                            'approved_date': datetime.utcnow()
                        }
                    }
                )
                results['successful'] += 1
            except Exception as e:
                results['failed'] += 1
                logger.error(f"Bulk approve error for {account_id}: {e}")
        
        return results
    
    async def bulk_purchase_discount(self, user_id: int, account_ids: List[str]) -> Dict[str, Any]:
        """Calculate bulk purchase discount"""
        count = len(account_ids)
        
        # Discount tiers
        if count >= 10:
            discount = 0.20  # 20% for 10+
        elif count >= 5:
            discount = 0.15  # 15% for 5+
        elif count >= 3:
            discount = 0.10  # 10% for 3+
        else:
            discount = 0.0
        
        # Get account prices
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