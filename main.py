import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError
from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web
from app.bots.SellerBot import SellerBot
from app.bots.BuyerBot import BuyerBot
from app.bots.AdminBot import AdminBot
from app.database.connection import DatabaseConnection
from app.services.OtpService import OtpService
from app.services.BulkService import BulkService
from app.services.MlService import MLService
from app.services.BackupService import BackupService
from app.services.AnalyticsService import AnalyticsService
from app.services.SupportService import SupportService
from app.services.MarketingService import MarketingService
from app.services.SecurityService import SecurityService
from app.services.ComplianceService import ComplianceService
from app.services.SocialService import SocialService
from app.utils.logger import setup_logger

load_dotenv()

# Setup logging
logger = setup_logger(__name__)

# Load admin user IDs from environment
admin_user_ids_str = os.getenv('ADMIN_USER_IDS', '')
admin_user_ids = [int(uid.strip()) for uid in admin_user_ids_str.split(',') if uid.strip()]

print(f"DEBUG: Loaded admin IDs from env: {admin_user_ids}")

async def main():
    """Main application entry point"""
    try:
        # Initialize database connection
        db_connection = DatabaseConnection()
        await db_connection.connect()
        
        # Get API credentials
        api_id = int(os.getenv('API_ID'))
        api_hash = os.getenv('API_HASH')
        
        # Initialize all services
        otp_service = OtpService(api_id, api_hash)
        bulk_service = BulkService(db_connection, None)  # Will set verification_service later
        ml_service = MLService(db_connection)
        backup_service = BackupService(db_connection, api_id, api_hash)
        analytics_service = AnalyticsService(db_connection)
        support_service = SupportService(db_connection)
        marketing_service = MarketingService(db_connection)
        security_service = SecurityService(db_connection)
        compliance_service = ComplianceService(db_connection)
        social_service = SocialService(db_connection)
        
        # Start background tasks
        asyncio.create_task(backup_service.schedule_automatic_backups())
        asyncio.create_task(ml_service.train_models())
        
        # Initialize bots with time sync fix
        await asyncio.sleep(1)  # Time sync fix
        
        # Create sessions directory
        os.makedirs('sessions', exist_ok=True)
        
        # Seller Bot with all services
        seller_bot = SellerBot(
            api_id=api_id,
            api_hash=api_hash,
            bot_token=os.getenv('SELLER_BOT_TOKEN'),
            db_connection=db_connection,
            otp_service=otp_service,
            bulk_service=bulk_service,
            ml_service=ml_service,
            security_service=security_service,
            social_service=social_service
        )
        
        # Buyer Bot with all services
        buyer_bot = BuyerBot(
            api_id=api_id,
            api_hash=api_hash,
            bot_token=os.getenv('BUYER_BOT_TOKEN'),
            db_connection=db_connection,
            otp_service=otp_service,
            marketing_service=marketing_service,
            social_service=social_service,
            support_service=support_service
        )
        
        # Admin Bot with all services
        admin_bot = None
        admin_token = os.getenv('ADMIN_BOT_TOKEN')
        if admin_token:
            admin_bot = AdminBot(
                api_id=api_id,
                api_hash=api_hash,
                bot_token=admin_token,
                db_connection=db_connection,
                admin_user_ids=admin_user_ids,
                analytics_service=analytics_service,
                backup_service=backup_service,
                support_service=support_service,
                marketing_service=marketing_service,
                security_service=security_service,
                compliance_service=compliance_service,
                bulk_service=bulk_service
            )
        
        # Start all bots
        logger.info("Starting Telegram Account Marketplace...")
        
        tasks = []
        
        # Start seller bot
        await seller_bot.start()
        tasks.append(seller_bot.run_until_disconnected())
        logger.info("Seller bot started")
        
        await asyncio.sleep(2)  # Prevent session conflicts
        
        # Start buyer bot
        await buyer_bot.start()
        tasks.append(buyer_bot.run_until_disconnected())
        logger.info("Buyer bot started")
        
        await asyncio.sleep(2)  # Prevent session conflicts
        
        # Start admin bot if configured
        if admin_bot:
            await admin_bot.start()
            tasks.append(admin_bot.run_until_disconnected())
            logger.info("Admin bot started")
        
        logger.info("All bots are running. Press Ctrl+C to stop.")
        
        # Optional web server for health checks (only if PORT is set)
        if os.getenv('PORT'):
            app = web.Application()
            app.router.add_get('/', lambda request: web.Response(text="Telegram Bot is running!"))
            app.router.add_get('/health', lambda request: web.Response(text="OK"))
            
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', int(os.getenv('PORT', 8000)))
            await site.start()
            logger.info(f"Health check server started on port {os.getenv('PORT', 8000)}")
        
        # Run all bots concurrently
        await asyncio.gather(*tasks)
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
    finally:
        # Cleanup
        if 'db_connection' in locals():
            await db_connection.close()

if __name__ == "__main__":
    asyncio.run(main())