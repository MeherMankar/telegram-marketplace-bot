import os
import tempfile
from datetime import datetime, timedelta
from telethon import events, Button
from telethon.tl.types import DocumentAttributeFilename
from .BaseBot import BaseBot
from app.database.connection import db
from app.models import Account, AccountStatus, SettingsManager
from app.services.VerificationService import VerificationService
from app.services.PaymentService import PaymentService

from app.utils.SessionImporter import SessionImporter
from app.utils.UniversalSessionConverter import UniversalSessionConverter
from app.services.OtpService import OtpService
from app.services.AccountLoginService import AccountLoginService
from app.utils import encrypt_session, create_main_menu, create_tos_keyboard, create_otp_method_keyboard, create_otp_verification_keyboard
import logging
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class SellerBot(BaseBot):
    def __init__(self, api_id: int, api_hash: str, bot_token: str, db_connection, otp_service=None, bulk_service=None, ml_service=None, security_service=None, social_service=None):
        super().__init__(api_id, api_hash, bot_token, db_connection, "Seller")
        self.api_id = api_id
        self.api_hash = api_hash
        self.verification_service = VerificationService(db_connection)
        self.payment_service = PaymentService(db_connection)
        self.bulk_service = bulk_service
        self.ml_service = ml_service
        self.security_service = security_service
        self.social_service = social_service
        self.session_importer = SessionImporter()
        self.settings_manager = SettingsManager(db_connection)
        # Single shared OTP service instance
        self.otp_service = OtpService(api_id, api_hash)
        # Account login service for session handling
        self.account_login_service = AccountLoginService(db_connection, api_id, api_hash)
    
    async def get_upload_limits(self):
        """Get upload limits from admin settings"""
        return await self.settings_manager.get_setting("seller_upload_limits")
    
    async def get_verification_settings(self):
        """Get verification settings from admin settings"""
        return await self.settings_manager.get_setting("seller_verification_settings")
    
    async def get_payout_settings(self):
        """Get payout settings from admin settings"""
        return await self.settings_manager.get_setting("seller_payout_settings")
    
    async def get_general_settings(self):
        """Get general settings from admin settings"""
        return await self.settings_manager.get_setting("general_settings")
    
    async def get_security_settings(self):
        """Get security settings from admin settings"""
        return await self.settings_manager.get_setting("security_settings")
    
    def register_handlers(self):
        """Register seller bot event handlers"""
        
        @self.client.on(events.NewMessage)
        async def all_messages_handler(event):
            print(f"[SELLER] 📨 ANY MESSAGE: {event.text[:50] if event.text else 'No text'}")
            logger.info(f"[SELLER] 📨 ANY MESSAGE RECEIVED: {event.text[:50] if event.text else 'No text'}")
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            logger.info(f"[SELLER] /start handler triggered")
            await self.handle_start(event)
        
        @self.client.on(events.NewMessage(pattern='/debug'))
        async def debug_handler(event):
            logger.info(f"[SELLER] /debug handler triggered")
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": event.sender_id})
            state = user_doc.get('state') if user_doc else 'No state'
            await event.respond(f"Seller bot is working! 🔥\n\nYour state: {state}\nUser ID: {event.sender_id}")
        
        @self.client.on(events.CallbackQuery)
        async def callback_handler(event):
            print(f"[SELLER] 🔔 CALLBACK: {event.data}")
            logger.info(f"[SELLER] 🔔 CALLBACK RECEIVED: {event.data}")
            await self.handle_callback(event)
        
        @self.client.on(events.NewMessage(func=lambda e: e.document))
        async def document_handler(event):
            await self.handle_document(event)
        
        @self.client.on(events.NewMessage(func=lambda e: e.text and not e.text.startswith('/')))
        async def text_handler(event):
            print(f"[SELLER] 🔔 TEXT HANDLER: {event.text[:50]}")
            logger.info(f"[SELLER] 🔔 TEXT HANDLER TRIGGERED for {event.sender_id}")
            logger.info(f"[SELLER] 📝 Text content: {event.text[:100]}")
            try:
                await self.handle_text(event)
            except Exception as e:
                print(f"[SELLER] ERROR: {e}")
                logger.error(f"[SELLER] ❌ Text handler crashed: {e}")
                import traceback
                logger.error(traceback.format_exc())
    
    async def handle_start(self, event):
        """Handle /start command"""
        try:
            logger.info(f"[SELLER] /start command received from user {event.sender_id}")
            user = await self.get_or_create_user(event)
            
            # Clear any existing state on /start
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"state": "", "temp_phone": "", "temp_otp_code": ""}}
            )
            logger.info(f"[SELLER] Cleared state for user {user.telegram_user_id}")
            logger.info(f"[SELLER] Showing welcome message to {user.first_name} ({user.telegram_user_id})")
            
            welcome_message = f"""
🔥 **Welcome to Telegram Account Marketplace - Seller Bot**

Hello {user.first_name}! 👋

This bot allows you to sell your Telegram accounts safely and securely.

**How it works:**
1. Upload your account session OR use Phone + OTP
2. Automated verification checks
3. Admin review and approval
4. Account listed for sale
5. Get paid when sold!

**Two Ways to Sell:**
📤 **Session Upload**: Upload session files/strings
📱 **Phone + OTP**: Verify ownership via phone number

Ready to start selling?
            """
            
            buttons = create_main_menu(is_seller=True)
            logger.info(f"[SELLER] Main menu buttons: {buttons}")
            await self.send_message(event.chat_id, welcome_message, buttons)
            logger.info(f"[SELLER] Welcome message sent to {user.telegram_user_id}")
            
        except Exception as e:
            logger.error(f"[SELLER] Start handler error for {event.sender_id}: {str(e)}")
            await self.send_message(event.chat_id, "❌ An error occurred. Please try again.")
    
    async def handle_callback(self, event):
        """Handle callback queries"""
        try:
            data = event.data.decode('utf-8')
            logger.info(f"[SELLER] Callback received: '{data}' from user {event.sender_id}")
            user = await self.get_or_create_user(event)
            
            if data == "upload_account":
                await self.handle_upload_account(event, user)
            elif data == "sell_via_otp":
                logger.info(f"[SELLER] User {user.telegram_user_id} clicked 'Sell via OTP'")
                await self.handle_sell_via_otp(event, user)
            elif data == "use_phone_otp":
                logger.info(f"[SELLER] User {user.telegram_user_id} clicked 'Use Phone + OTP'")
                await self.handle_use_phone_otp(event, user)
            elif data == "upload_session":
                logger.info(f"[SELLER] User {user.telegram_user_id} clicked 'Upload Session'")
                await self.handle_upload_account(event, user)
            elif data == "my_balance":
                user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
                balance = user_doc.get("balance", 0.0) if user_doc else 0.0
                await self.edit_message(event, f"💰 **Your Balance: ${balance:.2f}**", [[Button.inline("💸 Request Payout", "request_payout"), Button.inline("🔙 Back", "back_to_main")]])
            elif data == "my_accounts":
                accounts = await self.db_connection.accounts.find({"seller_id": user.telegram_user_id}).sort("created_at", -1).to_list(length=10)
                if not accounts:
                    await self.edit_message(event, "📊 **Your Accounts**\n\nYou haven't uploaded any accounts yet.", [[Button.inline("📤 Upload Account", "upload_account"), Button.inline("🔙 Back", "back_to_main")]])
                    return
                
                accounts_message = "📊 **Your Accounts**\n\n"
                for account in accounts:
                    status_emoji = {"pending": "⏳", "checking": "🔍", "approved": "✅", "rejected": "❌", "sold": "💰"}.get(account["status"], "❓")
                    username = account.get("username", "No username")
                    accounts_message += f"{status_emoji} **{username}** - {account['status'].title()}\n"
                
                await self.edit_message(event, accounts_message, [[Button.inline("📤 Upload Another", "upload_account"), Button.inline("🔙 Back", "back_to_main")]])
            elif data == "request_payout":
                user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
                balance = user_doc.get("balance", 0.0) if user_doc else 0.0
                if balance <= 0:
                    await self.edit_message(event, "💸 **Request Payout**\n\n❌ You don't have any balance to withdraw.", [[Button.inline("🔙 Back", "back_to_main")]])
                    return
                
                await self.edit_message(event, f"💸 **Request Payout**\n\n💰 **Available Balance: ${balance:.2f}**\n\nChoose your preferred payout method:", [[Button.inline("💳 UPI Payout", "payout_upi"), Button.inline("₿ Crypto Payout", "payout_crypto")], [Button.inline("🔙 Back", "back_to_main")]])
            elif data == "accept_tos":
                await self.db_connection.users.update_one({"telegram_user_id": user.telegram_user_id}, {"$set": {"tos_accepted": utc_now()}})
                # Check what flow user came from
                user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
                if user_doc and user_doc.get("temp_flow") == "otp":
                    # Continue with OTP flow
                    await self.db_connection.users.update_one({"telegram_user_id": user.telegram_user_id}, {"$unset": {"temp_flow": ""}})
                    await self.handle_sell_via_otp(event, user)
                else:
                    # Continue with upload flow
                    await self.edit_message(event, "📤 **Upload Account**\n\nPlease send your session file or session string.", [[Button.inline("🔙 Back", "back_to_main")]])
                    await self.db_connection.users.update_one({"telegram_user_id": user.telegram_user_id}, {"$set": {"state": "awaiting_upload"}})
            elif data == "cancel_upload" or data == "cancel_otp":
                await self.db_connection.users.update_one({"telegram_user_id": event.sender_id}, {"$unset": {"state": "", "temp_phone": "", "temp_otp": ""}})
                buttons = create_main_menu(is_seller=True)
                await self.edit_message(event, "Upload cancelled. What would you like to do?", buttons)
            elif data.startswith("resend_otp_"):
                user_id = int(data.split("_", 2)[2])
                user_doc = await self.db_connection.users.find_one({"telegram_user_id": user_id})
                if not user_doc or not user_doc.get("temp_phone"):
                    await self.edit_message(event, "❌ **No Phone Number Found**\n\nPlease start the process again.", [[Button.inline("🔙 Back", "back_to_main")]])
                    return
                
                phone_number = user_doc["temp_phone"]
                otp_result = await self.otp_service.verify_account_ownership(phone_number, user_id)
                
                if otp_result['success']:
                    await self.edit_message(event, f"✅ **New OTP Sent!**\n\n📱 **Phone:** {phone_number}\n⏰ **Expires in:** 5 minutes\n\nPlease enter the new verification code:", buttons=create_otp_verification_keyboard(user_id))
                else:
                    await self.edit_message(event, f"❌ **Failed to Resend OTP**\n\n{otp_result['error']}", [[Button.inline("🔙 Back", "back_to_main")]])
            elif data.startswith("payout_"):
                method = data.split("_")[1]
                user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
                balance = user_doc.get("balance", 0.0) if user_doc else 0.0
                
                if method == "upi":
                    payout_message = f"💳 **UPI Payout Request**\n\n💰 **Amount: ${balance:.2f}**\n\nPlease provide your UPI ID:"
                else:
                    payout_message = f"₿ **Crypto Payout Request**\n\n💰 **Amount: ${balance:.2f}**\n\nPlease provide your wallet address:"
                
                await self.edit_message(event, payout_message, [[Button.inline("🔙 Cancel", "request_payout")]])
                await self.db_connection.users.update_one({"telegram_user_id": user.telegram_user_id}, {"$set": {"state": f"payout_{method}"}})
            elif data == "back_to_main":
                logger.info(f"[SELLER] User {user.telegram_user_id} clicked 'Back to Main'")
                # Clear state when going back to main
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$unset": {"state": "", "temp_phone": "", "temp_otp_code": ""}}
                )
                await self.handle_start(event)
            elif data == "seller_stats":
                await self.handle_seller_stats(event, user)
            elif data == "my_rating":
                await self.handle_my_rating(event, user)
            elif data == "help":
                await self.handle_help(event)
            else:
                logger.warning(f"[SELLER] Unknown callback data: '{data}' from user {event.sender_id}")
            
            try:
                await self.answer_callback(event)
            except Exception:
                pass  # Ignore callback answer errors
            
        except Exception as e:
            logger.error(f"[SELLER] Callback handler error for {event.sender_id}: {str(e)}")
            try:
                await self.answer_callback(event, "❌ An error occurred", alert=True)
            except Exception:
                pass  # Ignore callback answer errors
    
    async def handle_sell_via_otp(self, event, user):
        """Handle sell via OTP option"""
        try:
            # Check if maintenance mode is enabled
            general_settings = await self.get_general_settings()
            if general_settings.get('maintenance_mode', False):
                await self.edit_message(
                    event,
                    "🔧 **Maintenance Mode**\n\nThe system is currently under maintenance.\nPlease try again later.",
                    [[Button.inline("🔙 Back", "back_to_main")]]
                )
                return
            
            # Check daily upload limit (admin managed)
            upload_limits = await self.get_upload_limits()
            if upload_limits.get('enabled', False):
                max_uploads = upload_limits.get('max_per_day', 999)
                today = utc_now().date()
                if user.last_upload_date and user.last_upload_date.date() == today:
                    if user.upload_count_today >= max_uploads:
                        await self.edit_message(
                            event,
                            f"❌ **Daily Upload Limit Reached**\n\nYou can upload maximum {max_uploads} accounts per day.\nTry again tomorrow.",
                            [[Button.inline("🔙 Back", "back_to_main")]]
                        )
                        return
            
            # Skip ToS for OTP flow - show method selection directly
            # ToS will be handled per method if needed
            
            # Show OTP selling method selection
            otp_message = """
📱 **Sell Account via Phone + OTP**

Choose how you want to provide your account:

**📤 Upload Session**: If you have session files/strings
**📱 Phone + OTP**: Verify ownership via your phone number
**📦 TData Archive**: Upload Telegram Desktop data

**Phone + OTP Process:**
1. Enter your account's phone number
2. Receive OTP on your phone
3. Enter OTP to verify ownership
4. Automated verification checks
5. Admin review and approval
6. Account listed for sale

**Session Upload Process:**
1. Upload session file or paste session string
2. Automated verification checks
3. Admin review and approval
4. Account listed for sale

**TData Process:**
1. Export TData from Telegram Desktop
2. Create ZIP archive of tdata folder
3. Upload ZIP file to bot
4. Automatic conversion and verification
            """
            
            buttons = create_otp_method_keyboard()
            await self.edit_message(event, otp_message, buttons)
            
        except Exception as e:
            logger.error(f"[SELLER] Sell via OTP handler error for {user.telegram_user_id}: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_use_phone_otp(self, event, user):
        """Handle phone + OTP method"""
        try:
            user_id = event.sender_id
            
            phone_message = """
📱 **Enter Your Phone Number**

Please enter the phone number of the Telegram account you want to sell.

**Format Examples:**
• +1234567890
• +91987654321
• +447123456789

**Important:**
• Use international format with country code
• This must be the phone number of your Telegram account
• You will receive an OTP on this number

Send your phone number:
            """
            
            # Use in-memory pending_actions like teleguard does
            if not hasattr(self, 'pending_actions'):
                self.pending_actions = {}
            
            self.pending_actions[user_id] = {
                "action": "awaiting_phone_otp"
            }
            
            print(f"[SELLER] Set pending_action for {user_id}: awaiting_phone_otp")
            logger.info(f"[SELLER] Set pending_action for {user_id}: awaiting_phone_otp")
            
            await self.edit_message(
                event,
                phone_message,
                [[Button.inline("🔙 Cancel", "cancel_otp")]]
            )
            
        except Exception as e:
            print(f"[SELLER] ERROR in handle_use_phone_otp: {e}")
            logger.error(f"Use phone OTP handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_text(self, event):
        """Handle text messages (session strings, phone numbers, OTP codes)"""
        try:
            print(f"[SELLER] handle_text called for {event.sender_id}")
            logger.info(f"[SELLER] ===== TEXT HANDLER CALLED =====")
            
            if not event.text:
                return
            
            user_id = event.sender_id
            
            # Check pending_actions first (in-memory state)
            if not hasattr(self, 'pending_actions'):
                self.pending_actions = {}
            
            pending_action = self.pending_actions.get(user_id)
            print(f"[SELLER] Pending action: {pending_action}")
            
            if pending_action and pending_action.get("action") == "awaiting_phone_otp":
                phone_text = str(event.text).strip()
                print(f"[SELLER] PHONE OTP FLOW - Phone: {phone_text}")
                
                # Clear pending action
                self.pending_actions.pop(user_id, None)
                
                # Create minimal user object
                class UserObj:
                    def __init__(self, uid):
                        self.telegram_user_id = uid
                user = UserObj(user_id)
                
                await self.process_phone_number(event, user, phone_text)
                return
            
            # Fallback to database state
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user_id})
            if not user_doc:
                return
            
            state = user_doc.get("state")
            print(f"[SELLER] DB state: {state}")
            
            if not state:
                return
            
            if state == "awaiting_upload":
                await self.db_connection.users.update_one({"telegram_user_id": user.telegram_user_id}, {"$unset": {"state": ""}})
                processing_msg = await self.send_message(event.chat_id, "🔄 **Processing your session...**\n\nThis may take a few moments.")
                
                session_text = str(event.text).strip() if event.text else ""
                if not session_text:
                    await self.client.edit_message(event.chat_id, processing_msg.id, "❌ **Invalid Session**\n\nPlease provide a valid session string.")
                    return
                
                # Use AccountLoginService to login and store
                login_result = await self.account_login_service.login_and_store_account(
                    session_text, user.telegram_user_id, "auto"
                )
                
                if not login_result.get("success"):
                    error_msg = login_result.get("error", "Login failed")
                    await self.client.edit_message(event.chat_id, processing_msg.id, f"❌ **Account Login Failed**\n\n{error_msg}")
                    return
                
                account_id = login_result["account_id"]
                
                await self.client.edit_message(event.chat_id, processing_msg.id, "✅ **Session imported successfully!**\n\n🔍 Starting automated verification...")
                import asyncio
                asyncio.create_task(self.run_verification(account_id, event.chat_id))
            
            if state == "awaiting_phone_otp":
                phone_text = str(event.text).strip() if event.text else ""
                print(f"[SELLER] PHONE OTP FLOW - Phone: {phone_text}")
                logger.info(f"[SELLER] ===== PHONE OTP FLOW STARTED =====")
                logger.info(f"[SELLER] User: {user_id}")
                logger.info(f"[SELLER] Phone: {phone_text}")
                logger.info(f"[SELLER] Chat ID: {event.chat_id}")
                
                if not phone_text:
                    print(f"[SELLER] Invalid phone")
                    await self.send_message(event.chat_id, "❌ **Invalid Phone Number**\n\nPlease provide a valid phone number.")
                    return
                
                # Process the phone number
                print(f"[SELLER] Calling process_phone_number...")
                logger.info(f"[SELLER] Calling process_phone_number...")
                try:
                    # Create minimal user object for compatibility
                    class UserObj:
                        def __init__(self, uid):
                            self.telegram_user_id = uid
                    user = UserObj(user_id)
                    await self.process_phone_number(event, user, phone_text)
                    print(f"[SELLER] process_phone_number completed")
                    logger.info(f"[SELLER] ===== PHONE OTP FLOW COMPLETED =====")
                except Exception as phone_error:
                    print(f"[SELLER] ERROR: {phone_error}")
                    logger.error(f"[SELLER] Error in process_phone_number: {phone_error}")
                    import traceback
                    traceback.print_exc()
                    logger.error(traceback.format_exc())
                    await self.send_message(event.chat_id, f"❌ Error processing phone: {str(phone_error)}")
            
            elif state == "awaiting_otp_code":
                otp_text = str(event.text).strip() if event.text else ""
                # Remove spaces and any non-digit characters from OTP
                otp_clean = ''.join(filter(str.isdigit, otp_text))
                
                logger.info(f"[SELLER] Processing OTP code from {user_id}: '{otp_text}' -> '{otp_clean}'")
                if not otp_clean or len(otp_clean) < 4:
                    await self.send_message(event.chat_id, "❌ **Invalid OTP**\n\nPlease provide a valid OTP code (4-6 digits).")
                    return
                # Create minimal user object for compatibility
                class UserObj:
                    def __init__(self, uid):
                        self.telegram_user_id = uid
                user = UserObj(user_id)
                # Pass clean OTP (Telegram accepts both formats)
                await self.process_otp_code(event, user, otp_clean)
            
            elif state == "awaiting_2fa_password":
                password_text = str(event.text).strip() if event.text else ""
                logger.info(f"[SELLER] Processing 2FA password from {user_id}")
                if not password_text:
                    await self.send_message(event.chat_id, "❌ **Invalid Password**\n\nPlease provide a valid 2FA password.")
                    return
                # Create minimal user object for compatibility
                class UserObj:
                    def __init__(self, uid):
                        self.telegram_user_id = uid
                user = UserObj(user_id)
                await self.process_2fa_password(event, user, password_text)
            
            elif state.startswith("payout_"):
                method = state.split("_")[1]
                await self.db_connection.users.update_one({"telegram_user_id": user_id}, {"$unset": {"state": ""}})
                
                user_doc = await self.db_connection.users.find_one({"telegram_user_id": user_id})
                balance = user_doc.get("balance", 0.0) if user_doc else 0.0
                
                payout_details = str(event.text).strip() if event.text else ""
                if not payout_details:
                    await self.send_message(event.chat_id, "❌ **Invalid Details**\n\nPlease provide valid payment details.")
                    return
                
                transaction_data = {
                    "user_id": user_id,
                    "type": "payout",
                    "amount": balance,
                    "payment_method": method,
                    "status": "pending",
                    "payment_address": payout_details,
                    "created_at": utc_now()
                }
                
                await self.db_connection.transactions.insert_one(transaction_data)
                await self.send_message(event.chat_id, f"✅ **Payout Request Submitted**\n\n💰 **Amount:** ${balance:.2f}\n💳 **Method:** {method.upper()}\n📍 **Details:** {payout_details}\n\n⏳ **Status:** Pending admin approval", buttons=[[Button.inline("🔙 Back", "back_to_main")]])
            
        except Exception as e:
            logger.error(f"[SELLER] Text handler error for {event.sender_id}: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to process your input. Please try again.")
    
    async def handle_document(self, event):
        try:
            logger.info(f"[SELLER] Document received from user {event.sender_id}")
            user = await self.get_or_create_user(event)
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
            
            current_state = user_doc.get("state") if user_doc else None
            logger.info(f"[SELLER] User {user.telegram_user_id} current state: {current_state}")
            
            if not user_doc or user_doc.get("state") != "awaiting_upload":
                logger.info(f"[SELLER] Document received without awaiting_upload state - auto-setting state")
                # Auto-set the state and process the document
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$set": {"state": "awaiting_upload"}}
                )
            
            file_name = "unknown"
            if event.document.attributes:
                for attr in event.document.attributes:
                    if isinstance(attr, DocumentAttributeFilename):
                        file_name = attr.file_name
                        break
            
            # Check if it's a TData archive
            if file_name.lower().endswith(('.zip', '.rar', '.7z')) and 'tdata' in file_name.lower():
                temp_file = tempfile.mktemp(suffix='.zip')
                await event.download_media(temp_file)
                await self.handle_tdata_archive(event, user, temp_file)
                return
            
            temp_file = tempfile.mktemp(suffix=os.path.splitext(file_name)[1])
            await event.download_media(temp_file)
            
            await self.db_connection.users.update_one({"telegram_user_id": user.telegram_user_id}, {"$unset": {"state": ""}})
            processing_msg = await self.send_message(event.chat_id, "🔄 **Processing your session...**\n\nThis may take a few moments.")
            
            # Use AccountLoginService to login and store
            login_result = await self.account_login_service.login_and_store_account(
                temp_file, user.telegram_user_id, "auto"
            )
            os.unlink(temp_file)
            
            if not login_result.get("success"):
                error_msg = login_result.get("error", "Login failed")
                await self.client.edit_message(event.chat_id, processing_msg.id, f"❌ **Account Login Failed**\n\n{error_msg}")
                return
            
            account_id = login_result["account_id"]
            
            await self.client.edit_message(event.chat_id, processing_msg.id, "✅ **Session imported successfully!**\n\n🔍 Starting automated verification...")
            import asyncio
            asyncio.create_task(self.run_verification(account_id, event.chat_id))
            
        except Exception as e:
            logger.error(f"Document handler error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to process file. Please try again.")
    
    async def handle_tdata_archive(self, event, user, archive_path):
        """Handle TData archive upload"""
        try:
            import zipfile
            import tempfile
            import shutil
            
            processing_msg = await self.send_message(event.chat_id, "📦 **Processing TData Archive...**\n\nExtracting and converting...")
            
            # Create temp directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                extract_path = os.path.join(temp_dir, "tdata")
                
                # Extract archive
                if archive_path.lower().endswith('.zip'):
                    with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_path)
                else:
                    await self.client.edit_message(event.chat_id, processing_msg.id, "❌ **Unsupported Archive Format**\n\nOnly ZIP files are supported for TData.")
                    return
                
                # Look for tdata folder in extracted content
                tdata_path = None
                for root, dirs, files in os.walk(extract_path):
                    if 'key_datas' in files:
                        tdata_path = root
                        break
                
                if not tdata_path:
                    await self.client.edit_message(event.chat_id, processing_msg.id, "❌ **Invalid TData Archive**\n\nNo valid TData structure found in archive.")
                    return
                
                # Use AccountLoginService to login and store TData
                login_result = await self.account_login_service.login_and_store_account(
                    tdata_path, user.telegram_user_id, "tdata"
                )
                
                if not login_result.get("success"):
                    error_msg = login_result.get("error", "Login failed")
                    await self.client.edit_message(event.chat_id, processing_msg.id, f"❌ **TData Login Failed**\n\n{error_msg}")
                    return
                
                account_id = login_result["account_id"]
                
                await self.client.edit_message(event.chat_id, processing_msg.id, "✅ **TData imported successfully!**\n\n🔍 Starting automated verification...")
                import asyncio
                asyncio.create_task(self.run_verification(account_id, event.chat_id))
                
        except Exception as e:
            logger.error(f"TData archive handler error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to process TData archive. Please try again.")
    
    async def process_phone_number(self, event, user, phone_number):
        """Process phone number and send OTP - Simplified approach"""
        try:
            user_id = event.sender_id
            print(f"[SELLER] process_phone_number: {phone_number} for {user_id}")
            logger.info(f"[SELLER] Processing phone number {phone_number} for user {user_id}")
            
            # Validate phone number format
            if not phone_number.startswith('+') or len(phone_number) < 10:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Phone Number**\n\nPlease use international format with country code.\nExample: +1234567890"
                )
                return
            
            # Show processing message
            processing_msg = await self.send_message(
                event.chat_id,
                "📱 **Sending OTP...**\n\nPlease wait while we send the verification code to your phone."
            )
            
            # Clear state now
            await self.db_connection.users.update_one(
                {"telegram_user_id": user_id},
                {"$unset": {"state": ""}}
            )
            
            # Use shared OTP service instance
            print(f"[SELLER] Calling OTP service...")
            logger.info(f"[SELLER] Calling verify_account_ownership for {phone_number}")
            otp_result = await self.otp_service.verify_account_ownership(phone_number, user_id)
            print(f"[SELLER] OTP result: {otp_result.get('success')}")
            logger.info(f"[SELLER] OTP result: {otp_result}")
            
            if otp_result.get('success'):
                success_message = f"✅ **OTP Sent Successfully!**\n\n📱 **Phone:** {phone_number}\n⏰ **Expires in:** 5 minutes\n\nPlease enter the verification code you received:"
                
                # Set user state for OTP input BEFORE editing message
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user_id},
                    {"$set": {
                        "state": "awaiting_otp_code", 
                        "temp_phone": phone_number
                    }}
                )
                logger.info(f"[SELLER] State set to awaiting_otp_code for user {user_id}")
                
                await self.client.edit_message(
                    event.chat_id,
                    processing_msg.id,
                    success_message,
                    buttons=create_otp_verification_keyboard(user_id)
                )
                
            else:
                error_msg = otp_result.get('error', 'Unknown error occurred')
                await self.client.edit_message(
                    event.chat_id,
                    processing_msg.id,
                    f"❌ **Failed to Send OTP**\n\n{error_msg}\n\nPlease try again with a valid phone number."
                )
            
        except Exception as e:
            logger.error(f"[SELLER] Phone processing error for {event.sender_id}: {str(e)}")
            await self.send_message(event.chat_id, f"❌ **Phone Processing Failed**\n\n{str(e)}\n\nPlease try again or use session upload.")
    
    async def process_otp_code(self, event, user, otp_code):
        """Process OTP code and verify account - Simplified approach"""
        try:
            user_id = event.sender_id
            
            # Show processing message
            processing_msg = await self.send_message(
                event.chat_id,
                "🔍 **Verifying OTP...**\n\nPlease wait while we verify your code."
            )
            
            # Get phone number from user doc
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user_id})
            phone_number = user_doc.get("temp_phone") if user_doc else None
            
            if not phone_number:
                await self.client.edit_message(event.chat_id, processing_msg.id, "❌ **Session Expired**\n\nPhone number not found. Please start over.")
                return
            
            # Verify OTP using shared service
            verification_result = await self.otp_service.verify_otp_and_create_session(user_id, otp_code)
            
            if verification_result.get('success'):
                # Clear user state
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user_id},
                    {"$unset": {"state": "", "temp_phone": ""}}
                )
                
                # Create account record
                account_info = verification_result["account_info"]
                
                # Encrypt session before storing
                from app.utils.encryption import encrypt_data
                encrypted_session = encrypt_data(verification_result["session_string"])
                
                account_data = {
                    "seller_id": user_id,
                    "telegram_account_id": account_info.get("id"),
                    "username": account_info.get("username"),
                    "first_name": account_info.get("first_name"),
                    "last_name": account_info.get("last_name"),
                    "phone_number": account_info.get("phone"),
                    "session_string": encrypted_session,
                    "tfa_password": verification_result.get("tfa_password"),
                    "status": AccountStatus.PENDING,
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                    "obtained_via": "otp"
                }
                
                result = await self.db_connection.accounts.insert_one(account_data)
                account_id = str(result.inserted_id)
                
                success_msg = f"✅ **Account Added Successfully!**\n\n👤 **Username:** @{account_info.get('username', 'N/A')}\n📱 **Phone:** {account_info.get('phone', 'Hidden')}\n🎆 **Premium:** {'Yes' if account_info.get('premium') else 'No'}\n\n🔍 **Starting verification...**"
                
                await self.client.edit_message(event.chat_id, processing_msg.id, success_msg)
                
                # Start verification
                import asyncio
                asyncio.create_task(self.run_verification(account_id, event.chat_id))
                
            elif verification_result.get('requires_password'):
                tfa_msg = "🔐 **Two-Factor Authentication Required**\n\nYour account has 2FA enabled. Please enter your password:"
                await self.client.edit_message(event.chat_id, processing_msg.id, tfa_msg, buttons=[[Button.inline("❌ Cancel", "cancel_otp")]])
                
                # Set state for 2FA password
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user_id},
                    {"$set": {"state": "awaiting_2fa_password", "temp_otp_code": otp_code}}
                )
                return
                
            else:
                await self.client.edit_message(
                    event.chat_id,
                    processing_msg.id,
                    f"❌ **OTP Verification Failed**\n\n{verification_result.get('error', 'Unknown error')}\n\nPlease try again."
                )
            
        except Exception as e:
            logger.error(f"Process OTP code error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to verify OTP. Please try again.")
    
    async def process_2fa_password(self, event, user, password):
        """Process 2FA password - Simplified approach"""
        try:
            user_id = user.telegram_user_id
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user_id})
            temp_otp_code = user_doc.get("temp_otp_code")
            
            if not temp_otp_code:
                await self.send_message(event.chat_id, "❌ Session expired. Please start over.")
                return
            
            processing_msg = await self.send_message(event.chat_id, "🔐 **Verifying Password...**")
            
            # Get phone number from user doc
            phone_number = user_doc.get("temp_phone")
            if not phone_number:
                await self.client.edit_message(event.chat_id, processing_msg.id, "❌ **Session Expired**\n\nPhone number not found. Please start over.")
                return
            
            # Verify with password using shared service
            verification_result = await self.otp_service.verify_otp_and_create_session(user_id, temp_otp_code, password)
            
            if verification_result.get('success'):
                # Clear user state
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user_id},
                    {"$unset": {"state": "", "temp_phone": "", "temp_otp_code": ""}}
                )
                
                # Create account record
                account_info = verification_result["account_info"]
                
                # Encrypt session before storing
                from app.utils.encryption import encrypt_data
                encrypted_session = encrypt_data(verification_result["session_string"])
                
                account_data = {
                    "seller_id": user_id,
                    "telegram_account_id": account_info.get("id"),
                    "username": account_info.get("username"),
                    "first_name": account_info.get("first_name"),
                    "last_name": account_info.get("last_name"),
                    "phone_number": account_info.get("phone"),
                    "session_string": encrypted_session,
                    "tfa_password": password,
                    "status": AccountStatus.PENDING,
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                    "obtained_via": "otp"
                }
                
                result = await self.db_connection.accounts.insert_one(account_data)
                account_id = str(result.inserted_id)
                
                success_msg = f"✅ **Account Added with 2FA!**\n\n👤 **Username:** @{account_info.get('username', 'N/A')}\n📱 **Phone:** {account_info.get('phone', 'Hidden')}\n🔐 **2FA:** Enabled\n\n🔍 **Starting verification...**"
                
                await self.client.edit_message(event.chat_id, processing_msg.id, success_msg)
                
                # Start verification
                import asyncio
                asyncio.create_task(self.run_verification(account_id, event.chat_id))
                
            else:
                error_msg = f"❌ **Password Verification Failed**\n\n{verification_result.get('error', 'Unknown error')}"
                await self.client.edit_message(event.chat_id, processing_msg.id, error_msg)
            
        except Exception as e:
            logger.error(f"Process 2FA password error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to verify password. Please try again.")
    
    async def process_otp_account(self, event, user, verification_result, message_id):
        """Process account obtained via OTP"""
        try:
            # Use event.sender_id directly
            user_id = event.sender_id
            
            # Create account record
            account_info = verification_result.get("account_info")
            logger.info(f"Account info from verification: {account_info}")
            
            if not account_info:
                logger.error("No account_info in verification result")
                logger.error(f"Full verification result: {verification_result}")
                error_msg = "❌ **Account Processing Failed**\n\nFailed to retrieve account information. Please try again."
                if message_id:
                    await self.client.edit_message(event.chat_id, message_id, error_msg)
                else:
                    await self.send_message(event.chat_id, error_msg)
                return
            
            # Safely extract account info with defaults
            account_data = {
                "seller_id": user_id,
                "telegram_account_id": account_info.get("id") if account_info else None,
                "username": account_info.get("username") if account_info else None,
                "first_name": account_info.get("first_name") if account_info else None,
                "last_name": account_info.get("last_name") if account_info else None,
                "phone_number": account_info.get("phone") if account_info else None,
                "session_string": verification_result.get("session_string", ""),
                "tfa_password": verification_result.get("tfa_password"),  # Store 2FA password for buyer
                "status": AccountStatus.PENDING,
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "obtained_via": "otp"  # Mark as OTP-obtained
            }
            
            # Save account
            result = await self.db_connection.accounts.insert_one(account_data)
            account_id = str(result.inserted_id)
            
            # Update user upload count
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user_id})
            today = utc_now().date()
            
            if user_doc and user_doc.get("last_upload_date") and user_doc["last_upload_date"].date() == today:
                upload_count = user_doc.get("upload_count_today", 0) + 1
            else:
                upload_count = 1
            
            await self.db_connection.users.update_one(
                {"telegram_user_id": user_id},
                {
                    "$set": {
                        "upload_count_today": upload_count,
                        "last_upload_date": utc_now()
                    }
                }
            )
            
            # Update success message with safe access
            username = account_info.get('username', 'No username') if account_info else 'No username'
            phone = account_info.get('phone', 'Hidden') if account_info else 'Hidden'
            account_id_display = account_info.get('id', 'Unknown') if account_info else 'Unknown'
            
            success_msg = f"✅ **Account Verified Successfully!**\n\n👤 **Account:** {username}\n📱 **Phone:** {phone}\n🆔 **ID:** {account_id_display}\n\n🔍 **Starting automated verification...**\n\nThis will take 2-3 minutes to complete all security checks."
            
            if message_id:
                await self.client.edit_message(event.chat_id, message_id, success_msg)
            else:
                await self.send_message(event.chat_id, success_msg)
            
            # Start verification in background
            import asyncio
            asyncio.create_task(self.run_verification(account_id, event.chat_id))
            
        except Exception as e:
            logger.error(f"Process OTP account error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to process account. Please try again.")
    

    
    async def check_spam_status(self, session_string, chat_id):
        """Check spam status via @SpamBot and auto-submit appeal if needed"""
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            from app.utils.encryption import decrypt_data
            import asyncio
            
            # Decrypt session
            decrypted_session = decrypt_data(session_string)
            
            # Create client
            client = TelegramClient(StringSession(decrypted_session), self.api_id, self.api_hash)
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return {"status": "error", "message": "Session not authorized"}
            
            # Send /start to @SpamBot
            spam_bot = await client.get_entity("@SpamBot")
            await client.send_message(spam_bot, "/start")
            
            # Wait for response
            await asyncio.sleep(2)
            messages = await client.get_messages(spam_bot, limit=1)
            
            spam_result = {"status": "clean", "message": "No spam restrictions"}
            
            if messages:
                response = messages[0].message
                response_lower = response.lower()
                
                # Check if account has spam restrictions
                if "unfortunately" in response_lower and "anti-spam" in response_lower:
                    spam_result = {"status": "spam", "message": response}
                    await self.send_message(chat_id, "⚠️ **Account Limited**\n\nYour account has spam restrictions.")
                    
                    # Silently submit appeal in background
                    try:
                        # Click "Submit a complaint" button
                        await asyncio.sleep(1)
                        await messages[0].click(text="Submit a complaint")
                        
                        # Wait for confirmation message
                        await asyncio.sleep(2)
                        confirm_msgs = await client.get_messages(spam_bot, limit=1)
                        
                        if confirm_msgs and "never send this to strangers" in confirm_msgs[0].message.lower():
                            # Click "No, I'll never do any of this!" button
                            await asyncio.sleep(1)
                            await confirm_msgs[0].click(text="No, I'll never do any of this!")
                            
                            # Wait for appeal request message
                            await asyncio.sleep(2)
                            appeal_msgs = await client.get_messages(spam_bot, limit=1)
                            
                            if appeal_msgs and "write me some details" in appeal_msgs[0].message.lower():
                                # Send appeal message
                                await asyncio.sleep(1)
                                appeal_text = "I don't know. I think nothing went wrong. But I am unable to send any message to anyone."
                                await client.send_message(spam_bot, appeal_text)
                                spam_result["appeal_submitted"] = True
                                logger.info(f"Spam appeal submitted silently for account")
                    except Exception as appeal_error:
                        logger.error(f"Failed to submit appeal: {appeal_error}")
                
                elif "limited" in response_lower or "restricted" in response_lower or "spam" in response_lower:
                    spam_result = {"status": "spam", "message": response}
                    await self.send_message(chat_id, f"⚠️ **Spam Check Alert**\n\nYour account has spam restrictions:\n\n{response[:200]}")
                else:
                    await self.send_message(chat_id, "✅ **Spam Check Passed**\n\nYour account has no spam restrictions.")
            
            await client.disconnect()
            return spam_result
            
        except Exception as e:
            logger.error(f"Spam check error: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    async def run_verification(self, account_id, chat_id):
        try:
            from bson import ObjectId
            if isinstance(account_id, str):
                account_id = ObjectId(account_id)
            
            account_doc = await self.db_connection.accounts.find_one({"_id": account_id})
            if not account_doc:
                return
            
            await self.db_connection.accounts.update_one(
                {"_id": account_id},
                {"$set": {"status": AccountStatus.CHECKING, "updated_at": utc_now()}}
            )
            
            # Check spam status via @SpamBot first
            spam_status = await self.check_spam_status(account_doc["session_string"], chat_id)
            if spam_status:
                await self.db_connection.accounts.update_one(
                    {"_id": account_id},
                    {"$set": {"spam_check_result": spam_status, "updated_at": utc_now()}}
                )
            
            verification_result = await self.verification_service.verify_account(account_doc)
            
            update_data = {
                "checks": verification_result["checks"],
                "verification_logs": verification_result["logs"],
                "updated_at": utc_now()
            }
            
            if verification_result["overall_status"] == "passed":
                update_data["status"] = AccountStatus.APPROVED
                result_message = "✅ **Verification Completed Successfully!**\n\nYour account passed all automated checks."
            elif verification_result["overall_status"] == "failed":
                update_data["status"] = AccountStatus.REJECTED
                result_message = "❌ **Verification Failed**\n\nYour account did not pass the automated checks."
            else:
                update_data["status"] = AccountStatus.PENDING
                result_message = "⚠️ **Manual Review Required**\n\nYour account needs manual admin review."
            
            await self.db_connection.accounts.update_one({"_id": account_id}, {"$set": update_data})
            await self.send_message(chat_id, result_message)
            
        except Exception as e:
            logger.error(f"Verification error: {str(e)}")
            await self.send_message(chat_id, "❌ **Verification Error**\n\nAn error occurred during verification.")
    
    async def handle_upload_account(self, event, user):
        """Handle upload account"""
        try:
            await self.edit_message(
                event, 
                "📤 **Upload Account**\n\nPlease send:\n• Session file (.session)\n• Session string (text)\n• TData archive (.zip)\n\nSupported formats: Telethon, Pyrogram, TData", 
                [[Button.inline("🔙 Back", "back_to_main")]]
            )
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id}, 
                {"$set": {"state": "awaiting_upload"}}
            )
            
        except Exception as e:
            logger.error(f"Upload account handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_seller_stats(self, event, user):
        """Handle seller stats"""
        try:
            total_accounts = await self.db_connection.accounts.count_documents({"seller_id": user.telegram_user_id})
            approved_accounts = await self.db_connection.accounts.count_documents({"seller_id": user.telegram_user_id, "status": "approved"})
            sold_accounts = await self.db_connection.accounts.count_documents({"seller_id": user.telegram_user_id, "status": "sold"})
            
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
            balance = user_doc.get("balance", 0.0) if user_doc else 0.0
            
            stats_message = f"""📊 **Your Seller Statistics**

📤 **Total Uploaded:** {total_accounts}
✅ **Approved:** {approved_accounts}
💰 **Sold:** {sold_accounts}
💵 **Current Balance:** ${balance:.2f}

📈 **Success Rate:** {(approved_accounts/total_accounts*100) if total_accounts > 0 else 0:.1f}%
💎 **Conversion Rate:** {(sold_accounts/approved_accounts*100) if approved_accounts > 0 else 0:.1f}%"""
            
            await self.edit_message(event, stats_message, [[Button.inline("🔙 Back", "back_to_main")]])
            
        except Exception as e:
            logger.error(f"Seller stats handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_my_rating(self, event, user):
        """Handle my rating"""
        try:
            total_accounts = await self.db_connection.accounts.count_documents({"seller_id": user.telegram_user_id})
            approved_accounts = await self.db_connection.accounts.count_documents({"seller_id": user.telegram_user_id, "status": "approved"})
            sold_accounts = await self.db_connection.accounts.count_documents({"seller_id": user.telegram_user_id, "status": "sold"})
            
            if total_accounts == 0:
                rating = 0.0
                rating_text = "No Rating"
            else:
                success_rate = approved_accounts / total_accounts
                conversion_rate = sold_accounts / approved_accounts if approved_accounts > 0 else 0
                rating = (success_rate * 0.7 + conversion_rate * 0.3) * 5
                rating_text = f"{rating:.1f}/5.0 ⭐"
            
            rating_message = f"""⭐ **Your Seller Rating**

🌟 **Current Rating:** {rating_text}

**Rating Factors:**
• Account approval rate: {(approved_accounts/total_accounts*100) if total_accounts > 0 else 0:.1f}%
• Sales conversion rate: {(sold_accounts/approved_accounts*100) if approved_accounts > 0 else 0:.1f}%
• Account quality scores
• Customer feedback

**Tips to Improve:**
• Upload high-quality accounts
• Ensure accounts have clean history
• Provide accurate information
• Maintain good account standards"""
            
            await self.edit_message(event, rating_message, [[Button.inline("🔙 Back", "back_to_main")]])
            
        except Exception as e:
            logger.error(f"My rating handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_help(self, event):
        """Handle help"""
        try:
            help_message = """❓ **Help & Support**

**How to Sell Accounts:**
1. Click 'Upload Account' or 'Sell via OTP'
2. Provide session file/string or phone number
3. Complete verification process
4. Wait for admin approval
5. Get paid when account sells!

**Upload Methods:**
📤 **Session Upload**: Upload .session files or session strings
📱 **Phone + OTP**: Verify ownership via phone number

**Account Requirements:**
✅ Must be your own account
✅ Clean history (no spam/bans)
✅ Active and accessible
✅ No illegal activity

**Payment:**
💰 Earnings added to your balance
💸 Request payout via UPI or Crypto
⏰ Payouts processed within 24 hours

**Need More Help?**
Contact our support team for assistance."""
            
            await self.edit_message(event, help_message, [[Button.inline("🔙 Back", "back_to_main")]])
            
        except Exception as e:
            logger.error(f"Help handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
