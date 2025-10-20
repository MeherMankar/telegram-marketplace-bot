#!/usr/bin/env python3
"""
Simple database cleanup script
Removes problematic records and indexes
"""

import asyncio
import os
import sys
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def cleanup_database():
    """Clean up database schema issues"""
    try:
        # Connect directly to MongoDB
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/telegram_marketplace')
        client = AsyncIOMotorClient(mongo_uri)
        db = client.get_default_database()
        
        logger.info("Connected to database")
        
        # 1. Drop the problematic user_id index
        try:
            await db.users.drop_index("user_id_1")
            logger.info("Dropped user_id_1 index")
        except Exception as e:
            logger.info(f"user_id_1 index doesn't exist: {e}")
        
        # 2. Remove all records with null user_id or telegram_user_id
        logger.info("Cleaning up problematic records...")
        result = await db.users.delete_many({
            "$or": [
                {"user_id": None},
                {"telegram_user_id": None},
                {"telegram_user_id": {"$exists": False}},
                {"user_id": {"$exists": True, "$ne": None}}  # Remove old user_id records
            ]
        })
        logger.info(f"Deleted {result.deleted_count} problematic records")
        
        # 3. Create proper index on telegram_user_id
        try:
            await db.users.create_index("telegram_user_id", unique=True)
            logger.info("Created unique index on telegram_user_id")
        except Exception as e:
            logger.info(f"Index creation result: {e}")
        
        # 4. Show final state
        user_count = await db.users.count_documents({})
        logger.info(f"Total users remaining: {user_count}")
        
        # 5. List all indexes
        indexes = await db.users.list_indexes().to_list(length=None)
        logger.info("Current indexes:")
        for index in indexes:
            logger.info(f"  - {index}")
        
        logger.info("Database cleanup completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(cleanup_database())