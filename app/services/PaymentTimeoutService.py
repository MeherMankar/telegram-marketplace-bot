"""Payment timeout handling service"""
import asyncio
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class PaymentTimeoutService:
    """Handle payment timeouts and cleanup"""
    
    def __init__(self, db_connection):
        self.db = db_connection
        self.timeout_minutes = 30
    
    async def start_monitoring(self):
        """Start background task to monitor payment timeouts"""
        while True:
            try:
                await self.check_expired_payments()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Payment timeout monitoring error: {str(e)}")
                await asyncio.sleep(60)
    
    async def check_expired_payments(self):
        """Check and expire old pending payments"""
        cutoff_time = datetime.utcnow() - timedelta(minutes=self.timeout_minutes)
        
        # Expire pending transactions
        result = await self.db.transactions.update_many(
            {
                "status": "pending",
                "created_at": {"$lt": cutoff_time}
            },
            {
                "$set": {
                    "status": "expired",
                    "expired_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"Expired {result.modified_count} pending transactions")
        
        # Expire pending payment orders
        if hasattr(self.db, 'payment_orders'):
            result = await self.db.payment_orders.update_many(
                {
                    "status": "pending",
                    "created_at": {"$lt": cutoff_time}
                },
                {
                    "$set": {
                        "status": "expired",
                        "expired_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Expired {result.modified_count} pending payment orders")
        
        # Expire UPI orders
        if hasattr(self.db, 'upi_orders'):
            result = await self.db.upi_orders.update_many(
                {
                    "status": "pending",
                    "created_at": {"$lt": cutoff_time}
                },
                {
                    "$set": {
                        "status": "expired",
                        "expired_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Expired {result.modified_count} pending UPI orders")
    
    async def notify_user_timeout(self, user_id: int, transaction_id: str):
        """Notify user about payment timeout"""
        # This will be called by bot to send notification
        pass
