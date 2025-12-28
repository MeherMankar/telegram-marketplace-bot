import asyncio
import logging
import os
import secrets
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
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
from app.services.PaymentTimeoutService import PaymentTimeoutService
from app.services.MonitoringService import MonitoringService
from app.services.ReferralService import ReferralService
from app.services.CodeInterceptorService import CodeInterceptorService
from app.utils.logger import setup_logger
from app.utils.error_tracker import ErrorTracker
from app.utils.encryption_rotation import EncryptionKeyManager

load_dotenv()

logger = setup_logger(__name__)

admin_user_ids_str = os.getenv('ADMIN_USER_IDS', '')
admin_user_ids = [int(uid.strip()) for uid in admin_user_ids_str.split(',') if uid.strip()]

WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', secrets.token_urlsafe(32))

def verify_webhook_signature(request_body: bytes, signature: str) -> bool:
    """Verify webhook signature to prevent CSRF"""
    import hmac
    import hashlib
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        request_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

async def main():
    """Main application entry point"""
    try:
        db_connection = DatabaseConnection()
        await db_connection.connect()
        
        api_id = int(os.getenv('API_ID'))
        api_hash = os.getenv('API_HASH')
        
        otp_service = OtpService(api_id, api_hash, db_connection)
        bulk_service = BulkService(db_connection, None)
        ml_service = MLService(db_connection)
        backup_service = BackupService(db_connection, api_id, api_hash)
        analytics_service = AnalyticsService(db_connection)
        support_service = SupportService(db_connection)
        marketing_service = MarketingService(db_connection)
        security_service = SecurityService(db_connection)
        compliance_service = ComplianceService(db_connection)
        social_service = SocialService(db_connection)
        payment_timeout_service = PaymentTimeoutService(db_connection)
        monitoring_service = MonitoringService(db_connection)
        referral_service = ReferralService(db_connection)
        error_tracker = ErrorTracker(db_connection)
        encryption_manager = EncryptionKeyManager(db_connection)
        code_interceptor = CodeInterceptorService(api_id, api_hash, db_connection)
        
        # Start background tasks
        asyncio.create_task(backup_service.schedule_automatic_backups())
        asyncio.create_task(ml_service.train_models())
        asyncio.create_task(payment_timeout_service.start_monitoring())
        
        # Check encryption key rotation
        if await encryption_manager.should_rotate():
            logger.info("Encryption key rotation needed")
            await encryption_manager.rotate_key()
        
        await asyncio.sleep(1)
        
        os.makedirs('sessions', exist_ok=True)
        
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
        buyer_bot.transfer_service.code_interceptor = code_interceptor
        
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
                bulk_service=bulk_service,
                code_interceptor_service=code_interceptor
            )
            # Set admin bot client in code interceptor after admin bot is created
            await admin_bot.start()
            code_interceptor.admin_bot_client = admin_bot.client
        
        logger.info("Starting Telegram Account Marketplace...")
        
        tasks = []
        
        await seller_bot.start()
        tasks.append(seller_bot.run_until_disconnected())
        logger.info("Seller bot started")
        
        await asyncio.sleep(2)
        
        await buyer_bot.start()
        tasks.append(buyer_bot.run_until_disconnected())
        logger.info("Buyer bot started")
        
        await asyncio.sleep(2)
        
        if admin_bot:
            tasks.append(admin_bot.run_until_disconnected())
            logger.info("Admin bot started")
        
        logger.info("All bots are running. Press Ctrl+C to stop.")
        
        port = os.getenv('PORT')
        if port and port != '8000':
            try:
                async def health_handler(request):
                    return web.Response(text="OK")
                
                app = web.Application()
                app.router.add_get('/health', health_handler)
                
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, '0.0.0.0', int(port))
                await site.start()
                logger.info(f"Health check server started on port {port}")
            except OSError as e:
                logger.warning(f"Web server failed to start: {e}")
        
        await asyncio.gather(*tasks)
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise
    except OSError as e:
        logger.error(f"System error: {e}")
        raise
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        raise
    finally:
        if 'db_connection' in locals():
            await db_connection.close()

if __name__ == "__main__":
    asyncio.run(main())
