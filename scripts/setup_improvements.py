"""
Setup script for improvements
Run this after deploying the new code
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def setup():
    """Setup all improvements"""
    
    logger.info("🚀 Setting up improvements...")
    
    # Connect to MongoDB
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/telegram_marketplace')
    client = AsyncIOMotorClient(mongo_uri)
    db = client.get_default_database()
    
    # 1. Create indexes
    logger.info("📊 Creating database indexes...")
    
    await db.users.create_index("telegram_user_id", unique=True)
    await db.users.create_index("referral_code", unique=True, sparse=True)
    await db.users.create_index("last_activity")
    
    await db.accounts.create_index("seller_id")
    await db.accounts.create_index("status")
    await db.accounts.create_index([("status", 1), ("created_at", -1)])
    
    await db.listings.create_index("account_id", unique=True)
    await db.listings.create_index("status")
    await db.listings.create_index([("country", 1), ("creation_year", 1), ("status", 1)])
    
    await db.transactions.create_index("user_id")
    await db.transactions.create_index("status")
    await db.transactions.create_index([("status", 1), ("created_at", -1)])
    
    await db.payment_orders.create_index("order_id", unique=True)
    await db.payment_orders.create_index([("status", 1), ("created_at", -1)])
    
    await db.upi_orders.create_index("order_id", unique=True)
    await db.upi_orders.create_index([("status", 1), ("created_at", -1)])
    
    await db.error_logs.create_index([("resolved", 1), ("timestamp", -1)])
    await db.metrics.create_index([("name", 1), ("timestamp", -1)])
    await db.referrals.create_index("referrer_id")
    await db.referrals.create_index("referee_id")
    
    logger.info("✅ Indexes created")
    
    # 2. Initialize collections
    logger.info("📦 Initializing collections...")
    
    collections = [
        "error_logs",
        "metrics",
        "referrals",
        "encryption_keys",
        "admin_notifications"
    ]
    
    existing_collections = await db.list_collection_names()
    
    for collection in collections:
        if collection not in existing_collections:
            await db.create_collection(collection)
            logger.info(f"  ✓ Created {collection}")
    
    logger.info("✅ Collections initialized")
    
    # 3. Set up encryption key
    logger.info("🔐 Setting up encryption key...")
    
    current_key = await db.encryption_keys.find_one({"current": True})
    if not current_key:
        from datetime import datetime
        encryption_key = os.getenv('SESSION_ENCRYPTION_KEY')
        
        if encryption_key:
            await db.encryption_keys.insert_one({
                "key": encryption_key,
                "current": True,
                "created_at": datetime.utcnow()
            })
            logger.info("  ✓ Encryption key saved")
        else:
            logger.warning("  ⚠️ SESSION_ENCRYPTION_KEY not found in .env")
    else:
        logger.info("  ✓ Encryption key already exists")
    
    # 4. Verify setup
    logger.info("🔍 Verifying setup...")
    
    # Check indexes
    user_indexes = await db.users.index_information()
    if "telegram_user_id_1" in user_indexes:
        logger.info("  ✓ User indexes verified")
    
    listing_indexes = await db.listings.index_information()
    if "country_1_creation_year_1_status_1" in listing_indexes:
        logger.info("  ✓ Listing indexes verified")
    
    # Check collections
    collections_count = len(await db.list_collection_names())
    logger.info(f"  ✓ {collections_count} collections found")
    
    logger.info("\n✅ Setup completed successfully!")
    logger.info("\n📝 Next steps:")
    logger.info("1. Review IMPROVEMENTS.md for feature documentation")
    logger.info("2. Check INTEGRATION_EXAMPLE.py for code examples")
    logger.info("3. Integrate features into your bot handlers")
    logger.info("4. Test in development environment")
    logger.info("5. Deploy to production")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(setup())
