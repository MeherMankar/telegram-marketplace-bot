"""Create database indexes for optimization"""
import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_indexes():
    """Create all necessary database indexes"""
    
    # Connect to MongoDB
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/telegram_marketplace')
    client = AsyncIOMotorClient(mongo_uri)
    db = client.get_default_database()
    
    logger.info("Creating database indexes...")
    
    # Users collection indexes
    await db.users.create_index("telegram_user_id", unique=True)
    await db.users.create_index("referral_code", unique=True, sparse=True)
    await db.users.create_index("last_activity")
    logger.info("✓ Users indexes created")
    
    # Accounts collection indexes
    await db.accounts.create_index("seller_id")
    await db.accounts.create_index("status")
    await db.accounts.create_index([("status", 1), ("created_at", -1)])
    await db.accounts.create_index("telegram_account_id", unique=True, sparse=True)
    logger.info("✓ Accounts indexes created")
    
    # Listings collection indexes
    await db.listings.create_index("account_id", unique=True)
    await db.listings.create_index("status")
    await db.listings.create_index("country")
    await db.listings.create_index("creation_year")
    await db.listings.create_index([("country", 1), ("creation_year", 1), ("status", 1)])
    await db.listings.create_index([("status", 1), ("created_at", -1)])
    logger.info("✓ Listings indexes created")
    
    # Transactions collection indexes
    await db.transactions.create_index("user_id")
    await db.transactions.create_index("status")
    await db.transactions.create_index("type")
    await db.transactions.create_index([("user_id", 1), ("status", 1)])
    await db.transactions.create_index([("status", 1), ("created_at", -1)])
    logger.info("✓ Transactions indexes created")
    
    # Payment orders indexes
    await db.payment_orders.create_index("order_id", unique=True)
    await db.payment_orders.create_index("user_id")
    await db.payment_orders.create_index("status")
    await db.payment_orders.create_index([("status", 1), ("created_at", -1)])
    logger.info("✓ Payment orders indexes created")
    
    # UPI orders indexes
    await db.upi_orders.create_index("order_id", unique=True)
    await db.upi_orders.create_index("user_id")
    await db.upi_orders.create_index("status")
    await db.upi_orders.create_index([("status", 1), ("created_at", -1)])
    logger.info("✓ UPI orders indexes created")
    
    # Error logs indexes
    await db.error_logs.create_index("timestamp")
    await db.error_logs.create_index("resolved")
    await db.error_logs.create_index([("resolved", 1), ("timestamp", -1)])
    logger.info("✓ Error logs indexes created")
    
    # Metrics indexes
    await db.metrics.create_index("name")
    await db.metrics.create_index("timestamp")
    await db.metrics.create_index([("name", 1), ("timestamp", -1)])
    logger.info("✓ Metrics indexes created")
    
    # Referrals indexes
    await db.referrals.create_index("referrer_id")
    await db.referrals.create_index("referee_id")
    await db.referrals.create_index("created_at")
    logger.info("✓ Referrals indexes created")
    
    # Admin actions indexes
    await db.admin_actions.create_index("admin_id")
    await db.admin_actions.create_index("action_type")
    await db.admin_actions.create_index("timestamp")
    logger.info("✓ Admin actions indexes created")
    
    logger.info("✅ All indexes created successfully!")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(create_indexes())
