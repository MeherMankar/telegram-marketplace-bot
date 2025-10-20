import logging
from datetime import datetime
from app.services.ListingService import ListingService
from app.services.OtpService import OtpService

logger = logging.getLogger(__name__)

class AdminService:
    """Admin service for account and payment management"""
    
    def __init__(self, db_connection=None):
        self.db_connection = db_connection
        if db_connection:
            self.listing_service = ListingService(db_connection)
            self.otp_service = OtpService(db_connection)
    
    async def approve_account(self, admin_id: int, account_id: str) -> dict:
        """Approve an account for listing"""
        try:
            account = await self.db_connection.accounts.find_one({"_id": account_id})
            if not account:
                return {"success": False, "error": "Account not found"}
            
            # Update account status
            await self.db_connection.accounts.update_one(
                {"_id": account_id},
                {
                    "$set": {
                        "status": "approved",
                        "approved_at": datetime.utcnow(),
                        "approved_by": admin_id
                    }
                }
            )
            
            # Create listing
            listing_result = await self.listing_service.create_listing(account_id, account["seller_id"])
            
            if listing_result["success"]:
                # Enable OTP destroyer
                await self.otp_service.enable_otp_destroyer(account_id, account["session_string"])
                
                return {
                    "success": True,
                    "price": listing_result["price"],
                    "listing_id": listing_result["listing_id"]
                }
            else:
                return {"success": False, "error": "Failed to create listing"}
            
        except Exception as e:
            logger.error(f"Failed to approve account: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def reject_account(self, admin_id: int, account_id: str, reason: str) -> dict:
        """Reject an account"""
        try:
            await self.db_connection.accounts.update_one(
                {"_id": account_id},
                {
                    "$set": {
                        "status": "rejected",
                        "rejected_at": datetime.utcnow(),
                        "rejected_by": admin_id,
                        "rejection_reason": reason
                    }
                }
            )
            
            return {"success": True, "message": "Account rejected"}
            
        except Exception as e:
            logger.error(f"Failed to reject account: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def approve_payment(self, admin_id: int, transaction_id: str) -> dict:
        """Approve a payment"""
        try:
            await self.db_connection.transactions.update_one(
                {"_id": transaction_id},
                {
                    "$set": {
                        "status": "approved",
                        "approved_at": datetime.utcnow(),
                        "approved_by": admin_id
                    }
                }
            )
            
            return {"success": True, "message": "Payment approved"}
            
        except Exception as e:
            logger.error(f"Failed to approve payment: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def get_admin_stats(self) -> dict:
        """Get admin statistics"""
        try:
            stats = {
                'accounts': {
                    'pending': await self.db_connection.accounts.count_documents({'status': 'pending'}),
                    'approved': await self.db_connection.accounts.count_documents({'status': 'approved'}),
                    'rejected': await self.db_connection.accounts.count_documents({'status': 'rejected'}),
                    'sold': await self.db_connection.accounts.count_documents({'status': 'sold'})
                },
                'listings': {
                    'active': await self.db_connection.listings.count_documents({'status': 'active'}),
                    'sold': await self.db_connection.listings.count_documents({'status': 'sold'})
                },
                'transactions': {
                    'pending': await self.db_connection.transactions.count_documents({'status': 'pending'}),
                    'confirmed': await self.db_connection.transactions.count_documents({'status': 'confirmed'})
                },
                'users': {
                    'total': await self.db_connection.users.count_documents({}),
                    'sellers': await self.db_connection.users.count_documents({'upload_count_today': {'$gt': 0}})
                }
            }
            return stats
        except Exception as e:
            logger.error(f"Failed to get admin stats: {str(e)}")
            return {'accounts': {}, 'listings': {}, 'transactions': {}, 'users': {}}