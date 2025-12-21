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
            
            # DEBUG: Check temp_phone BEFORE get_or_create_user
            user_check = await self.db_connection.users.find_one({"telegram_user_id": event.sender_id})
            print(f"[SELLER] CALLBACK START - temp_phone in DB: {user_check.get('temp_phone') if user_check else 'NO USER'}")
            
            user = await self.get_or_create_user(event)
            
            # DEBUG: Check temp_phone AFTER get_or_create_user
            user_check2 = await self.db_connection.users.find_one({"telegram_user_id": event.sender_id})
            print(f"[SELLER] AFTER get_or_create_user - temp_phone in DB: {user_check2.get('temp_phone') if user_check2 else 'NO USER'}")
            
            if data == "upload_account":
                await self.handle_upload_account(event, user)
            elif data.startswith("country_"):
                country = data.split("_", 1)[1]
                await self.handle_country_selected(event, user, country)
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
            elif data.startswith("add_proxy_"):
                parts = data.split("_")
                logger.info(f"[SELLER] add_proxy callback - parts: {parts}")
                if len(parts) >= 3:
                    if parts[2] == "upload":
                        country = parts[3] if len(parts) > 3 else "OTHER"
                        await self.handle_add_proxy_upload(event, user, country)
                    elif parts[2] == "otp":
                        country = parts[3] if len(parts) > 3 else "OTHER"
                        logger.info(f"[SELLER] Calling handle_add_proxy_otp for country={country}")
                        await self.handle_add_proxy_otp(event, user, country)
                    else:
                        account_id = parts[2]
                        await self.handle_add_proxy(event, user, account_id)
            elif data.startswith("skip_proxy_"):
                parts = data.split("_")
                if len(parts) >= 3:
                    if parts[2] == "upload":
                        country = parts[3] if len(parts) > 3 else "OTHER"
                        await self.handle_skip_proxy_upload(event, user, country)
                    elif parts[2] == "otp":
                        country = parts[3] if len(parts) > 3 else "OTHER"
                        await self.handle_skip_proxy_otp(event, user, country)
                    else:
                        account_id = parts[2]
                        await self.handle_skip_proxy_confirm(event, user, account_id)
            elif data.startswith("skip_confirm_"):
                parts = data.split("_")
                if len(parts) >= 3:
                    if parts[2] == "upload":
                        country = parts[3] if len(parts) > 3 else "OTHER"
                        await self.handle_skip_confirm_upload(event, user, country)
                    elif parts[2] == "otp":
                        country = parts[3] if len(parts) > 3 else "OTHER"
                        await self.handle_skip_confirm_otp(event, user, country)
                    else:
                        account_id = parts[2]
                        await self.handle_skip_proxy_final(event, user, account_id)
            elif data.startswith("skip_cancel_"):
                account_id = data.split("_", 2)[2]
                await self.show_proxy_prompt(event.chat_id, user.telegram_user_id, account_id)
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
            
            # Show OTP flow directly - no need for method selection
            otp_message = """
📱 **Sell Account via Phone + OTP**

**Process:**
1. Enter your account's phone number
2. Receive OTP on your phone
3. Enter OTP to verify ownership
4. Automated verification checks
5. Admin review and approval
6. Account listed for sale

**Requirements:**
✅ Active Telegram account
✅ Access to phone number
✅ Ability to receive SMS/calls

Ready to start?
            """
            
            buttons = [
                [Button.inline("📱 Continue with Phone + OTP", "use_phone_otp")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
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
• +1234567890 (US)
• +91987654321 (India)
• +447123456789 (UK)

**Important:**
• Use international format with country code
• This must be the phone number of your Telegram account
• You will receive an OTP on this number

Send your phone number:
            """
            
            # Use in-memory pending_actions
            if not hasattr(self, 'pending_actions'):
                self.pending_actions = {}
            
            self.pending_actions[user_id] = {
                "action": "awaiting_phone_for_proxy"
            }
            
            logger.info(f"[SELLER] Set pending_actions for {user_id}: awaiting_phone_for_proxy")
            
            await self.edit_message(
                event,
                phone_message,
                [[Button.inline("🔙 Cancel", "cancel_otp")]]
            )
            
        except Exception as e:
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
            
            logger.info(f"[SELLER] Checking pending_actions for {user_id}: {pending_action}")
            
            if pending_action and pending_action.get("action") == "awaiting_phone_for_proxy":
                phone_text = str(event.text).strip()
                self.pending_actions.pop(user_id, None)
                
                class UserObj:
                    def __init__(self, uid):
                        self.telegram_user_id = uid
                user = UserObj(user_id)
                
                await self.handle_phone_for_proxy(event, user, phone_text)
                return
            
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
                
                # Show proxy prompt before verification
                await self.client.edit_message(event.chat_id, processing_msg.id, "✅ **Session imported successfully!**")
                await self.show_proxy_prompt(event.chat_id, user.telegram_user_id, account_id)
            
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
            
            elif state.startswith("awaiting_proxy_"):
                parts = state.split("_")
                if len(parts) >= 3:
                    flow_type = parts[2]  # "upload" or "otp"
                    country = parts[3] if len(parts) > 3 else "OTHER"
                    proxy_text = str(event.text).strip() if event.text else ""
                    await self.process_proxy_before_account(event, user_id, flow_type, country, proxy_text)
            
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
            
            await self.client.edit_message(event.chat_id, processing_msg.id, "✅ **Session imported successfully!**")
            
            # Start verification directly
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
                
                await self.client.edit_message(event.chat_id, processing_msg.id, "✅ **TData imported successfully!**")
                
                # Start verification directly
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
            
            # Get seller proxy if available
            seller_proxy = None
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user_id})
            
            # Only use proxy if not skipped
            if user_doc and not user_doc.get("skip_proxy") and user_doc.get("temp_proxy_host"):
                # Get proxy from seller_proxies collection
                from app.models import SellerProxyManager
                proxy_manager = SellerProxyManager(self.db_connection)
                proxy_doc = await self.db_connection.seller_proxies.find_one({
                    "seller_id": user_id,
                    "proxy_host": user_doc["temp_proxy_host"]
                })
                if proxy_doc:
                    seller_proxy = {
                        "proxy_type": proxy_doc["proxy_type"],
                        "addr": proxy_doc["proxy_host"],
                        "port": proxy_doc["proxy_port"],
                        "username": proxy_doc.get("proxy_username"),
                        "password": proxy_doc.get("proxy_password")
                    }
                    logger.info(f"[SELLER] Using seller proxy: {seller_proxy['addr']}:{seller_proxy['port']}")
            
            # Use shared OTP service instance with seller proxy
            print(f"[SELLER] Calling OTP service with proxy={seller_proxy}...")
            logger.info(f"[SELLER] Calling verify_account_ownership for {phone_number} with proxy={seller_proxy}")
            otp_result = await self.otp_service.verify_account_ownership(phone_number, user_id, seller_proxy)
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
                
                success_msg = f"✅ **Account Added Successfully!**\n\n👤 **Username:** @{account_info.get('username', 'N/A')}\n📱 **Phone:** {account_info.get('phone', 'Hidden')}\n🎆 **Premium:** {'Yes' if account_info.get('premium') else 'No'}"
                
                await self.client.edit_message(event.chat_id, processing_msg.id, success_msg)
                
                # Start verification directly
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
                
                success_msg = f"✅ **Account Added with 2FA!**\n\n👤 **Username:** @{account_info.get('username', 'N/A')}\n📱 **Phone:** {account_info.get('phone', 'Hidden')}\n🔐 **2FA:** Enabled"
                
                await self.client.edit_message(event.chat_id, processing_msg.id, success_msg)
                
                # Start verification directly
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
    
    async def check_account_frozen(self, session_string, chat_id):
        """Check if account is frozen by trying to send a message"""
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            from telethon.errors import UserDeactivatedError, AuthKeyUnregisteredError
            from app.utils.encryption import decrypt_data
            import asyncio
            
            decrypted_session = decrypt_data(session_string)
            client = TelegramClient(StringSession(decrypted_session), self.api_id, self.api_hash)
            
            try:
                await client.connect()
                
                if not await client.is_user_authorized():
                    await client.disconnect()
                    return {"is_frozen": True, "reason": "Not authorized"}
                
                # Try to get own info
                me = await client.get_me()
                
                # Try to send message to Saved Messages
                try:
                    await client.send_message('me', 'Test')
                    await asyncio.sleep(1)
                    # Delete test message
                    messages = await client.get_messages('me', limit=1)
                    if messages:
                        await messages[0].delete()
                    
                    await client.disconnect()
                    return {"is_frozen": False, "reason": "Account is active"}
                    
                except Exception as send_error:
                    await client.disconnect()
                    return {"is_frozen": True, "reason": f"Cannot send messages: {str(send_error)}"}
                    
            except (UserDeactivatedError, AuthKeyUnregisteredError) as e:
                await client.disconnect()
                return {"is_frozen": True, "reason": "Account deactivated or banned"}
                
        except Exception as e:
            logger.error(f"Frozen check error: {str(e)}")
            return {"is_frozen": False, "reason": f"Check failed: {str(e)}"}
    
    async def run_verification(self, account_id, chat_id):
        """Run automated verification checks and send to admin for manual review"""
        try:
            from bson import ObjectId
            if isinstance(account_id, str):
                account_id = ObjectId(account_id)
            
            account_doc = await self.db_connection.accounts.find_one({"_id": account_id})
            if not account_doc:
                return
            
            # Update status to checking
            await self.db_connection.accounts.update_one(
                {"_id": account_id},
                {"$set": {"status": AccountStatus.CHECKING, "updated_at": utc_now()}}
            )
            
            await self.send_message(chat_id, "🔍 **Running Automated Checks...**\n\n1️⃣ Checking if account is frozen\n2️⃣ Spam check via @SpamBot\n3️⃣ Quality score analysis\n4️⃣ Security verification")
            
            # 1. Check if account is frozen FIRST
            frozen_check = await self.check_account_frozen(account_doc["session_string"], chat_id)
            
            if frozen_check.get("is_frozen"):
                # Account is frozen - reject immediately
                await self.db_connection.accounts.update_one(
                    {"_id": account_id},
                    {"$set": {
                        "status": AccountStatus.REJECTED,
                        "rejection_reason": "Account is frozen",
                        "frozen_check_result": frozen_check,
                        "updated_at": utc_now()
                    }}
                )
                
                await self.send_message(
                    chat_id,
                    "❌ **Account Rejected - Frozen**\n\n"
                    "Your account is frozen and cannot be sold.\n\n"
                    "⚠️ No payment will be made for frozen accounts."
                )
                return
            
            await self.send_message(chat_id, "✅ Account is active (not frozen)")
            
            # 2. Check spam status via @SpamBot
            spam_status = await self.check_spam_status(account_doc["session_string"], chat_id)
            if spam_status:
                await self.db_connection.accounts.update_one(
                    {"_id": account_id},
                    {"$set": {"spam_check_result": spam_status, "updated_at": utc_now()}}
                )
            
            # 3. Run full verification (30+ checks)
            verification_result = await self.verification_service.verify_account(account_doc)
            
            # Save verification results
            await self.db_connection.accounts.update_one(
                {"_id": account_id},
                {"$set": {
                    "checks": verification_result.get("checks", {}),
                    "verification_logs": verification_result.get("logs", []),
                    "frozen_check_result": frozen_check,
                    "status": AccountStatus.PENDING,  # Always pending for admin review
                    "updated_at": utc_now()
                }}
            )
            
            # Calculate quality score
            checks = verification_result.get("checks", {})
            quality_score = 0
            
            if checks.get("profile_completeness", {}).get("passed"):
                quality_score += 30
            if checks.get("account_age", {}).get("passed"):
                quality_score += 20
            if checks.get("spam_status", {}).get("passed"):
                quality_score += 25
            if checks.get("activity_patterns", {}).get("passed"):
                quality_score += 15
            if checks.get("two_factor_auth", {}).get("passed"):
                quality_score += 10
            
            # Show results to seller
            result_message = f"✅ **Automated Checks Complete!**\n\n"
            result_message += f"🔓 **Frozen Status:** Not Frozen\n"
            result_message += f"📊 **Quality Score:** {quality_score}/100\n"
            result_message += f"🔍 **Verification Score:** {verification_result.get('score_percentage', 0):.1f}%\n"
            result_message += f"🚫 **Spam Status:** {'Clean' if spam_status.get('status') == 'clean' else 'Limited'}\n\n"
            result_message += f"⏳ **Status:** Pending admin review\n\n"
            result_message += f"Your account has been sent to admin for manual verification. You'll be notified once approved!"
            
            await self.send_message(chat_id, result_message)
            
            # Notify admin about new account for review
            await self.notify_admin_new_account(account_id, account_doc, quality_score, verification_result)
            
        except Exception as e:
            logger.error(f"Verification error: {str(e)}")
            await self.send_message(chat_id, "❌ **Verification Error**\n\nAn error occurred during verification.")
    
    async def handle_upload_account(self, event, user):
        """Handle upload account"""
        try:
            # Ask for country first
            message = """
🌍 **Select Account Country**

Which country is this account from?
This helps us match the right proxy.

**Common Countries:**
            """
            
            buttons = [
                [Button.inline("🇮🇳 India", "country_IN"), Button.inline("🇺🇸 USA", "country_US")],
                [Button.inline("🇬🇧 UK", "country_GB"), Button.inline("🇨🇦 Canada", "country_CA")],
                [Button.inline("🇦🇺 Australia", "country_AU"), Button.inline("🇩🇪 Germany", "country_DE")],
                [Button.inline("🌐 Other", "country_OTHER")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, message, buttons)
            
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

    
    async def show_proxy_prompt(self, chat_id, seller_id, account_id):
        """Show proxy prompt to seller"""
        try:
            from app.models import SellerProxyManager
            proxy_manager = SellerProxyManager(self.db_connection)
            
            # Check if seller needs new proxy
            needs_proxy = await proxy_manager.needs_new_proxy(seller_id)
            
            if needs_proxy:
                message = """
⚠️ **IMPORTANT: Proxy Required**

To protect your account from being frozen, you need to add a proxy.

**Why Proxy?**
• Prevents account freezing
• Protects your privacy
• Required for verification

**Supported Types:**
• SOCKS5 (recommended)
• SOCKS4
• HTTP

⚠️ **Note:** MTProto proxies are NOT supported (Telethon limitation)

**1 proxy per 10 accounts**
You need to add a proxy now.

❌ **WARNING:** If you skip and your account gets frozen, NO MONEY will be added to your balance!
                """
            else:
                message = """
✅ **Proxy Available**

You have an available proxy slot.

Would you like to add a new proxy or use existing?
                """
            
            buttons = [
                [Button.inline("➕ Add Proxy", f"add_proxy_{account_id}")],
                [Button.inline("⏭️ Skip Proxy", f"skip_proxy_{account_id}")]
            ]
            
            await self.send_message(chat_id, message, buttons)
            
        except Exception as e:
            logger.error(f"Show proxy prompt error: {e}")
            # Continue with verification if error
            import asyncio
            asyncio.create_task(self.run_verification(account_id, chat_id))
    
    async def handle_add_proxy(self, event, user, account_id):
        """Handle add proxy"""
        try:
            message = """
🌐 **Add Proxy Configuration**

Send proxy in format:
`type://host:port`
or
`type://username:password@host:port`

**Examples:**
`socks5://proxy.example.com:1080`
`socks5://user:pass@proxy.example.com:1080`
`http://proxy.example.com:8080`

**Supported:** SOCKS5, SOCKS4, HTTP
❌ **NOT Supported:** MTProto (Telethon limitation)

Send your proxy configuration:
            """
            
            await self.edit_message(event, message, [[Button.inline("❌ Cancel", f"skip_proxy_{account_id}")]])
            
            # Set state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"state": f"awaiting_proxy_{account_id}"}}
            )
            
        except Exception as e:
            logger.error(f"Handle add proxy error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)
    
    async def handle_skip_proxy_confirm(self, event, user, account_id):
        """Show skip confirmation"""
        try:
            message = """
⚠️ **WARNING: Skip Proxy?**

Are you sure you want to skip adding a proxy?

**Risks:**
❌ Account may get frozen
❌ Verification may fail
❌ NO MONEY if account frozen

**If frozen:**
• Your account will be rejected
• No payment will be made
• You lose the account

Do you really want to skip?
            """
            
            buttons = [
                [Button.inline("✅ Yes, Skip", f"skip_confirm_{account_id}")],
                [Button.inline("❌ No, Add Proxy", f"add_proxy_{account_id}")]
            ]
            
            await self.edit_message(event, message, buttons)
            
        except Exception as e:
            logger.error(f"Skip proxy confirm error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)
    
    async def handle_skip_proxy_final(self, event, user, account_id):
        """Handle final skip"""
        try:
            await self.edit_message(event, "⚠️ **Proxy Skipped**\n\n🔍 Starting verification without proxy...\n\n⚠️ Remember: No payment if account gets frozen!")
            
            # Start verification
            import asyncio
            asyncio.create_task(self.run_verification(account_id, event.chat_id))
            
        except Exception as e:
            logger.error(f"Skip proxy final error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)

    
    async def process_proxy_config(self, event, seller_id, account_id, proxy_text):
        """Process proxy configuration"""
        try:
            import re
            from app.models import SellerProxy, SellerProxyManager
            
            # Clear state
            await self.db_connection.users.update_one(
                {"telegram_user_id": seller_id},
                {"$unset": {"state": ""}}
            )
            
            # Parse proxy
            match = re.match(r'(socks5|socks4|http)://(?:([^:]+):([^@]+)@)?([^:]+):(\d+)', proxy_text)
            
            if not match:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Proxy Format**\n\nPlease use format:\n`type://host:port`\nor\n`type://user:pass@host:port`"
                )
                return
            
            proxy_type, username, password, host, port = match.groups()
            
            # Create proxy
            proxy = SellerProxy(
                seller_id=seller_id,
                proxy_type=proxy_type,
                proxy_host=host,
                proxy_port=int(port),
                proxy_username=username,
                proxy_password=password,
                accounts_count=1,
                max_accounts=10
            )
            
            # Save proxy
            proxy_manager = SellerProxyManager(self.db_connection)
            await proxy_manager.add_proxy(seller_id, proxy)
            
            # Link account to proxy
            from bson import ObjectId
            await self.db_connection.accounts.update_one(
                {"_id": ObjectId(account_id)},
                {"$set": {"proxy_host": host, "uses_proxy": True}}
            )
            
            await self.send_message(
                event.chat_id,
                f"✅ **Proxy Added Successfully!**\n\n"
                f"Type: {proxy_type.upper()}\n"
                f"Host: {host}:{port}\n"
                f"Capacity: 1/10 accounts\n\n"
                f"🔍 Starting verification with proxy..."
            )
            
            # Start verification
            import asyncio
            asyncio.create_task(self.run_verification(account_id, event.chat_id))
            
        except Exception as e:
            logger.error(f"Process proxy config error: {e}")
            await self.send_message(event.chat_id, f"❌ Error: {str(e)}")

    
    async def handle_country_selected(self, event, user, country):
        """Handle country selection for upload"""
        try:
            # Store country temporarily
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"temp_country": country}}
            )
            
            # Show proxy prompt
            await self.show_proxy_prompt_before_upload(event, user, country)
            
        except Exception as e:
            logger.error(f"Country selected error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)
    
    async def show_proxy_prompt_before_upload(self, event, user, country):
        """Show proxy prompt before upload"""
        try:
            from app.models import SellerProxyManager
            proxy_manager = SellerProxyManager(self.db_connection)
            
            country_names = {
                "IN": "🇮🇳 India",
                "US": "🇺🇸 USA", 
                "GB": "🇬🇧 UK",
                "CA": "🇨🇦 Canada",
                "AU": "🇦🇺 Australia",
                "DE": "🇩🇪 Germany",
                "OTHER": "🌐 Other"
            }
            
            country_name = country_names.get(country, country)
            
            message = f"""
⚠️ **PROXY REQUIRED FOR {country_name} ACCOUNT**

You're adding a {country_name} account.
**You need a {country_name} proxy!**

**Why Proxy?**
• Prevents account freezing
• Matches account location
• Required for verification

**Supported Types:**
• SOCKS5 (recommended)
• SOCKS4  
• HTTP

❌ **MTProto NOT supported**

**1 proxy per 10 accounts**

⚠️ **WARNING:** If you skip and account gets frozen, NO MONEY will be added!

Add {country_name} proxy now:
            """
            
            buttons = [
                [Button.inline(f"➕ Add {country_name} Proxy", f"add_proxy_upload_{country}")],
                [Button.inline("⏭️ Skip (Risky)", f"skip_proxy_upload_{country}")]
            ]
            
            await self.edit_message(event, message, buttons)
            
        except Exception as e:
            logger.error(f"Show proxy prompt before upload error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)
    
    async def handle_phone_for_proxy(self, event, user, phone_number):
        """Handle phone number and detect country for proxy"""
        try:
            print(f"[SELLER] handle_phone_for_proxy called - phone={phone_number}, user={user.telegram_user_id}")
            logger.info(f"[SELLER] handle_phone_for_proxy called with phone={phone_number}, user={user.telegram_user_id}")
            
            # Detect country from phone
            country = self.detect_country_from_phone(phone_number)
            print(f"[SELLER] Detected country: {country}")
            
            # Store phone and country FIRST
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"temp_phone": phone_number, "temp_country": country}}
            )
            
            print(f"[SELLER] Saved to DB: temp_phone={phone_number}, temp_country={country}")
            logger.info(f"[SELLER] Saved temp_phone={phone_number}, temp_country={country} for user {user.telegram_user_id}")
            
            country_names = {
                "IN": "🇮🇳 India",
                "US": "🇺🇸 USA",
                "GB": "🇬🇧 UK", 
                "CA": "🇨🇦 Canada",
                "AU": "🇦🇺 Australia",
                "DE": "🇩🇪 Germany"
            }
            
            country_name = country_names.get(country, f"🌐 {country}")
            
            message = f"""
⚠️ **PROXY REQUIRED FOR {country_name} ACCOUNT**

Detected: {country_name} account
Phone: {phone_number}

**You need a {country_name} proxy!**

**Why Proxy?**
• Prevents account freezing
• Matches account location  
• Required for verification

**Supported:** SOCKS5, SOCKS4, HTTP
❌ **NOT Supported:** MTProto

⚠️ **WARNING:** Skip = No payment if frozen!

Add {country_name} proxy now:
            """
            
            buttons = [
                [Button.inline(f"➕ Add {country_name} Proxy", f"add_proxy_otp_{country}")],
                [Button.inline("⏭️ Skip (Risky)", f"skip_proxy_otp_{country}")]
            ]
            
            await self.send_message(event.chat_id, message, buttons)
            
            # Debug: Check if temp_phone is still in DB after sending message
            user_check = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
            print(f"[SELLER] After send_message, temp_phone in DB: {user_check.get('temp_phone') if user_check else 'NO USER'}")
            
        except Exception as e:
            logger.error(f"Handle phone for proxy error: {e}")
            await self.send_message(event.chat_id, f"❌ Error: {str(e)}")
    
    def detect_country_from_phone(self, phone):
        """Detect country from phone number"""
        phone = phone.strip().replace("+", "")
        
        # Country code mapping
        if phone.startswith("91"): return "IN"
        elif phone.startswith("1"): return "US"
        elif phone.startswith("44"): return "GB"
        elif phone.startswith("61"): return "AU"
        elif phone.startswith("49"): return "DE"
        elif phone.startswith("33"): return "FR"
        elif phone.startswith("39"): return "IT"
        elif phone.startswith("34"): return "ES"
        elif phone.startswith("7"): return "RU"
        elif phone.startswith("86"): return "CN"
        elif phone.startswith("81"): return "JP"
        elif phone.startswith("82"): return "KR"
        elif phone.startswith("55"): return "BR"
        elif phone.startswith("52"): return "MX"
        elif phone.startswith("27"): return "ZA"
        else: return "OTHER"

    
    async def handle_add_proxy_upload(self, event, user, country):
        """Handle add proxy for upload flow"""
        try:
            country_names = {"IN": "Indian", "US": "US", "GB": "UK", "CA": "Canadian", "AU": "Australian", "DE": "German", "OTHER": ""}
            country_name = country_names.get(country, "")
            
            message = f"""
🌐 **Add {country_name} Proxy**

Supported formats:
• `socks5://host:port`
• `socks5://user:pass@host:port`
• `tg://socks?server=host&port=1080`
• `t.me/socks?server=host&port=1080`

Supported: SOCKS5, SOCKS4, HTTP
❌ NOT: MTProto

Send your {country_name} proxy:
            """
            
            await self.edit_message(event, message, [[Button.inline("❌ Cancel", "back_to_main")]])
            
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"state": f"awaiting_proxy_upload_{country}"}}
            )
            
        except Exception as e:
            logger.error(f"Add proxy upload error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)
    
    async def handle_add_proxy_otp(self, event, user, country):
        """Handle add proxy for OTP flow"""
        try:
            print(f"[SELLER] handle_add_proxy_otp called for country={country}, user={user.telegram_user_id}")
            
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
            temp_phone = user_doc.get("temp_phone") if user_doc else None
            print(f"[SELLER] temp_phone in DB: {temp_phone}")
            logger.info(f"[SELLER] handle_add_proxy_otp - temp_phone before: {temp_phone}")
            
            country_names = {"IN": "Indian", "US": "US", "GB": "UK", "CA": "Canadian", "AU": "Australian", "DE": "German", "OTHER": ""}
            country_name = country_names.get(country, "")
            
            message = f"""
🌐 **Add {country_name} Proxy**

Supported formats:
• `socks5://host:port`
• `socks5://user:pass@host:port`
• `tg://socks?server=host&port=1080`
• `t.me/socks?server=host&port=1080`

Supported: SOCKS5, SOCKS4, HTTP
❌ NOT: MTProto

Send your {country_name} proxy:
            """
            
            await self.edit_message(event, message, [[Button.inline("❌ Cancel", "back_to_main")]])
            
            update_data = {"state": f"awaiting_proxy_otp_{country}"}
            if temp_phone:
                update_data["temp_phone"] = temp_phone
                logger.info(f"[SELLER] Preserving temp_phone: {temp_phone}")
            
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": update_data}
            )
            
            logger.info(f"[SELLER] State set to awaiting_proxy_otp_{country} with temp_phone={temp_phone}")
            
        except Exception as e:
            logger.error(f"Add proxy OTP error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)
    
    async def handle_skip_proxy_upload(self, event, user, country):
        """Handle skip proxy for upload"""
        try:
            message = """
⚠️ **WARNING: Skip Proxy?**

**Risks:**
❌ Account may get frozen
❌ Verification may fail
❌ NO MONEY if account frozen

Do you really want to skip?
            """
            
            buttons = [
                [Button.inline("✅ Yes, Skip", f"skip_confirm_upload_{country}")],
                [Button.inline("❌ No, Add Proxy", f"add_proxy_upload_{country}")]
            ]
            
            await self.edit_message(event, message, buttons)
            
        except Exception as e:
            logger.error(f"Skip proxy upload error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)
    
    async def handle_skip_proxy_otp(self, event, user, country):
        """Handle skip proxy for OTP"""
        try:
            print(f"[SELLER] handle_skip_proxy_otp called for country={country}")
            
            # Check temp_phone before doing anything
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
            print(f"[SELLER] temp_phone before skip: {user_doc.get('temp_phone') if user_doc else 'NO USER'}")
            message = """
⚠️ **WARNING: Skip Proxy?**

**Risks:**
❌ Account may get frozen
❌ Verification may fail  
❌ NO MONEY if account frozen

Do you really want to skip?
            """
            
            buttons = [
                [Button.inline("✅ Yes, Skip", f"skip_confirm_otp_{country}")],
                [Button.inline("❌ No, Add Proxy", f"add_proxy_otp_{country}")]
            ]
            
            await self.edit_message(event, message, buttons)
            
        except Exception as e:
            logger.error(f"Skip proxy OTP error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)

    
    async def handle_skip_confirm_upload(self, event, user, country):
        """Handle skip confirmation for upload"""
        try:
            await self.edit_message(event, "⚠️ **Proxy Skipped**\n\n📤 Now send your session file/string:")
            
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"state": "awaiting_upload", "skip_proxy": True}}
            )
            
        except Exception as e:
            logger.error(f"Skip confirm upload error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)
    
    async def handle_skip_confirm_otp(self, event, user, country):
        """Handle skip confirmation for OTP"""
        try:
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
            phone = user_doc.get("temp_phone") if user_doc else None
            
            if not phone:
                await self.edit_message(event, "❌ Session expired. Please start over.")
                return
            
            await self.edit_message(event, "⚠️ **Proxy Skipped**\n\n📱 Sending OTP...")
            
            # Mark as skipped and continue with OTP
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"skip_proxy": True}, "$unset": {"temp_proxy_host": ""}}
            )
            
            # Create minimal user object
            class UserObj:
                def __init__(self, uid):
                    self.telegram_user_id = uid
            user_obj = UserObj(user.telegram_user_id)
            
            await self.process_phone_number(event, user_obj, phone)
            
        except Exception as e:
            logger.error(f"Skip confirm OTP error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)

    
    async def process_proxy_before_account(self, event, seller_id, flow_type, country, proxy_text):
        """Process proxy configuration before account upload"""
        try:
            import re
            import html
            from urllib.parse import urlparse, parse_qs
            from app.models import SellerProxy, SellerProxyManager
            
            await self.db_connection.users.update_one(
                {"telegram_user_id": seller_id},
                {"$unset": {"state": ""}}
            )
            
            proxy_text = html.unescape(proxy_text.strip())
            proxy_text = re.sub(r'^https?://', '', proxy_text)
            
            if 't.me/proxy' in proxy_text or 't.me/socks' in proxy_text:
                if '?' not in proxy_text:
                    await self.send_message(event.chat_id, "❌ Invalid t.me proxy link")
                    return
                query_part = proxy_text.split('?')[1]
                params = {}
                for param in query_part.split('&'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        params[key] = value
                proxy_type = 'socks5'
                host_val = params.get('server')
                port_val = int(params.get('port', 1080))
                username_val = params.get('user')
                password_val = params.get('pass')
            elif proxy_text.startswith('tg://'):
                parsed = urlparse(proxy_text)
                params = parse_qs(parsed.query)
                proxy_type = 'socks5'
                host_val = params.get('server', [''])[0]
                port_val = int(params.get('port', [1080])[0])
                username_val = params.get('user', [''])[0] or None
                password_val = params.get('pass', [''])[0] or None
            elif '://' in proxy_text:
                match = re.match(r'(socks5|socks4|http)://(?:([^:]+):([^@]+)@)?([^:]+):(\d+)', proxy_text)
                if not match:
                    await self.send_message(event.chat_id, "❌ Invalid proxy format")
                    return
                proxy_type, username_val, password_val, host_val, port_val = match.groups()
                port_val = int(port_val)
            else:
                await self.send_message(event.chat_id, "❌ Invalid proxy format")
                return
            
            if not host_val or not port_val:
                await self.send_message(event.chat_id, "❌ Missing server or port")
                return
            
            proxy = SellerProxy(
                seller_id=seller_id,
                proxy_type=proxy_type,
                proxy_host=host_val,
                proxy_port=port_val,
                proxy_username=username_val,
                proxy_password=password_val,
                accounts_count=0,
                max_accounts=10
            )
            
            proxy_manager = SellerProxyManager(self.db_connection)
            await proxy_manager.add_proxy(seller_id, proxy)
            
            await self.db_connection.users.update_one(
                {"telegram_user_id": seller_id},
                {"$set": {"temp_proxy_host": host_val, "has_proxy": True}}
            )
            
            await self.send_message(
                event.chat_id,
                f"✅ **{country} Proxy Added!**\n\n"
                f"Type: {proxy_type.upper()}\n"
                f"Host: {host_val}:{port_val}\n"
                f"Capacity: 0/10 accounts\n\n"
            )
            
            if flow_type == "upload":
                await self.send_message(
                    event.chat_id,
                    "📤 **Now Upload Your Account**\n\nSend:\n• Session file\n• Session string\n• TData archive"
                )
                await self.db_connection.users.update_one(
                    {"telegram_user_id": seller_id},
                    {"$set": {"state": "awaiting_upload"}}
                )
            elif flow_type == "otp":
                user_doc = await self.db_connection.users.find_one({"telegram_user_id": seller_id})
                phone = user_doc.get("temp_phone") if user_doc else None
                
                logger.info(f"[SELLER] OTP flow continuation - phone: {phone}")
                
                if phone:
                    await self.send_message(
                        event.chat_id,
                        f"📱 **Sending OTP to {phone}...**\n\nPlease wait..."
                    )
                    class UserObj:
                        def __init__(self, uid):
                            self.telegram_user_id = uid
                    user_obj = UserObj(seller_id)
                    await self.process_phone_number(event, user_obj, phone)
                else:
                    logger.error(f"[SELLER] Phone not found for seller {seller_id}")
                    await self.send_message(event.chat_id, "❌ Session expired. Please start over.")
            
        except Exception as e:
            logger.error(f"Process proxy before account error: {e}")
            await self.send_message(event.chat_id, f"❌ Error: {str(e)}")


    async def notify_admin_new_account(self, account_id, account_doc, quality_score, verification_result):
        """Notify admin about new account pending review"""
        try:
            import os
            admin_ids_str = os.getenv('ADMIN_USER_IDS', '')
            if not admin_ids_str:
                logger.warning("No admin user IDs configured")
                return
            
            admin_ids = [int(uid.strip()) for uid in admin_ids_str.split(',') if uid.strip()]
            
            username = account_doc.get('username', 'No username')
            phone = account_doc.get('phone_number', 'Hidden')
            country = account_doc.get('country', 'Unknown')
            spam_status = account_doc.get('spam_check_result', {}).get('status', 'unknown')
            
            admin_message = f"🔔 **New Account for Review**\n\n"
            admin_message += f"👤 **Account:** @{username}\n"
            admin_message += f"📱 **Phone:** {phone}\n"
            admin_message += f"🌍 **Country:** {country}\n\n"
            admin_message += f"📊 **Quality Score:** {quality_score}/100\n"
            admin_message += f"🔍 **Verification:** {verification_result.get('score_percentage', 0):.1f}%\n"
            admin_message += f"🚫 **Spam Status:** {spam_status.title()}\n\n"
            admin_message += f"⏳ **Awaiting manual review**\n\n"
            admin_message += f"Use /start in Admin Bot to review this account."
            
            for admin_id in admin_ids:
                try:
                    await self.client.send_message(admin_id, admin_message)
                    logger.info(f"Notified admin {admin_id} about account {account_id}")
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {str(e)}")
            
        except Exception as e:
            logger.error(f"Notify admin error: {str(e)}")
