#!/usr/bin/env python3
"""
Database Schema Fix Script
Fixes duplicate key errors and schema mismatches
"""

import asyncio
import os
import sys
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import DatabaseConnection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_database_schema():
    """Fix database schema issues"""
    db_conn = DatabaseConnection()
    try:
        # Connect to database
        await db_conn.connect()
        logger.info("Connected to database")
        
        # 1. Check for existing indexes
        logger.info("Checking existing indexes...")
        indexes = await db_conn.users.list_indexes().to_list(length=None)
        for index in indexes:
            logger.info(f"Index: {index}")
        
        # 2. Drop problematic indexes if they exist
        try:
            await db_conn.users.drop_index("user_id_1")
            logger.info("Dropped user_id_1 index")
        except Exception as e:
            logger.info(f"user_id_1 index doesn't exist or already dropped: {e}")
        
        # 3. Remove records with null user_id or telegram_user_id
        logger.info("Cleaning up null records...")
        result = await db_conn.users.delete_many({
            "$or": [
                {"user_id": None},
                {"telegram_user_id": None},
                {"telegram_user_id": {"$exists": False}}
            ]
        })
        logger.info(f"Deleted {result.deleted_count} records with null IDs")
        
        # 4. Create proper indexes
        logger.info("Creating proper indexes...")
        await db_conn.users.create_index("telegram_user_id", unique=True)
        logger.info("Created unique index on telegram_user_id")
        
        # 5. Check for duplicate telegram_user_ids
        logger.info("Checking for duplicate telegram_user_ids...")
        pipeline = [
            {"$group": {"_id": "$telegram_user_id", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}}
        ]
        duplicates = await db_conn.users.aggregate(pipeline).to_list(length=None)
        
        if duplicates:
            logger.warning(f"Found {len(duplicates)} duplicate telegram_user_ids")
            for dup in duplicates:
                logger.warning(f"Duplicate telegram_user_id: {dup['_id']} (count: {dup['count']})")
                
                # Keep the most recent record, delete others
                users = await db_conn.users.find(
                    {"telegram_user_id": dup["_id"]}
                ).sort("created_at", -1).to_list(length=None)
                
                if len(users) > 1:
                    # Keep the first (most recent), delete the rest
                    keep_user = users[0]
                    delete_ids = [user["_id"] for user in users[1:]]
                    
                    result = await db_conn.users.delete_many({"_id": {"$in": delete_ids}})
                    logger.info(f"Kept user {keep_user['_id']}, deleted {result.deleted_count} duplicates")
        else:
            logger.info("No duplicate telegram_user_ids found")
        
        # 6. Ensure all users have required fields
        logger.info("Ensuring all users have required fields...")
        await db_conn.users.update_many(
            {"balance": {"$exists": False}},
            {"$set": {"balance": 0.0}}
        )
        await db_conn.users.update_many(
            {"upload_count_today": {"$exists": False}},
            {"$set": {"upload_count_today": 0}}
        )
        await db_conn.users.update_many(
            {"is_admin": {"$exists": False}},
            {"$set": {"is_admin": False}}
        )
        await db_conn.users.update_many(
            {"created_at": {"$exists": False}},
            {"$set": {"created_at": datetime.utcnow()}}
        )
        
        logger.info("Database schema fix completed successfully!")
        
        # 7. Show final user count
        user_count = await db_conn.users.count_documents({})
        logger.info(f"Total users in database: {user_count}")
        
    except Exception as e:
        logger.error(f"Error fixing database schema: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        await db_conn.close()

if __name__ == "__main__":
    asyncio.run(fix_database_schema())