#!/usr/bin/env python3
"""
Seed Bot Settings Script

This script initializes the database with default bot settings
that can be managed by admins through the admin bot.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the parent directory to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import db
from app.models.bot_settings import BotSettings

async def seed_bot_settings():
    """Seed the database with default bot settings"""
    try:
        print("🌱 Seeding bot settings...")
        
        # Define all setting types and their defaults
        settings_to_seed = [
            {
                "type": "seller_upload_limits",
                "settings": BotSettings.SELLER_UPLOAD_LIMITS,
                "description": "Seller bot upload limits and file restrictions"
            },
            {
                "type": "seller_verification_settings", 
                "settings": BotSettings.SELLER_VERIFICATION_SETTINGS,
                "description": "Seller bot verification thresholds and requirements"
            },
            {
                "type": "seller_payout_settings",
                "settings": BotSettings.SELLER_PAYOUT_SETTINGS,
                "description": "Seller bot payout configurations"
            },
            {
                "type": "buyer_purchase_settings",
                "settings": BotSettings.BUYER_PURCHASE_SETTINGS,
                "description": "Buyer bot purchase settings and timeouts"
            },
            {
                "type": "buyer_browsing_settings",
                "settings": BotSettings.BUYER_BROWSING_SETTINGS,
                "description": "Buyer bot browsing preferences and display options"
            },
            {
                "type": "general_settings",
                "settings": BotSettings.GENERAL_SETTINGS,
                "description": "General bot settings and system-wide configurations"
            },
            {
                "type": "security_settings",
                "settings": BotSettings.SECURITY_SETTINGS,
                "description": "Security settings and protection features"
            },
            {
                "type": "payment_settings",
                "settings": BotSettings.PAYMENT_SETTINGS,
                "description": "Payment method configurations and options"
            }
        ]
        
        # Seed each setting type
        for setting_config in settings_to_seed:
            # Check if setting already exists
            existing = await self.db_connection.admin_settings.find_one({
                "type": setting_config["type"]
            })
            
            if existing:
                print(f"⚠️  Settings '{setting_config['type']}' already exist, skipping...")
                continue
            
            # Insert new setting
            setting_doc = {
                "type": setting_config["type"],
                "settings": setting_config["settings"],
                "description": setting_config["description"],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "created_by": "system",
                "version": "1.0"
            }
            
            await self.db_connection.admin_settings.insert_one(setting_doc)
            print(f"✅ Seeded '{setting_config['type']}' settings")
        
        print("\n🎉 Bot settings seeding completed successfully!")
        print("\n📋 Seeded Settings Summary:")
        print("• Seller Upload Limits - Controls daily upload limits and file restrictions")
        print("• Seller Verification Settings - Manages account verification thresholds")
        print("• Seller Payout Settings - Configures payout methods and minimums")
        print("• Buyer Purchase Settings - Controls payment methods and timeouts")
        print("• Buyer Browsing Settings - Manages marketplace display options")
        print("• General Settings - System-wide configurations and maintenance mode")
        print("• Security Settings - Protection features and encryption settings")
        print("• Payment Settings - Payment method availability and simulation")
        
        print("\n🔧 Admin Access:")
        print("Use the Admin Bot to modify these settings:")
        print("1. Start the admin bot")
        print("2. Click 'Bot Settings'")
        print("3. Select the category to configure")
        print("4. Toggle settings as needed")
        
        return True
        
    except Exception as e:
        print(f"❌ Error seeding bot settings: {str(e)}")
        return False

async def verify_settings():
    """Verify that all settings were seeded correctly"""
    try:
        print("\n🔍 Verifying seeded settings...")
        
        setting_types = [
            "seller_upload_limits",
            "seller_verification_settings", 
            "seller_payout_settings",
            "buyer_purchase_settings",
            "buyer_browsing_settings",
            "general_settings",
            "security_settings",
            "payment_settings"
        ]
        
        all_good = True
        for setting_type in setting_types:
            setting = await self.db_connection.admin_settings.find_one({"type": setting_type})
            if setting:
                print(f"✅ {setting_type}: {len(setting.get('settings', {}))} settings")
            else:
                print(f"❌ {setting_type}: NOT FOUND")
                all_good = False
        
        if all_good:
            print("\n🎉 All settings verified successfully!")
        else:
            print("\n⚠️  Some settings are missing. Please run the seeding again.")
        
        return all_good
        
    except Exception as e:
        print(f"❌ Error verifying settings: {str(e)}")
        return False

async def reset_settings():
    """Reset all bot settings to defaults (use with caution)"""
    try:
        print("⚠️  RESETTING ALL BOT SETTINGS TO DEFAULTS...")
        response = input("Are you sure? This will overwrite all current settings (y/N): ")
        
        if response.lower() != 'y':
            print("❌ Reset cancelled.")
            return False
        
        # Delete all existing settings
        result = await self.db_connection.admin_settings.delete_many({
            "type": {"$in": [
                "seller_upload_limits",
                "seller_verification_settings", 
                "seller_payout_settings",
                "buyer_purchase_settings",
                "buyer_browsing_settings",
                "general_settings",
                "security_settings",
                "payment_settings"
            ]}
        })
        
        print(f"🗑️  Deleted {result.deleted_count} existing settings")
        
        # Re-seed with defaults
        success = await seed_bot_settings()
        
        if success:
            print("✅ Settings reset to defaults successfully!")
        else:
            print("❌ Failed to reset settings.")
        
        return success
        
    except Exception as e:
        print(f"❌ Error resetting settings: {str(e)}")
        return False

async def main():
    """Main function"""
    try:
        print("🚀 Bot Settings Management Script")
        print("=" * 50)
        
        if len(sys.argv) > 1:
            command = sys.argv[1].lower()
            
            if command == "reset":
                await reset_settings()
            elif command == "verify":
                await verify_settings()
            elif command == "seed":
                await seed_bot_settings()
                await verify_settings()
            else:
                print(f"❌ Unknown command: {command}")
                print("Available commands: seed, verify, reset")
        else:
            # Default: seed settings
            await seed_bot_settings()
            await verify_settings()
        
    except KeyboardInterrupt:
        print("\n⚠️  Script interrupted by user")
    except Exception as e:
        print(f"❌ Script error: {str(e)}")
    finally:
        # Close database connection
        if hasattr(db, 'client'):
            db.client.close()

if __name__ == "__main__":
    asyncio.run(main())