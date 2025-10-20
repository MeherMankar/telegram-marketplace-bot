#!/usr/bin/env python3
"""
Script to seed admin users and initial configuration
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import init_db, db
from app.models import User
from datetime import datetime

load_dotenv()

async def seed_admin_users():
    """Seed admin users from environment variable"""
    try:
        await init_db()
        
        admin_ids_str = os.getenv('ADMIN_USER_IDS', '')
        if not admin_ids_str:
            print("❌ No ADMIN_USER_IDS found in environment variables")
            return
        
        admin_ids = [int(uid.strip()) for uid in admin_ids_str.split(',') if uid.strip()]
        
        for admin_id in admin_ids:
            # Check if admin user already exists
            existing_user = await self.db_connection.users.find_one({"telegram_user_id": admin_id})
            
            if existing_user:
                # Update existing user to admin
                await self.db_connection.users.update_one(
                    {"telegram_user_id": admin_id},
                    {"$set": {"is_admin": True}}
                )
                print(f"✅ Updated existing user {admin_id} to admin")
            else:
                # Create new admin user
                admin_user = {
                    "telegram_user_id": admin_id,
                    "username": f"admin_{admin_id}",
                    "first_name": "Admin",
                    "last_name": "User",
                    "is_admin": True,
                    "balance": 0.0,
                    "created_at": datetime.utcnow(),
                    "upload_count_today": 0
                }
                
                await self.db_connection.users.insert_one(admin_user)
                print(f"✅ Created new admin user {admin_id}")
        
        print(f"🎉 Successfully seeded {len(admin_ids)} admin users")
        
    except Exception as e:
        print(f"❌ Error seeding admin users: {str(e)}")

async def seed_price_table():
    """Seed initial price table"""
    try:
        # Create a settings collection for price table
        price_table = {
            "IN": {"2025": 40, "2024": 30, "2023": 25, "2022": 20},
            "US": {"2025": 50, "2024": 40, "2023": 35, "2022": 30},
            "UK": {"2025": 45, "2024": 35, "2023": 30, "2022": 25},
            "CA": {"2025": 45, "2024": 35, "2023": 30, "2022": 25},
            "AU": {"2025": 45, "2024": 35, "2023": 30, "2022": 25}
        }
        
        # Check if price table already exists
        existing_settings = await self.db_connection.settings.find_one({"type": "price_table"})
        
        if existing_settings:
            await self.db_connection.settings.update_one(
                {"type": "price_table"},
                {"$set": {"data": price_table, "updated_at": datetime.utcnow()}}
            )
            print("✅ Updated existing price table")
        else:
            await self.db_connection.settings.insert_one({
                "type": "price_table",
                "data": price_table,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            })
            print("✅ Created new price table")
        
        print("🎉 Successfully seeded price table")
        
    except Exception as e:
        print(f"❌ Error seeding price table: {str(e)}")

async def main():
    """Main seeding function"""
    print("🌱 Starting database seeding...")
    
    await seed_admin_users()
    await seed_price_table()
    
    print("✅ Database seeding completed!")

if __name__ == "__main__":
    asyncio.run(main())