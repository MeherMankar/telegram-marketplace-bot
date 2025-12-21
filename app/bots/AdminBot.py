from datetime import datetime
from telethon import events, Button
from .BaseBot import BaseBot
from app.database.connection import db
from app.models import SettingsManager
from app.services.VerificationService import VerificationService
from app.services.PaymentSettingsService import PaymentSettingsService
from app.services.PaymentService import PaymentService
from app.utils import create_admin_review_keyboard
import logging
import os
from app.utils.datetime_utils import utc_now
from app.bots import proxy_handlers
from bson import ObjectId

logger = logging.getLogger(__name__)

class AdminBot(BaseBot):
    def __init__(self, api_id: int, api_hash: str, bot_token: str, db_connection, admin_user_ids, analytics_service=None, backup_service=None, support_service=None, marketing_service=None, security_service=None, compliance_service=None, bulk_service=None, admin_service=None, code_interceptor_service=None):
        super().__init__(api_id, api_hash, bot_token, db_connection, "Admin")
        self.verification_service = VerificationService(db_connection)
        self.admin_user_ids = admin_user_ids
        self.analytics_service = analytics_service
        self.backup_service = backup_service
        self.support_service = support_service
        self.marketing_service = marketing_service
        self.security_service = security_service
        self.compliance_service = compliance_service
        self.bulk_service = bulk_service
        self.admin_service = admin_service
        self.code_interceptor = code_interceptor_service
        self.settings_manager = SettingsManager(db_connection)
        self.payment_settings_service = PaymentSettingsService(db_connection)
        self.payment_service = PaymentService(db_connection)
    
    async def check_admin_access(self, event):
        """Check if user has admin access"""
        # Check if user is admin BEFORE creating/storing user record
        if event.sender_id not in self.admin_user_ids:
            logger.warning(f"[ADMIN] Access denied for non-admin user {event.sender_id}")
            # Don't respond to non-admin users at all
            return False, None
        
        # Only create user record if they are admin
        user = await self.get_or_create_user(event)
        return True, user
    
    def register_handlers(self):
        """Register admin bot event handlers"""
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await self.handle_start(event)
        
        @self.client.on(events.NewMessage(pattern='/add'))
        async def add_account_handler(event):
            await self.handle_add_interceptor_account(event)
        
        @self.client.on(events.NewMessage(pattern='/list'))
        async def list_accounts_handler(event):
            await self.handle_list_interceptor_accounts(event)
        
        @self.client.on(events.NewMessage(pattern='/stats'))
        async def stats_handler(event):
            await self.handle_interceptor_stats(event)
        
        @self.client.on(events.CallbackQuery)
        async def callback_handler(event):
            await self.handle_callback(event)
        
        @self.client.on(events.NewMessage(func=lambda e: e.text and not e.text.startswith('/')))
        async def text_handler(event):
            await self.handle_text(event)
    
    async def handle_start(self, event):
        """Handle /start command"""
        try:
            logger.info(f"[ADMIN] /start command received from user {event.sender_id}")
            
            # Check admin access
            is_admin, user = await self.check_admin_access(event)
            if not is_admin:
                return
            
            logger.info(f"[ADMIN] Admin user {user.first_name} ({user.telegram_user_id}) accessed admin panel")
            
            # Get admin stats
            stats = await self.get_admin_stats()
            
            welcome_message = f"""
🔧 **Admin Dashboard**

Welcome, Admin {user.first_name}! 👋

📊 **System Statistics:**
• Pending Accounts: {stats.get('accounts', {}).get('pending', 0)}
• Approved Accounts: {stats.get('accounts', {}).get('approved', 0)}
• Active Listings: {stats.get('listings', {}).get('active', 0)}
• Pending Transactions: {stats.get('transactions', {}).get('pending', 0)}
• Total Users: {stats.get('users', {}).get('total', 0)}

**Admin Functions:**
            """
            
            buttons = [
                [Button.inline("📋 Review Accounts", "review_accounts"), Button.inline("💰 Verify Payments", "approve_payments")],
                [Button.inline("💸 Approve Payouts", "approve_payouts"), Button.inline("💲 Manage Prices", "manage_prices")],
                [Button.inline("⚙️ Verification Settings", "verification_settings"), Button.inline("📏 Upload Limits", "upload_limits")],
                [Button.inline("💰 Payment Settings", "payment_settings"), Button.inline("💳 UPI Settings", "upi_settings")],
                [Button.inline("🔑 Razorpay Settings", "razorpay_settings"), Button.inline("₿ Crypto Settings", "crypto_settings")],
                [Button.inline("🔒 Security Settings", "security_settings")],
                [Button.inline("🤖 Bot Settings", "bot_settings"), Button.inline("📊 View Stats", "view_stats")],
                [Button.inline("📝 View Logs", "view_logs")]
            ]
            
            await self.send_message(event.chat_id, welcome_message, buttons)
            logger.info(f"[ADMIN] Admin dashboard sent to {user.telegram_user_id}")
            
        except Exception as e:
            logger.error(f"[ADMIN] Start handler error for {event.sender_id}: {str(e)}")
            await self.send_message(event.chat_id, "❌ An error occurred. Please try again.")
    
    async def handle_callback(self, event):
        """Handle callback queries"""
        try:
            data = event.data.decode('utf-8')
            logger.info(f"[ADMIN] Callback received: '{data}' from user {event.sender_id}")
            
            # Check admin access
            is_admin, user = await self.check_admin_access(event)
            if not is_admin:
                await self.answer_callback(event, "❌ Access denied", alert=True)
                return
            
            if data == "review_accounts":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'Review Accounts'")
                await self.handle_review_accounts(event)
            elif data == "approve_payments":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'Approve Payments'")
                await self.handle_verify_payments(event)
            elif data == "approve_payouts":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'Approve Payouts'")
                await self.handle_approve_payouts(event)
            elif data == "manage_prices":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'Manage Prices'")
                await self.handle_manage_prices(event)
            elif data == "view_stats":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'View Stats'")
                await self.handle_view_stats(event)
            elif data == "view_logs":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'View Logs'")
                await self.handle_view_logs(event)
            elif data == "verification_settings":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'Verification Settings'")
                await self.handle_verification_settings(event)
            elif data == "upload_limits":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'Upload Limits'")
                await self.handle_upload_limits(event)
            elif data == "payment_settings":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'Payment Settings'")
                await self.handle_payment_settings(event)
            elif data == "upi_settings":
                await self.handle_upi_settings(event)
            elif data == "razorpay_settings":
                await self.handle_razorpay_settings(event)
            elif data == "crypto_settings":
                await self.handle_crypto_settings(event)
            elif data == "security_settings":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'Security Settings'")
                await self.handle_security_settings(event)
            elif data == "proxy_settings":
                await proxy_handlers.handle_proxy_settings(self, event)
            elif data == "proxy_add":
                await proxy_handlers.handle_proxy_add(self, event)
            elif data == "proxy_test":
                await proxy_handlers.handle_proxy_test(self, event)
            elif data == "proxy_disable":
                await proxy_handlers.handle_proxy_disable(self, event)
            elif data == "bot_settings":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'Bot Settings'")
                await self.handle_bot_settings(event)
            elif data == "payment_settings_detailed":
                await self.handle_payment_settings_detailed(event)
            elif data == "payment_gateways":
                await self.handle_payment_gateways(event)
            elif data == "payment_dashboard":
                await self.handle_payment_dashboard(event)
            elif data == "set_payment_timeout":
                await self.handle_payment_timeout_setting(event, user)
            elif data.startswith("set_upi_"):
                setting_type = data.split("_", 2)[2]
                await self.handle_set_upi_setting(event, user, setting_type)
            elif data.startswith("set_razorpay_"):
                setting_type = data.split("_", 2)[2]
                await self.handle_set_razorpay_setting(event, user, setting_type)
            elif data.startswith("set_crypto_"):
                setting_type = data.split("_", 2)[2]
                await self.handle_set_crypto_setting(event, user, setting_type)
            elif data == "security_settings_detailed":
                await self.handle_security_settings_detailed(event)
            elif data == "seller_settings":
                await self.handle_seller_settings(event)
            elif data.startswith("setting_seller_"):
                setting_key = data.split("_", 2)[2]
                await self.handle_toggle_seller_setting(event, user, setting_key)
            elif data == "set_seller_max_uploads":
                await self.handle_set_seller_max_uploads(event, user)
            elif data == "buyer_settings":
                await self.handle_buyer_settings(event)
            elif data.startswith("setting_buyer_"):
                setting_key = data.split("_", 2)[2]
                await self.handle_toggle_buyer_setting(event, user, setting_key)
            elif data == "set_buyer_max_purchases":
                await self.handle_set_buyer_max_purchases(event, user)
            elif data == "logs_filter_error":
                await self.handle_logs_filter(event, user, "ERROR")
            elif data == "logs_filter_warning":
                await self.handle_logs_filter(event, user, "WARNING")
            elif data == "logs_filter_all":
                await self.handle_logs_filter(event, user, None)
            elif data == "logs_refresh":
                await self.handle_view_logs(event)
            elif data == "logs_clear":
                await self.handle_clear_logs(event, user)
            elif data == "general_settings_detailed":
                await self.handle_general_settings_detailed(event)
            elif data.startswith("setting_"):
                setting_parts = data.split("_", 2)
                setting_type = setting_parts[1]
                setting_key = setting_parts[2]
                await self.handle_toggle_setting(event, user, setting_type, setting_key)
            elif data.startswith("set_limit_"):
                await self.handle_set_limit(event, data)
            elif data.startswith("set_upload_"):
                await self.handle_set_upload_limit(event, data)
            elif data.startswith("set_payment_"):
                await self.handle_set_payment_setting(event, data)
            elif data.startswith("set_security_"):
                await self.handle_set_security_setting(event, data)
            elif data.startswith("review_account_"):
                account_id = data.split("_", 2)[2]
                await self.handle_account_review_details(event, account_id)
            elif data.startswith("admin_approve_"):
                account_id = data.split("_", 2)[2]
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} approving account {account_id}")
                await self.handle_approve_account(event, user, account_id)
            elif data.startswith("admin_reject_"):
                account_id = data.split("_", 2)[2]
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} rejecting account {account_id}")
                await self.handle_reject_account(event, user, account_id)
            elif data.startswith("admin_manual_"):
                account_id = data.split("_", 2)[2]
                await self.handle_manual_review(event, user, account_id)
            elif data.startswith("admin_price_"):
                account_id = data.split("_", 2)[2]
                await self.handle_set_price(event, user, account_id)
            elif data.startswith("admin_verify_"):
                account_id = data.split("_", 2)[2]
                await self.handle_verify_account(event, user, account_id)
            elif data.startswith("auto_price_"):
                account_id = data.split("_", 2)[2]
                await self.handle_auto_price(event, user, account_id)
            elif data.startswith("admin_quality_"):
                account_id = data.split("_", 2)[2]
                await self.handle_quality_check(event, user, account_id)
            elif data.startswith("admin_security_"):
                account_id = data.split("_", 2)[2]
                await self.handle_security_check(event, user, account_id)
            elif data.startswith("admin_login_"):
                account_id = data.split("_", 2)[2]
                await self.handle_login_account(event, user, account_id)
            elif data.startswith("verify_payment_"):
                order_id = data.split("_", 2)[2]
                await self.handle_payment_verification_details(event, order_id)
            elif data.startswith("approve_payment_"):
                order_id = data.split("_", 2)[2]
                await self.handle_approve_payment_verification(event, user, order_id)
            elif data.startswith("reject_payment_"):
                order_id = data.split("_", 2)[2]
                await self.handle_reject_payment_verification(event, user, order_id)
            elif data.startswith("approve_upi_"):
                order_id = data.split("_", 2)[2]
                await self.handle_approve_upi_payment(event, user, order_id)
            elif data.startswith("reject_upi_"):
                order_id = data.split("_", 2)[2]
                await self.handle_reject_upi_payment(event, user, order_id)
            elif data.startswith("verify_upi_"):
                order_id = data.split("_", 2)[2]
                await self.handle_verify_upi_payment(event, order_id)
            elif data.startswith("view_screenshot_"):
                order_id = data.split("_", 2)[2]
                await self.handle_view_payment_screenshot(event, order_id)

            elif data.startswith("approve_payout_"):
                payout_id = data.split("_", 2)[2]
                await self.handle_approve_payout(event, user, payout_id)
            elif data.startswith("price_country_"):
                country = data.split("_", 2)[2]
                await self.handle_country_pricing(event, country)
            elif data.startswith("price_year_"):
                parts = data.split("_")
                country = parts[2]
                year = parts[3]
                await self.handle_year_pricing(event, country, year)
            elif data == "add_country":
                await self.handle_add_country(event)
            elif data.startswith("adjust_buy_"):
                parts = data.split("_")
                country = parts[2]
                year = parts[3]
                await self.handle_adjust_buy_price(event, country, year)
            elif data.startswith("adjust_sell_"):
                parts = data.split("_")
                country = parts[2]
                year = parts[3]
                await self.handle_adjust_sell_price(event, country, year)
            elif data == "back_to_main":
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} clicked 'Back to Main'")
                await self.handle_start(event)
            else:
                logger.warning(f"[ADMIN] Unknown callback data: '{data}' from admin {user.telegram_user_id}")
            
            try:
                await self.answer_callback(event)
            except Exception:
                pass  # Ignore callback answer errors
            
        except Exception as e:
            logger.error(f"[ADMIN] Callback handler error for {event.sender_id}: {str(e)}")
            try:
                await self.answer_callback(event, "❌ An error occurred", alert=True)
            except Exception:
                pass  # Ignore callback answer errors
    
    async def handle_review_accounts(self, event):
        """Handle account review"""
        try:
            # Get pending accounts (only pending, not approved)
            accounts = await self.db_connection.accounts.find({
                "status": "pending"
            }).sort("created_at", 1).to_list(length=10)
            
            if not accounts:
                await self.edit_message(
                    event,
                    "📋 **Account Review**\n\n✅ No accounts pending review!",
                    [[Button.inline("🔙 Back", "back_to_main")]]
                )
                return
            
            review_message = "📋 **Accounts Pending Review**\n\n"
            buttons = []
            
            for account in accounts:
                # Get seller info
                seller = await self.db_connection.users.find_one({"telegram_user_id": account["seller_id"]})
                seller_name = seller.get("first_name", "Unknown") if seller else "Unknown"
                
                username = account.get("username", "No username")
                country = account.get("country", "Unknown")
                creation_year = account.get("creation_year", "Unknown")
                
                review_message += f"👤 **{username}** ({country} {creation_year})\n"
                review_message += f"   Seller: {seller_name}\n"
                review_message += f"   Status: {account['status'].title()}\n\n"
                
                buttons.append([Button.inline(f"Review {username}", f"review_account_{account['_id']}")])
            
            buttons.append([Button.inline("🔙 Back", "back_to_main")])
            
            await self.edit_message(event, review_message, buttons)
            
        except Exception as e:
            logger.error(f"Review accounts handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_account_review_details(self, event, account_id):
        """Show detailed account review"""
        try:
            # Convert string account_id to ObjectId
            from bson import ObjectId
            try:
                if isinstance(account_id, str):
                    account_id = ObjectId(account_id)
            except Exception as e:
                logger.error(f"Invalid account ID format: {account_id}, error: {e}")
                await self.edit_message(
                    event,
                    "❌ Invalid account ID format.",
                    [[Button.inline("🔙 Back", "review_accounts")]]
                )
                return
            
            # Get account
            account = await self.db_connection.accounts.find_one({"_id": account_id})
            if not account:
                await self.edit_message(
                    event,
                    "❌ Account not found.",
                    [[Button.inline("🔙 Back", "review_accounts")]]
                )
                return
            
            # Get seller info
            seller = await self.db_connection.users.find_one({"telegram_user_id": account["seller_id"]})
            seller_name = seller.get("first_name", "Unknown") if seller else "Unknown"
            
            # Format verification results
            checks_summary = ""
            if account.get("checks"):
                for check_name, check_result in account["checks"].items():
                    status = "✅" if check_result.get("passed", False) else "❌"
                    checks_summary += f"{status} {check_name.replace('_', ' ').title()}\n"
            
            review_message = f"""
🔍 **Account Review Details**

👤 **Account:** {account.get('username', 'No username')}
🆔 **Telegram ID:** {account.get('telegram_account_id', 'Unknown')}
📱 **Phone:** {account.get('phone_number', 'Hidden')}
🌍 **Country:** {account.get('country', 'Unknown')}
📅 **Creation Year:** {account.get('creation_year', 'Unknown')}
👨💼 **Seller:** {seller_name}

**Verification Results:**
{checks_summary}

**Logs:**
{chr(10).join(account.get('verification_logs', [])[-5:])}

**Current Status:** {account['status'].title()}
            """
            
            buttons = create_admin_review_keyboard(account_id)
            await self.edit_message(event, review_message, buttons)
            
        except Exception as e:
            logger.error(f"Account review details error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_approve_account(self, event, user, account_id):
        """Handle account approval"""
        try:
            # Convert string account_id to ObjectId
            from bson import ObjectId
            if isinstance(account_id, str):
                account_id = ObjectId(account_id)
            
            # Simulate admin service approval
            if self.admin_service:
                result = await self.admin_service.approve_account(user.telegram_user_id, account_id)
            else:
                # Fallback implementation
                await self.db_connection.accounts.update_one(
                    {"_id": account_id},
                    {"$set": {"status": "approved", "approved_at": utc_now(), "approved_by": user.telegram_user_id}}
                )
                result = {"success": True, "price": 40}
            
            if result.get("success"):
                # Enable OTP destroyer
                account = await self.db_connection.accounts.find_one({"_id": account_id})
                if account and account.get("session_string"):
                    await self.verification_service.enable_otp_destroyer(account["session_string"])
                    await self.db_connection.accounts.update_one(
                        {"_id": account_id},
                        {"$set": {"otp_destroyer_enabled": True}}
                    )
                
                await self.edit_message(
                    event,
                    f"✅ **Account Approved**\n\nAccount has been approved and listed for sale.\nPrice: ${result.get('price', 0):.2f}",
                    [[Button.inline("🔙 Back", "review_accounts")]]
                )
                
                # Notify seller
                seller_id = account["seller_id"]
                await self.notify_seller_approval(seller_id, account_id, result.get('price', 0))
                
            else:
                await self.edit_message(
                    event,
                    f"❌ **Approval Failed**\n\n{result.get('error', 'Unknown error')}",
                    [[Button.inline("🔙 Back", "review_accounts")]]
                )
            
        except Exception as e:
            logger.error(f"Approve account error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_reject_account(self, event, user, account_id):
        """Handle account rejection"""
        try:
            # Convert string account_id to ObjectId
            from bson import ObjectId
            if isinstance(account_id, str):
                account_id = ObjectId(account_id)
            
            # For simplicity, using a default reason
            reason = "Account did not meet marketplace standards"
            
            # Simulate admin service rejection
            if self.admin_service:
                result = await self.admin_service.reject_account(user.telegram_user_id, account_id, reason)
            else:
                # Fallback implementation
                await self.db_connection.accounts.update_one(
                    {"_id": account_id},
                    {"$set": {"status": "rejected", "rejected_at": utc_now(), "rejected_by": user.telegram_user_id, "rejection_reason": reason}}
                )
                result = {"success": True}
            
            if result.get("success"):
                await self.edit_message(
                    event,
                    f"❌ **Account Rejected**\n\nReason: {reason}",
                    [[Button.inline("🔙 Back", "review_accounts")]]
                )
                
                # Notify seller
                account = await self.db_connection.accounts.find_one({"_id": account_id})
                if account:
                    await self.notify_seller_rejection(account["seller_id"], account_id, reason)
                
            else:
                await self.edit_message(
                    event,
                    f"❌ **Rejection Failed**\n\n{result.get('error', 'Unknown error')}",
                    [[Button.inline("🔙 Back", "review_accounts")]]
                )
            
        except Exception as e:
            logger.error(f"Reject account error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_verify_payments(self, event):
        """Handle payment verifications"""
        try:
            # Get pending payment verifications (regular payments)
            pending_orders = []
            try:
                if hasattr(self.payment_service, 'get_pending_verifications'):
                    pending_orders = await self.payment_service.get_pending_verifications()
            except (AttributeError, Exception) as e:
                logger.warning(f"Could not get pending payment verifications: {str(e)}")
                pending_orders = []
            
            # Get pending UPI orders
            pending_upi_orders = await self.db_connection.upi_orders.find({
                "status": "pending_verification",
                "screenshot_uploaded_at": {"$exists": True}
            }).to_list(length=20)
            
            if not pending_orders and not pending_upi_orders:
                await self.edit_message(
                    event,
                    "💰 **Payment Verifications**\n\n✅ No payments pending verification!",
                    [[Button.inline("🔙 Back", "back_to_main")]]
                )
                return
            
            payments_message = "💰 **Payments Pending Verification**\n\n"
            buttons = []
            
            # Add regular payment orders
            for order in pending_orders:
                # Get user info
                user_info = await self.db_connection.users.find_one({"telegram_user_id": order["user_id"]})
                user_name = user_info.get("first_name", "Unknown") if user_info else "Unknown"
                
                payments_message += f"💳 **₹{order['total_amount']:.2f}** - {order['payment_method'].upper()}\n"
                payments_message += f"   User: {user_name}\n"
                payments_message += f"   Submitted: {order['proof_submitted_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
                
                buttons.append([Button.inline(f"Verify ₹{order['total_amount']:.2f}", f"verify_payment_{order['order_id']}")])
            
            # Add UPI orders
            for order in pending_upi_orders:
                # Get user info
                user_info = await self.db_connection.users.find_one({"telegram_user_id": order["user_id"]})
                user_name = user_info.get("first_name", "Unknown") if user_info else "Unknown"
                
                payments_message += f"💳 **UPI Quick Deposit** - Any Amount\n"
                payments_message += f"   User: {user_name}\n"
                payments_message += f"   Submitted: {order.get('screenshot_uploaded_at', 'Unknown')}\n\n"
                
                buttons.append([Button.inline(f"Verify UPI {order['order_id'][:8]}...", f"verify_upi_{order['order_id']}")])
            
            buttons.append([Button.inline("🔙 Back", "back_to_main")])
            
            await self.edit_message(event, payments_message, buttons)
            
        except Exception as e:
            logger.error(f"Verify payments handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_payment_verification_details(self, event, order_id):
        """Show payment verification details"""
        try:
            order = None
            try:
                if hasattr(self.db_connection, 'payment_orders'):
                    order = await self.db_connection.payment_orders.find_one({"order_id": order_id})
            except (AttributeError, Exception) as e:
                pass
                
            if not order:
                await self.edit_message(
                    event,
                    "❌ Payment order not found.",
                    [[Button.inline("🔙 Back", "approve_payments")]]
                )
                return
            
            # Get user info
            user_info = await self.db_connection.users.find_one({"telegram_user_id": order["user_id"]})
            user_name = user_info.get("first_name", "Unknown") if user_info else "Unknown"
            
            details_message = f"""
🔍 **Payment Verification Details**

💳 **Order ID:** {order['order_id']}
👤 **User:** {user_name} (ID: {order['user_id']})
💰 **Base Amount:** ₹{order['base_amount']:.2f}
💵 **Fee:** ₹{order['fee_amount']:.2f}
💸 **Total Amount:** ₹{order['total_amount']:.2f}
💳 **Payment Method:** {order['payment_method'].upper()}
📅 **Submitted:** {order['proof_submitted_at'].strftime('%Y-%m-%d %H:%M')}

📸 **Screenshot:** {'✅ Uploaded' if order.get('screenshot_uploaded') else '❌ Not uploaded'}

**Action Required:** Verify this payment manually
            """
            
            buttons = [
                [Button.inline("✅ Approve Payment", f"approve_payment_{order_id}"),
                 Button.inline("❌ Reject Payment", f"reject_payment_{order_id}")]
            ]
            
            # Add screenshot view button if available
            if order.get('screenshot_file_id'):
                buttons.insert(1, [Button.inline("📸 View Screenshot", f"view_screenshot_{order_id}")])
            
            buttons.append([Button.inline("🔙 Back", "approve_payments")])
            
            await self.edit_message(event, details_message, buttons)
            
        except Exception as e:
            logger.error(f"Payment verification details error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_view_payment_screenshot(self, event, order_id):
        """View payment screenshot for verification"""
        try:
            # Get payment order
            order = None
            try:
                if hasattr(self.db_connection, 'payment_orders'):
                    order = await self.db_connection.payment_orders.find_one({"order_id": order_id})
            except (AttributeError, Exception) as e:
                pass
                
            if not order or not order.get('screenshot_file_id'):
                await self.answer_callback(event, "📸 Screenshot not found", alert=True)
                return
            
            # Get user info
            user_info = await self.db_connection.users.find_one({"telegram_user_id": order["user_id"]})
            user_name = user_info.get("first_name", "Unknown") if user_info else "Unknown"
            
            # Send screenshot to admin
            try:
                await self.client.send_file(
                    event.chat_id,
                    order['screenshot_file_id'],
                    caption=f"📸 **Payment Screenshot**\n\n**Order ID:** {order_id}\n**User:** {user_name}\n**Amount:** ₹{order['total_amount']:.2f}\n**Method:** {order['payment_method'].upper()}\n**Submitted:** {order['proof_submitted_at'].strftime('%Y-%m-%d %H:%M')}",
                    buttons=[
                        [Button.inline("✅ Approve Payment", f"approve_payment_{order_id}")],
                        [Button.inline("❌ Reject Payment", f"reject_payment_{order_id}")],
                        [Button.inline("🔙 Back to Details", f"verify_payment_{order_id}")]
                    ]
                )
                await self.answer_callback(event, "📸 Screenshot displayed")
            except Exception as e:
                logger.error(f"Error sending screenshot: {str(e)}")
                await self.answer_callback(event, "❌ Failed to load screenshot", alert=True)
                
        except Exception as e:
            logger.error(f"[ADMIN] View payment screenshot error: {str(e)}")
            await self.answer_callback(event, "❌ Error viewing screenshot", alert=True)
    
    async def handle_approve_payment_verification(self, event, user, order_id):
        """Approve payment verification"""
        try:
            result = await self.payment_service.verify_payment(
                order_id, user.telegram_user_id, True, "Approved by admin"
            )
            
            if result.get("success"):
                await self.edit_message(
                    event,
                    f"✅ **Payment Approved**\n\nOrder {order_id} has been verified and approved.",
                    [[Button.inline("🔙 Back", "approve_payments")]]
                )
            else:
                await self.edit_message(
                    event,
                    f"❌ **Approval Failed**\n\n{result.get('error', 'Unknown error')}",
                    [[Button.inline("🔙 Back", "approve_payments")]]
                )
            
        except Exception as e:
            logger.error(f"Approve payment verification error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_reject_payment_verification(self, event, user, order_id):
        """Reject payment verification"""
        try:
            result = await self.payment_service.verify_payment(
                order_id, user.telegram_user_id, False, "Rejected by admin - insufficient proof"
            )
            
            if result.get("success"):
                await self.edit_message(
                    event,
                    f"❌ **Payment Rejected**\n\nOrder {order_id} has been rejected.",
                    [[Button.inline("🔙 Back", "approve_payments")]]
                )
            else:
                await self.edit_message(
                    event,
                    f"❌ **Rejection Failed**\n\n{result.get('error', 'Unknown error')}",
                    [[Button.inline("🔙 Back", "approve_payments")]]
                )
            
        except Exception as e:
            logger.error(f"Reject payment verification error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_approve_payment(self, event, user, transaction_id):
        """Handle individual payment approval"""
        try:
            # Simulate admin service payment approval
            if self.admin_service:
                result = await self.admin_service.approve_payment(user.telegram_user_id, transaction_id)
            else:
                # Fallback implementation
                await self.db_connection.transactions.update_one(
                    {"_id": transaction_id},
                    {"$set": {"status": "confirmed", "confirmed_at": utc_now(), "confirmed_by": user.telegram_user_id}}
                )
                result = {"success": True}
            
            if result.get("success"):
                # Get transaction details
                transaction = await self.db_connection.transactions.find_one({"_id": transaction_id})
                
                # Mark listing as sold
                if transaction and transaction.get("listing_id"):
                    await self.db_connection.listings.update_one(
                        {"_id": transaction["listing_id"]},
                        {
                            "$set": {
                                "status": "sold",
                                "buyer_id": transaction["user_id"],
                                "sold_at": utc_now()
                            }
                        }
                    )
                    
                    # Mark account as sold
                    await self.db_connection.accounts.update_one(
                        {"_id": transaction["account_id"]},
                        {"$set": {"status": "sold"}}
                    )
                    
                    # Disable OTP destroyer and transfer account
                    account = await self.db_connection.accounts.find_one({"_id": transaction["account_id"]})
                    if account and account.get("session_string"):
                        await self.verification_service.disable_otp_destroyer(account["session_string"])
                        
                        # Send session to buyer (this would be implemented in the buyer bot)
                        await self.deliver_account_to_buyer(transaction["user_id"], account)
                
                await self.edit_message(
                    event,
                    "✅ **Payment Approved**\n\nPayment has been confirmed and seller balance updated.",
                    [[Button.inline("🔙 Back", "approve_payments")]]
                )
                
            else:
                await self.edit_message(
                    event,
                    f"❌ **Approval Failed**\n\n{result.get('error', 'Unknown error')}",
                    [[Button.inline("🔙 Back", "approve_payments")]]
                )
            
        except Exception as e:
            logger.error(f"Approve payment error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_view_stats(self, event):
        """Show system statistics"""
        try:
            # Use local stats method instead of admin_service
            stats = await self.get_admin_stats()
            
            stats_message = f"""
📊 **System Statistics**

**Accounts:**
• Pending: {stats.get('accounts', {}).get('pending', 0)}
• Approved: {stats.get('accounts', {}).get('approved', 0)}
• Rejected: {stats.get('accounts', {}).get('rejected', 0)}
• Sold: {stats.get('accounts', {}).get('sold', 0)}

**Listings:**
• Active: {stats.get('listings', {}).get('active', 0)}
• Sold: {stats.get('listings', {}).get('sold', 0)}

**Transactions:**
• Pending: {stats.get('transactions', {}).get('pending', 0)}
• Confirmed: {stats.get('transactions', {}).get('confirmed', 0)}

**Users:**
• Total: {stats.get('users', {}).get('total', 0)}
• Sellers: {stats.get('users', {}).get('sellers', 0)}
            """
            
            await self.edit_message(
                event,
                stats_message,
                [[Button.inline("🔄 Refresh", "view_stats")], [Button.inline("🔙 Back", "back_to_main")]]
            )
            
        except Exception as e:
            logger.error(f"View stats error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_manage_prices(self, event):
        """Handle price management with buy/sell pricing"""
        try:
            # Get current price table
            price_doc = await self.db_connection.admin_settings.find_one({"type": "price_table"})
            if price_doc:
                prices = price_doc.get("prices", {})
            else:
                prices = {"US": {"2025": {"buy": 40, "sell": 50}, "2024": {"buy": 30, "sell": 40}}, "IN": {"2025": {"buy": 30, "sell": 40}, "2024": {"buy": 20, "sell": 30}}}
            
            # Get available countries from accounts
            countries = await self.db_connection.accounts.distinct("country")
            if not countries:
                countries = list(prices.keys())
            
            price_message = "💲 **Price Management (Buy/Sell)**\n\nCurrent pricing by country:\n\n"
            
            for country in sorted(countries):
                if country and country in prices:
                    country_prices = prices[country]
                    price_message += f"🌍 **{country}**:\n"
                    for year, price_data in sorted(country_prices.items(), reverse=True):
                        if isinstance(price_data, dict):
                            buy_price = price_data.get('buy', 30)
                            sell_price = price_data.get('sell', 40)
                            profit = sell_price - buy_price
                            price_message += f"   {year}: Buy ₹{buy_price} | Sell ₹{sell_price} | Profit ₹{profit}\n"
                        else:
                            # Legacy format - convert to new format
                            buy_price = int(price_data * 0.75)
                            sell_price = price_data
                            price_message += f"   {year}: Buy ₹{buy_price} | Sell ₹{sell_price}\n"
                    price_message += "\n"
            
            buttons = []
            for country in sorted(countries)[:8]:  # Show max 8 countries
                if country:
                    buttons.append([Button.inline(f"🌍 {country}", f"price_country_{country}")])
            
            buttons.extend([
                [Button.inline("➕ Add Country", "add_country")],
                [Button.inline("🔙 Back", "back_to_main")]
            ])
            
            await self.edit_message(event, price_message, buttons)
            
        except Exception as e:
            logger.error(f"Manage prices handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_approve_payouts(self, event):
        """Handle payout approvals"""
        await self.edit_message(
            event,
            "💸 **Payout Approvals**\n\nPayout approval interface coming soon...",
            [[Button.inline("🔙 Back", "back_to_main")]]
        )
    
    async def handle_view_logs(self, event):
        """Handle log viewing"""
        try:
            # Get recent logs from database
            logs = await self.db_connection.error_logs.find().sort("timestamp", -1).limit(20).to_list(20)
            
            if not logs:
                message = "📝 **System Logs**\n\n✅ No logs found."
            else:
                message = f"📝 **System Logs** (Last 20)\n\n"
                for log in logs:
                    level = log.get('level', 'INFO')
                    emoji = {'ERROR': '🔴', 'WARNING': '⚠️', 'INFO': 'ℹ️'}.get(level, 'ℹ️')
                    timestamp = log.get('timestamp', utc_now()).strftime('%m/%d %H:%M')
                    message_text = log.get('message', 'No message')[:50]
                    message += f"{emoji} {timestamp} - {message_text}\n"
            
            buttons = [
                [Button.inline("🔴 Errors Only", "logs_filter_error")],
                [Button.inline("⚠️ Warnings", "logs_filter_warning"), Button.inline("ℹ️ All Logs", "logs_filter_all")],
                [Button.inline("🔄 Refresh", "logs_refresh"), Button.inline("🗑️ Clear Logs", "logs_clear")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, message, buttons)
            
        except Exception as e:
            logger.error(f"View logs error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_verification_settings(self, event):
        """Handle verification settings management"""
        try:
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "verification_limits"})
            if settings:
                limits = settings.get("limits", {})
            else:
                limits = {
                    "max_contacts": 5,
                    "max_bot_chats": 3,
                    "max_active_sessions": 3,
                    "max_groups_owned": 10,
                    "require_spam_check": True,
                    "require_zero_contacts": False
                }
            
            settings_message = f"""
⚙️ **Verification Settings**

Current limits for account verification:

📞 **Max Contacts:** {limits.get('max_contacts', 5)}
🤖 **Max Bot Chats:** {limits.get('max_bot_chats', 3)}
📱 **Max Active Sessions:** {limits.get('max_active_sessions', 3)}
👥 **Max Owned Groups:** {limits.get('max_groups_owned', 10)}
🚫 **Require Spam Check:** {'Yes' if limits.get('require_spam_check', True) else 'No'}
🔒 **Require Zero Contacts:** {'Yes' if limits.get('require_zero_contacts', False) else 'No'}

Click to modify:
            """
            
            buttons = [
                [Button.inline(f"📞 Contacts ({limits.get('max_contacts', 5)})", "set_limit_contacts"), 
                 Button.inline(f"🤖 Bot Chats ({limits.get('max_bot_chats', 3)})", "set_limit_bots")],
                [Button.inline(f"📱 Sessions ({limits.get('max_active_sessions', 3)})", "set_limit_sessions"), 
                 Button.inline(f"👥 Groups ({limits.get('max_groups_owned', 10)})", "set_limit_groups")],
                [Button.inline(f"🚫 Spam Check ({'On' if limits.get('require_spam_check', True) else 'Off'})", "set_limit_spam"), 
                 Button.inline(f"🔒 Zero Contacts ({'On' if limits.get('require_zero_contacts', False) else 'Off'})", "set_limit_zero_contacts")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"Verification settings error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_set_limit(self, event, data):
        """Handle setting verification limits"""
        try:
            limit_type = data.split("_", 2)[2]
            logger.info(f"[ADMIN] Setting limit type: {limit_type} for admin {event.sender_id}")
            
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "verification_limits"})
            if settings:
                limits = settings.get("limits", {})
                logger.info(f"[ADMIN] Current limits: {limits}")
            else:
                limits = {
                    "max_contacts": 5,
                    "max_bot_chats": 3,
                    "max_active_sessions": 3,
                    "max_groups_owned": 10,
                    "require_spam_check": True,
                    "require_zero_contacts": False
                }
                logger.info(f"[ADMIN] Using default limits: {limits}")
            
            if limit_type == "contacts":
                # Cycle through contact limits: 0, 3, 5, 10, 20
                current = limits.get('max_contacts', 5)
                new_value = {0: 3, 3: 5, 5: 10, 10: 20, 20: 0}.get(current, 5)
                limits['max_contacts'] = new_value
                logger.info(f"[ADMIN] Changed max_contacts from {current} to {new_value}")
                
            elif limit_type == "bots":
                # Cycle through bot limits: 0, 3, 5, 10
                current = limits.get('max_bot_chats', 3)
                new_value = {0: 3, 3: 5, 5: 10, 10: 0}.get(current, 3)
                limits['max_bot_chats'] = new_value
                logger.info(f"[ADMIN] Changed max_bot_chats from {current} to {new_value}")
                
            elif limit_type == "sessions":
                # Cycle through session limits: 1, 3, 5, 10
                current = limits.get('max_active_sessions', 3)
                new_value = {1: 3, 3: 5, 5: 10, 10: 1}.get(current, 3)
                limits['max_active_sessions'] = new_value
                logger.info(f"[ADMIN] Changed max_active_sessions from {current} to {new_value}")
                
            elif limit_type == "groups":
                # Cycle through group limits: 5, 10, 20, 50
                current = limits.get('max_groups_owned', 10)
                new_value = {5: 10, 10: 20, 20: 50, 50: 5}.get(current, 10)
                limits['max_groups_owned'] = new_value
                logger.info(f"[ADMIN] Changed max_groups_owned from {current} to {new_value}")
                
            elif limit_type == "spam":
                # Toggle spam check
                current = limits.get('require_spam_check', True)
                limits['require_spam_check'] = not current
                logger.info(f"[ADMIN] Toggled require_spam_check from {current} to {not current}")
                
            elif limit_type == "zero_contacts":
                # Toggle zero contacts requirement
                current = limits.get('require_zero_contacts', False)
                limits['require_zero_contacts'] = not current
                logger.info(f"[ADMIN] Toggled require_zero_contacts from {current} to {not current}")
            
            # Save updated settings
            logger.info(f"[ADMIN] Saving updated limits to database: {limits}")
            await self.db_connection.admin_settings.update_one(
                {"type": "verification_limits"},
                {"$set": {"limits": limits, "updated_at": utc_now()}},
                upsert=True
            )
            logger.info(f"[ADMIN] Verification limits updated successfully")
            
            # Show updated settings
            await self.handle_verification_settings(event)
            
        except Exception as e:
            logger.error(f"[ADMIN] Set limit error for {event.sender_id}: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_upload_limits(self, event):
        """Handle upload limits management"""
        try:
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "upload_limits"})
            if settings:
                limits = settings.get("limits", {})
            else:
                limits = {
                    "enabled": False,
                    "max_per_day": 999
                }
            
            settings_message = f"""
📏 **Upload Limits Settings**

Current settings for daily upload limits:

🔄 **Upload Limits:** {'Enabled' if limits.get('enabled', True) else 'Disabled'}
📊 **Max Per Day:** {limits.get('max_per_day', 5)} accounts

Click to modify:
            """
            
            buttons = [
                [Button.inline(f"🔄 Limits ({'On' if limits.get('enabled', True) else 'Off'})", "set_upload_enabled"), 
                 Button.inline(f"📊 Max Per Day ({limits.get('max_per_day', 5)})", "set_upload_max")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"[ADMIN] Upload limits error for {event.sender_id}: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_set_upload_limit(self, event, data):
        """Handle setting upload limits"""
        try:
            setting_type = data.split("_", 2)[2]
            logger.info(f"[ADMIN] Setting upload limit type: {setting_type} for admin {event.sender_id}")
            
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "upload_limits"})
            if settings:
                limits = settings.get("limits", {})
                logger.info(f"[ADMIN] Current upload limits: {limits}")
            else:
                limits = {
                    "enabled": False,
                    "max_per_day": 999
                }
                logger.info(f"[ADMIN] Using default upload limits: {limits}")
            
            if setting_type == "enabled":
                # Toggle upload limits
                current = limits.get('enabled', True)
                limits['enabled'] = not current
                logger.info(f"[ADMIN] Toggled upload limits from {current} to {not current}")
                
            elif setting_type == "max":
                # Cycle through max limits: 1, 3, 5, 10, 20, 50, unlimited
                current = limits.get('max_per_day', 5)
                new_value = {1: 3, 3: 5, 5: 10, 10: 20, 20: 50, 50: 999, 999: 1}.get(current, 5)
                limits['max_per_day'] = new_value
                logger.info(f"[ADMIN] Changed max_per_day from {current} to {new_value}")
            
            # Save updated settings
            logger.info(f"[ADMIN] Saving updated upload limits to database: {limits}")
            await self.db_connection.admin_settings.update_one(
                {"type": "upload_limits"},
                {"$set": {"limits": limits, "updated_at": utc_now()}},
                upsert=True
            )
            logger.info(f"[ADMIN] Upload limits updated successfully")
            
            # Show updated settings
            await self.handle_upload_limits(event)
            
        except Exception as e:
            logger.error(f"[ADMIN] Set upload limit error for {event.sender_id}: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_bot_settings(self, event):
        """Handle comprehensive bot settings management"""
        try:
            settings_message = """
🤖 **Bot Settings Management**

Manage all seller and buyer bot settings:

**Seller Bot Settings:**
• Upload limits and file restrictions
• Verification thresholds
• Payout configurations

**Buyer Bot Settings:**
• Payment methods and timeouts
• Browsing preferences
• Purchase restrictions

**General Settings:**
• Maintenance mode
• Welcome messages
• Terms of service

Select category to configure:
            """
            
            buttons = [
                [Button.inline("📤 Seller Settings", "seller_settings"), Button.inline("🛒 Buyer Settings", "buyer_settings")],
                [Button.inline("⚙️ General Settings", "general_settings_detailed"), Button.inline("🔒 Security Settings", "security_settings_detailed")],
                [Button.inline("💰 Payment Settings", "payment_settings_detailed")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"Bot settings handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_toggle_setting(self, event, user, setting_type, setting_key):
        """Handle toggling individual settings"""
        try:
            logger.info(f"[ADMIN] Admin {user.telegram_user_id} toggling {setting_type}.{setting_key}")
            
            # Get current settings
            settings_doc = await self.db_connection.admin_settings.find_one({"type": f"{setting_type}_settings"})
            if settings_doc:
                current_settings = settings_doc.get("settings", {})
            else:
                # Use defaults from BotSettings
                from app.models.BotSettings import BotSettings
                default_attr = f"{setting_type.upper()}_SETTINGS"
                current_settings = getattr(BotSettings, default_attr, {})
            
            # Handle different setting types
            if setting_key == "max_login_attempts":
                # Cycle through attempt limits: 1, 3, 5, 10
                current = current_settings.get(setting_key, 3)
                new_value = {1: 3, 3: 5, 5: 10, 10: 1}.get(current, 3)
                current_settings[setting_key] = new_value
                logger.info(f"[ADMIN] Changed {setting_key} from {current} to {new_value}")
            else:
                # Toggle boolean settings
                current = current_settings.get(setting_key, True)
                current_settings[setting_key] = not current
                logger.info(f"[ADMIN] Toggled {setting_key} from {current} to {not current}")
            
            # Save updated settings
            await self.db_connection.admin_settings.update_one(
                {"type": f"{setting_type}_settings"},
                {
                    "$set": {
                        "settings": current_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            logger.info(f"[ADMIN] Settings updated successfully for {setting_type}")
            
            # Redirect back to appropriate settings page
            if setting_type == "payment":
                await self.handle_payment_settings(event)
            elif setting_type == "security":
                await self.handle_security_settings(event)
            else:
                await self.handle_bot_settings(event)
            
        except Exception as e:
            logger.error(f"[ADMIN] Toggle setting error for {user.telegram_user_id}: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_set_payment_setting(self, event, data):
        """Handle payment setting changes"""
        await self.edit_message(
            event,
            "💰 **Payment Settings**\n\nPayment settings management coming soon...",
            [[Button.inline("🔙 Back", "back_to_main")]]
        )
    
    async def handle_set_security_setting(self, event, data):
        """Handle security setting changes"""
        await self.edit_message(
            event,
            "🔒 **Security Settings**\n\nSecurity settings management coming soon...",
            [[Button.inline("🔙 Back", "back_to_main")]]
        )
    
    async def handle_payment_settings_detailed(self, event):
        """Handle detailed payment settings management"""
        try:
            # Get current payment settings
            settings = await self.db_connection.admin_settings.find_one({"type": "payment_settings"})
            if settings:
                payment_settings = settings.get("settings", {})
            else:
                payment_settings = {
                    "upi_enabled": True,
                    "crypto_enabled": True,
                    "razorpay_enabled": True,
                    "simulate_payments": True,
                    "payment_confirmation_required": True,
                    "payment_timeout_minutes": 15,
                    "auto_refund_enabled": True
                }
            
            settings_message = f"""
💰 **Payment Settings**

Configure payment methods and options:

💳 **UPI Payments:** {'Enabled' if payment_settings.get('upi_enabled', True) else 'Disabled'}
🔑 **Razorpay Gateway:** {'Enabled' if payment_settings.get('razorpay_enabled', True) else 'Disabled'}
₿ **Crypto Payments:** {'Enabled' if payment_settings.get('crypto_enabled', True) else 'Disabled'}
🧪 **Simulate Payments:** {'On' if payment_settings.get('simulate_payments', True) else 'Off'}
✅ **Require Admin Confirmation:** {'Yes' if payment_settings.get('payment_confirmation_required', True) else 'No'}
⏱️ **Payment Timeout:** {payment_settings.get('payment_timeout_minutes', 15)} minutes
🔄 **Auto Refund:** {'Enabled' if payment_settings.get('auto_refund_enabled', True) else 'Disabled'}

Click to configure:
            """
            
            buttons = [
                [Button.inline(f"💳 UPI ({'On' if payment_settings.get('upi_enabled', True) else 'Off'})", "setting_payment_upi_enabled"),
                 Button.inline(f"🔑 Razorpay ({'On' if payment_settings.get('razorpay_enabled', True) else 'Off'})", "setting_payment_razorpay_enabled")],
                [Button.inline(f"₿ Crypto ({'On' if payment_settings.get('crypto_enabled', True) else 'Off'})", "setting_payment_crypto_enabled"),
                 Button.inline(f"🧪 Simulate ({'On' if payment_settings.get('simulate_payments', True) else 'Off'})", "setting_payment_simulate_payments")],
                [Button.inline(f"✅ Admin Confirm ({'On' if payment_settings.get('payment_confirmation_required', True) else 'Off'})", "setting_payment_payment_confirmation_required"),
                 Button.inline(f"⏱️ Timeout ({payment_settings.get('payment_timeout_minutes', 15)}m)", "set_payment_timeout")],
                [Button.inline(f"🔄 Auto Refund ({'On' if payment_settings.get('auto_refund_enabled', True) else 'Off'})", "setting_payment_auto_refund_enabled")],
                [Button.inline("💵 Payment Fees", "payment_fees")],
                [Button.inline("🔧 Configure Gateways", "payment_gateways"), Button.inline("📊 Payment Dashboard", "payment_dashboard")],
                [Button.inline("🔙 Back", "bot_settings")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"Payment settings detailed handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_security_settings_detailed(self, event):
        """Handle detailed security settings management"""
        try:
            # Get current security settings
            settings = await self.db_connection.admin_settings.find_one({"type": "security_settings"})
            if settings:
                security_settings = settings.get("settings", {})
            else:
                security_settings = {
                    "session_encryption_enabled": True,
                    "otp_destroyer_auto_enable": True,
                    "admin_approval_required": True,
                    "suspicious_activity_detection": True,
                    "max_login_attempts": 3
                }
            
            settings_message = f"""
🔒 **Security Settings**

Configure security and protection features:

🔐 **Session Encryption:** {'Enabled' if security_settings.get('session_encryption_enabled', True) else 'Disabled'}
🚫 **Auto OTP Destroyer:** {'Enabled' if security_settings.get('otp_destroyer_auto_enable', True) else 'Disabled'}
✅ **Admin Approval Required:** {'Yes' if security_settings.get('admin_approval_required', True) else 'No'}
🔍 **Suspicious Activity Detection:** {'On' if security_settings.get('suspicious_activity_detection', True) else 'Off'}
🔢 **Max Login Attempts:** {security_settings.get('max_login_attempts', 3)}

Click to modify:
            """
            
            buttons = [
                [Button.inline(f"🔐 Encryption ({'On' if security_settings.get('session_encryption_enabled', True) else 'Off'})", "setting_security_session_encryption_enabled"),
                 Button.inline(f"🚫 OTP Destroyer ({'On' if security_settings.get('otp_destroyer_auto_enable', True) else 'Off'})", "setting_security_otp_destroyer_auto_enable")],
                [Button.inline(f"✅ Admin Approval ({'On' if security_settings.get('admin_approval_required', True) else 'Off'})", "setting_security_admin_approval_required"),
                 Button.inline(f"🔍 Activity Detection ({'On' if security_settings.get('suspicious_activity_detection', True) else 'Off'})", "setting_security_suspicious_activity_detection")],
                [Button.inline(f"🔢 Max Attempts ({security_settings.get('max_login_attempts', 3)})", "setting_security_max_login_attempts")],
                [Button.inline("🌐 Proxy Settings", "proxy_settings")],
                [Button.inline("🔙 Back", "bot_settings")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"Security settings detailed handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_seller_settings(self, event):
        """Handle seller bot settings"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "seller_settings"})
            if settings:
                seller_settings = settings.get("settings", {})
            else:
                seller_settings = {
                    "upload_enabled": True,
                    "otp_upload_enabled": True,
                    "tdata_upload_enabled": True,
                    "max_daily_uploads": 10,
                    "require_proxy": False,
                    "auto_verify": True
                }
            
            settings_message = f"""
📤 **Seller Bot Settings**

Configure seller bot features:

📤 **Upload Enabled:** {'Yes' if seller_settings.get('upload_enabled', True) else 'No'}
📱 **OTP Upload:** {'Enabled' if seller_settings.get('otp_upload_enabled', True) else 'Disabled'}
📦 **TData Upload:** {'Enabled' if seller_settings.get('tdata_upload_enabled', True) else 'Disabled'}
📊 **Max Daily Uploads:** {seller_settings.get('max_daily_uploads', 10)}
🌐 **Require Proxy:** {'Yes' if seller_settings.get('require_proxy', False) else 'No'}
🔍 **Auto Verify:** {'Enabled' if seller_settings.get('auto_verify', True) else 'Disabled'}

Click to modify:
            """
            
            buttons = [
                [Button.inline(f"📤 Upload ({'On' if seller_settings.get('upload_enabled', True) else 'Off'})", "setting_seller_upload_enabled"),
                 Button.inline(f"📱 OTP ({'On' if seller_settings.get('otp_upload_enabled', True) else 'Off'})", "setting_seller_otp_upload_enabled")],
                [Button.inline(f"📦 TData ({'On' if seller_settings.get('tdata_upload_enabled', True) else 'Off'})", "setting_seller_tdata_upload_enabled"),
                 Button.inline(f"📊 Max Uploads ({seller_settings.get('max_daily_uploads', 10)})", "set_seller_max_uploads")],
                [Button.inline(f"🌐 Require Proxy ({'On' if seller_settings.get('require_proxy', False) else 'Off'})", "setting_seller_require_proxy"),
                 Button.inline(f"🔍 Auto Verify ({'On' if seller_settings.get('auto_verify', True) else 'Off'})", "setting_seller_auto_verify")],
                [Button.inline("🔙 Back", "bot_settings")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"Seller settings handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_buyer_settings(self, event):
        """Handle buyer bot settings"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "buyer_settings"})
            if settings:
                buyer_settings = settings.get("settings", {})
            else:
                buyer_settings = {
                    "browse_enabled": True,
                    "purchase_enabled": True,
                    "preview_enabled": True,
                    "max_purchases_per_day": 5,
                    "require_balance": True,
                    "instant_delivery": True
                }
            
            settings_message = f"""
🛒 **Buyer Bot Settings**

Configure buyer bot features:

🔍 **Browse Enabled:** {'Yes' if buyer_settings.get('browse_enabled', True) else 'No'}
💰 **Purchase Enabled:** {'Yes' if buyer_settings.get('purchase_enabled', True) else 'No'}
👁️ **Preview Enabled:** {'Yes' if buyer_settings.get('preview_enabled', True) else 'No'}
📊 **Max Daily Purchases:** {buyer_settings.get('max_purchases_per_day', 5)}
💳 **Require Balance:** {'Yes' if buyer_settings.get('require_balance', True) else 'No'}
⚡ **Instant Delivery:** {'Enabled' if buyer_settings.get('instant_delivery', True) else 'Disabled'}

Click to modify:
            """
            
            buttons = [
                [Button.inline(f"🔍 Browse ({'On' if buyer_settings.get('browse_enabled', True) else 'Off'})", "setting_buyer_browse_enabled"),
                 Button.inline(f"💰 Purchase ({'On' if buyer_settings.get('purchase_enabled', True) else 'Off'})", "setting_buyer_purchase_enabled")],
                [Button.inline(f"👁️ Preview ({'On' if buyer_settings.get('preview_enabled', True) else 'Off'})", "setting_buyer_preview_enabled"),
                 Button.inline(f"📊 Max Purchases ({buyer_settings.get('max_purchases_per_day', 5)})", "set_buyer_max_purchases")],
                [Button.inline(f"💳 Require Balance ({'On' if buyer_settings.get('require_balance', True) else 'Off'})", "setting_buyer_require_balance"),
                 Button.inline(f"⚡ Instant Delivery ({'On' if buyer_settings.get('instant_delivery', True) else 'Off'})", "setting_buyer_instant_delivery")],
                [Button.inline("🔙 Back", "bot_settings")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"Buyer settings handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_general_settings_detailed(self, event):
        """Handle general settings management"""
        try:
            # Get current general settings
            settings = await self.db_connection.admin_settings.find_one({"type": "general_settings"})
            if settings:
                general_settings = settings.get("settings", {})
            else:
                general_settings = {
                    "maintenance_mode": False,
                    "welcome_message_enabled": True,
                    "tos_acceptance_required": True,
                    "rate_limiting_enabled": True,
                    "logging_level": "INFO"
                }
            
            settings_message = f"""
⚙️ **General Settings**

Configure system-wide settings:

🔧 **Maintenance Mode:** {'On' if general_settings.get('maintenance_mode', False) else 'Off'}
👋 **Welcome Messages:** {'Enabled' if general_settings.get('welcome_message_enabled', True) else 'Disabled'}
📋 **ToS Required:** {'Yes' if general_settings.get('tos_acceptance_required', True) else 'No'}
🔄 **Rate Limiting:** {'Enabled' if general_settings.get('rate_limiting_enabled', True) else 'Disabled'}
📝 **Logging Level:** {general_settings.get('logging_level', 'INFO')}

Click to modify:
            """
            
            buttons = [
                [Button.inline(f"🔧 Maintenance ({'On' if general_settings.get('maintenance_mode', False) else 'Off'})", "setting_general_maintenance_mode"),
                 Button.inline(f"👋 Welcome ({'On' if general_settings.get('welcome_message_enabled', True) else 'Off'})", "setting_general_welcome_message_enabled")],
                [Button.inline(f"📋 ToS Required ({'On' if general_settings.get('tos_acceptance_required', True) else 'Off'})", "setting_general_tos_acceptance_required"),
                 Button.inline(f"🔄 Rate Limiting ({'On' if general_settings.get('rate_limiting_enabled', True) else 'Off'})", "setting_general_rate_limiting_enabled")],
                [Button.inline("🔙 Back", "bot_settings")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"General settings detailed handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_payment_settings(self, event):
        """Handle payment settings from main dashboard"""
        await self.handle_payment_settings_detailed(event)
    
    async def handle_security_settings(self, event):
        """Handle security settings from main dashboard"""
        await self.handle_security_settings_detailed(event)
    
    async def handle_country_pricing(self, event, country):
        """Handle pricing for a specific country with buy/sell prices"""
        try:
            # Get current prices for country
            price_doc = await self.db_connection.admin_settings.find_one({"type": "price_table"})
            if price_doc:
                prices = price_doc.get("prices", {})
            else:
                prices = {}
            
            country_prices = prices.get(country, {"2025": {"buy": 30, "sell": 40}, "2024": {"buy": 25, "sell": 35}, "2023": {"buy": 20, "sell": 30}})
            
            price_message = f"🌍 **{country} Pricing**\n\nBuy/Sell prices by creation year:\n\n"
            
            for year, price_data in sorted(country_prices.items(), reverse=True):
                if isinstance(price_data, dict):
                    buy_price = price_data.get('buy', 30)
                    sell_price = price_data.get('sell', 40)
                    profit = sell_price - buy_price
                    price_message += f"📅 **{year}**:\n"
                    price_message += f"   Buy: ₹{buy_price} | Sell: ₹{sell_price} | Profit: ₹{profit}\n\n"
                else:
                    # Legacy format
                    price_message += f"📅 **{year}**: ₹{price_data} (Legacy)\n\n"
            
            buttons = []
            for year in sorted(country_prices.keys(), reverse=True):
                if isinstance(country_prices[year], dict):
                    buy_price = country_prices[year].get('buy', 30)
                    sell_price = country_prices[year].get('sell', 40)
                    buttons.append([Button.inline(f"📅 {year} (Buy ₹{buy_price} | Sell ₹{sell_price})", f"price_year_{country}_{year}")])
                else:
                    buttons.append([Button.inline(f"📅 {year} (₹{country_prices[year]})", f"price_year_{country}_{year}")])
            
            buttons.extend([
                [Button.inline("➕ Add Year", f"add_year_{country}")],
                [Button.inline("🔙 Back", "manage_prices")]
            ])
            
            await self.edit_message(event, price_message, buttons)
            
        except Exception as e:
            logger.error(f"Country pricing handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_year_pricing(self, event, country, year):
        """Handle pricing for a specific country and year with buy/sell toggle"""
        try:
            # Get current prices
            price_doc = await self.db_connection.admin_settings.find_one({"type": "price_table"})
            if price_doc:
                prices = price_doc.get("prices", {})
            else:
                prices = {}
            
            if country not in prices:
                prices[country] = {}
            
            current_data = prices[country].get(year, {"buy": 30, "sell": 40})
            if not isinstance(current_data, dict):
                # Convert legacy format
                current_data = {"buy": int(current_data * 0.75), "sell": current_data}
            
            # Show pricing options
            buy_price = current_data.get('buy', 30)
            sell_price = current_data.get('sell', 40)
            profit = sell_price - buy_price
            
            price_message = f"📅 **{country} {year} Pricing**\n\nCurrent prices:\n"
            price_message += f"💰 Buy Price: ₹{buy_price}\n"
            price_message += f"💲 Sell Price: ₹{sell_price}\n"
            price_message += f"💵 Profit: ₹{profit}\n\n"
            price_message += "Click to adjust prices:"
            
            buttons = [
                [Button.inline(f"💰 Buy Price (₹{buy_price})", f"adjust_buy_{country}_{year}"),
                 Button.inline(f"💲 Sell Price (₹{sell_price})", f"adjust_sell_{country}_{year}")],
                [Button.inline("🔙 Back", f"price_country_{country}")]
            ]
            
            await self.edit_message(event, price_message, buttons)
            
        except Exception as e:
            logger.error(f"Year pricing handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_add_country(self, event):
        """Handle adding a new country manually"""
        await self.edit_message(
            event,
            "➕ **Add New Country**\n\nSend country name to add pricing for it.\n\n**Format:** Country Name\n**Example:** India\n\nSend the country name:",
            [[Button.inline("❌ Cancel", "manage_prices")]]
        )
        
        # Set admin state for country input
        user = await self.get_or_create_user(event)
        await self.db_connection.users.update_one(
            {"telegram_user_id": user.telegram_user_id},
            {"$set": {"admin_state": "awaiting_country_name"}}
        )
    
    async def handle_adjust_buy_price(self, event, country, year):
        """Handle adjusting buy price with text input"""
        try:
            # Get current buy price
            price_doc = await self.db_connection.admin_settings.find_one({"type": "price_table"})
            if price_doc:
                prices = price_doc.get("prices", {})
            else:
                prices = {}
            
            current_data = prices.get(country, {}).get(year, {"buy": 30, "sell": 40})
            if not isinstance(current_data, dict):
                current_data = {"buy": int(current_data * 0.75), "sell": current_data}
            
            current_buy = current_data.get('buy', 30)
            
            await self.edit_message(
                event,
                f"💰 **Change Buy Price for {country} {year}**\n\nCurrent buy price: ₹{current_buy}\n\nSend new buy price:",
                [[Button.inline("❌ Cancel", f"price_year_{country}_{year}")]]
            )
            
            # Set admin state
            user = await self.get_or_create_user(event)
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"admin_state": f"buy_price_{country}_{year}"}}
            )
            
        except Exception as e:
            logger.error(f"Adjust buy price error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_adjust_sell_price(self, event, country, year):
        """Handle adjusting sell price with text input"""
        try:
            # Get current sell price
            price_doc = await self.db_connection.admin_settings.find_one({"type": "price_table"})
            if price_doc:
                prices = price_doc.get("prices", {})
            else:
                prices = {}
            
            current_data = prices.get(country, {}).get(year, {"buy": 30, "sell": 40})
            if not isinstance(current_data, dict):
                current_data = {"buy": int(current_data * 0.75), "sell": current_data}
            
            current_sell = current_data.get('sell', 40)
            
            await self.edit_message(
                event,
                f"💲 **Change Sell Price for {country} {year}**\n\nCurrent sell price: ₹{current_sell}\n\nSend new sell price:",
                [[Button.inline("❌ Cancel", f"price_year_{country}_{year}")]]
            )
            
            # Set admin state
            user = await self.get_or_create_user(event)
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"admin_state": f"sell_price_{country}_{year}"}}
            )
            
        except Exception as e:
            logger.error(f"Adjust sell price error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_text(self, event):
        """Handle text messages for admin input"""
        try:
            logger.info(f"[ADMIN] Text handler called for user {event.sender_id} with text: '{event.text}'")
            
            # Check admin access
            is_admin, user = await self.check_admin_access(event)
            if not is_admin:
                logger.info(f"[ADMIN] Access denied for user {event.sender_id}")
                return
            
            # Get admin state
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
            admin_state = user_doc.get("admin_state") if user_doc else None
            
            logger.info(f"[ADMIN] Admin state for user {user.telegram_user_id}: '{admin_state}'")
            
            if not admin_state:
                logger.info(f"[ADMIN] No admin state found for user {user.telegram_user_id}")
                return
            
            text_value = event.text.strip()
            logger.info(f"[ADMIN] Processing text '{text_value}' for state '{admin_state}'")
            
            if admin_state == "awaiting_country_name":
                await self.process_country_name(event, user, text_value)
            elif admin_state.startswith("setting_"):
                await self.process_setting_value(event, user, admin_state, text_value)
            elif admin_state.startswith("limit_"):
                await self.process_limit_value(event, user, admin_state, text_value)
            elif admin_state.startswith("upload_"):
                await self.process_upload_value(event, user, admin_state, text_value)
            elif admin_state.startswith("payment_"):
                await self.process_payment_value(event, user, admin_state, text_value)
            elif admin_state.startswith("security_"):
                await self.process_security_value(event, user, admin_state, text_value)
            elif admin_state.startswith("buy_price_"):
                await self.process_buy_price(event, user, admin_state, text_value)
            elif admin_state.startswith("sell_price_"):
                await self.process_sell_price(event, user, admin_state, text_value)
            elif admin_state == "upi_vpa":
                await self.process_upi_vpa(event, user, text_value)
            elif admin_state == "upi_name":
                await self.process_upi_name(event, user, text_value)
            elif admin_state == "razorpay_key_id":
                await self.process_razorpay_key_id(event, user, text_value)
            elif admin_state == "razorpay_key_secret":
                await self.process_razorpay_key_secret(event, user, text_value)
            elif admin_state == "razorpay_webhook_secret":
                await self.process_razorpay_webhook_secret(event, user, text_value)
            elif admin_state == "crypto_wallet":
                await self.process_crypto_wallet(event, user, text_value)
            elif admin_state == "crypto_api_key":
                await self.process_crypto_api_key(event, user, text_value)
            elif admin_state.startswith("payment_timeout"):
                await self.process_payment_timeout(event, user, text_value)
            elif admin_state.startswith("approve_upi_amount_"):
                order_id = admin_state.split("_", 3)[3]
                logger.info(f"[ADMIN] Processing UPI approval amount for order {order_id} with amount {text_value}")
                await self.process_upi_approval_amount(event, user, order_id, text_value)
            elif admin_state == "awaiting_proxy_config":
                await proxy_handlers.handle_proxy_config_input(self, event, user)
            else:
                logger.warning(f"[ADMIN] Unhandled admin state: '{admin_state}' for user {user.telegram_user_id}")
                await self.send_message(event.chat_id, "❌ Unknown command state. Please try again.")
            
        except Exception as e:
            logger.error(f"[ADMIN] Text handler error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to process input. Please try again.")
    
    async def process_setting_value(self, event, user, admin_state, text_value):
        """Process setting value input"""
        try:
            # Clear admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            # Parse admin state: setting_type_key
            parts = admin_state.split("_", 2)
            setting_type = parts[1]
            setting_key = parts[2]
            
            # Convert value based on setting type
            if setting_key in ["enabled", "required", "auto_enable", "detection"]:
                # Boolean values
                value = text_value.lower() in ['true', '1', 'yes', 'on', 'enable', 'enabled']
            elif setting_key in ["attempts", "timeout", "limit", "max"]:
                # Numeric values
                try:
                    value = int(text_value)
                except ValueError:
                    await self.send_message(event.chat_id, "❌ Please enter a valid number.")
                    return
            else:
                # String values
                value = text_value
            
            # Get current settings
            settings_doc = await self.db_connection.admin_settings.find_one({"type": f"{setting_type}_settings"})
            if settings_doc:
                current_settings = settings_doc.get("settings", {})
            else:
                current_settings = {}
            
            # Update setting
            current_settings[setting_key] = value
            
            # Save to database
            await self.db_connection.admin_settings.update_one(
                {"type": f"{setting_type}_settings"},
                {
                    "$set": {
                        "settings": current_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                f"✅ **Setting Updated**\n\n{setting_key.replace('_', ' ').title()}: `{value}`",
                buttons=[[Button.inline("🔙 Back", f"{setting_type}_settings_detailed")]]
            )
            
        except Exception as e:
            logger.error(f"Process setting value error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update setting. Please try again.")
    
    async def process_limit_value(self, event, user, admin_state, text_value):
        """Process limit value input"""
        try:
            # Clear admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            limit_type = admin_state.split("_", 1)[1]
            
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "verification_limits"})
            if settings:
                limits = settings.get("limits", {})
            else:
                limits = {}
            
            limit_map = {
                "contacts": "max_contacts",
                "bots": "max_bot_chats", 
                "sessions": "max_active_sessions",
                "groups": "max_groups_owned",
                "spam": "require_spam_check",
                "zero_contacts": "require_zero_contacts"
            }
            
            actual_key = limit_map.get(limit_type, limit_type)
            
            # Convert value
            if actual_key in ["require_spam_check", "require_zero_contacts"]:
                value = text_value.lower() in ['true', '1', 'yes', 'on', 'enable', 'enabled']
            else:
                try:
                    value = int(text_value)
                    if value < 0:
                        await self.send_message(event.chat_id, "❌ Please enter a positive number.")
                        return
                except ValueError:
                    await self.send_message(event.chat_id, "❌ Please enter a valid number.")
                    return
            
            limits[actual_key] = value
            
            # Save to database
            await self.db_connection.admin_settings.update_one(
                {"type": "verification_limits"},
                {"$set": {"limits": limits, "updated_at": utc_now()}},
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                f"✅ **Limit Updated**\n\n{actual_key.replace('_', ' ').title()}: `{value}`",
                buttons=[[Button.inline("🔙 Back", "verification_settings")]]
            )
            
        except Exception as e:
            logger.error(f"Process limit value error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update limit. Please try again.")
    
    async def process_upload_value(self, event, user, admin_state, text_value):
        """Process upload setting value input"""
        try:
            # Clear admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            setting_type = admin_state.split("_", 1)[1]
            
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "upload_limits"})
            if settings:
                limits = settings.get("limits", {})
            else:
                limits = {}
            
            setting_map = {"enabled": "enabled", "max": "max_per_day"}
            actual_key = setting_map.get(setting_type, setting_type)
            
            # Convert value
            if actual_key == "enabled":
                value = text_value.lower() in ['true', '1', 'yes', 'on', 'enable', 'enabled']
            else:
                try:
                    value = int(text_value)
                    if value < 0:
                        await self.send_message(event.chat_id, "❌ Please enter a positive number.")
                        return
                except ValueError:
                    await self.send_message(event.chat_id, "❌ Please enter a valid number.")
                    return
            
            limits[actual_key] = value
            
            # Save to database
            await self.db_connection.admin_settings.update_one(
                {"type": "upload_limits"},
                {"$set": {"limits": limits, "updated_at": utc_now()}},
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                f"✅ **Upload Setting Updated**\n\n{actual_key.replace('_', ' ').title()}: `{value}`",
                buttons=[[Button.inline("🔙 Back", "upload_limits")]]
            )
            
        except Exception as e:
            logger.error(f"Process upload value error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update upload setting. Please try again.")
    
    async def process_payment_value(self, event, user, admin_state, text_value):
        """Process payment setting value input"""
        try:
            # Clear admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            setting_type = admin_state.split("_", 1)[1]
            
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "payment_settings"})
            if settings:
                payment_settings = settings.get("settings", {})
            else:
                payment_settings = {}
            
            # Convert value (most payment settings are boolean)
            if setting_type in ["enabled", "required", "simulate", "confirmation_required", "payment_enabled", "otp_payment_enabled", "upi_enabled", "crypto_enabled"]:
                value = text_value.lower() in ['true', '1', 'yes', 'on', 'enable', 'enabled']
            elif setting_type in ["timeout", "limit", "amount"]:
                try:
                    value = int(text_value)
                    if value < 0:
                        await self.send_message(event.chat_id, "❌ Please enter a positive number.")
                        return
                except ValueError:
                    await self.send_message(event.chat_id, "❌ Please enter a valid number.")
                    return
            else:
                value = text_value
            
            payment_settings[setting_type] = value
            
            # Save to database
            await self.db_connection.admin_settings.update_one(
                {"type": "payment_settings"},
                {
                    "$set": {
                        "settings": payment_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                f"✅ **Payment Setting Updated**\n\n{setting_type.replace('_', ' ').title()}: `{value}`",
                buttons=[[Button.inline("🔙 Back", "payment_settings_detailed")]]
            )
            
        except Exception as e:
            logger.error(f"Process payment value error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update payment setting. Please try again.")
    
    async def process_security_value(self, event, user, admin_state, text_value):
        """Process security setting value input"""
        try:
            # Clear admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            setting_type = admin_state.split("_", 1)[1]
            
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "security_settings"})
            if settings:
                security_settings = settings.get("settings", {})
            else:
                security_settings = {}
            
            # Convert value
            if setting_type in ["enabled", "required", "auto_enable", "detection", "session_encryption_enabled", "otp_destroyer_auto_enable", "admin_approval_required", "suspicious_activity_detection"]:
                value = text_value.lower() in ['true', '1', 'yes', 'on', 'enable', 'enabled']
            elif setting_type in ["attempts", "timeout", "limit", "max_login_attempts"]:
                try:
                    value = int(text_value)
                    if value < 0:
                        await self.send_message(event.chat_id, "❌ Please enter a positive number.")
                        return
                except ValueError:
                    await self.send_message(event.chat_id, "❌ Please enter a valid number.")
                    return
            else:
                value = text_value
            
            security_settings[setting_type] = value
            
            # Save to database
            await self.db_connection.admin_settings.update_one(
                {"type": "security_settings"},
                {
                    "$set": {
                        "settings": security_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                f"✅ **Security Setting Updated**\n\n{setting_type.replace('_', ' ').title()}: `{value}`",
                buttons=[[Button.inline("🔙 Back", "security_settings_detailed")]]
            )
            
        except Exception as e:
            logger.error(f"Process security value error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update security setting. Please try again.")
    
    async def process_country_name(self, event, user, country_name):
        """Process country name input and add to pricing"""
        try:
            # Clear admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            # Validate country name
            if not country_name or len(country_name) < 2:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Country Name**\n\nPlease provide a valid country name."
                )
                return
            
            # Capitalize country name
            country_name = country_name.title()
            
            # Get current prices
            price_doc = await self.db_connection.admin_settings.find_one({"type": "price_table"})
            if price_doc:
                prices = price_doc.get("prices", {})
            else:
                prices = {}
            
            # Add country with default pricing
            if country_name not in prices:
                prices[country_name] = {
                    "2025": {"buy": 30, "sell": 40},
                    "2024": {"buy": 25, "sell": 35},
                    "2023": {"buy": 20, "sell": 30}
                }
                
                # Save to database
                await self.db_connection.admin_settings.update_one(
                    {"type": "price_table"},
                    {"$set": {"prices": prices, "updated_at": utc_now()}},
                    upsert=True
                )
                
                await self.send_message(
                    event.chat_id,
                    f"✅ **Country Added Successfully!**\n\n🌍 **{country_name}** has been added with default pricing:\n\n📅 **2025**: Buy ₹30 | Sell ₹40\n📅 **2024**: Buy ₹25 | Sell ₹35\n📅 **2023**: Buy ₹20 | Sell ₹30\n\nYou can now adjust the prices as needed.",
                    buttons=[[Button.inline(f"🌍 Configure {country_name}", f"price_country_{country_name}")], [Button.inline("🔙 Back to Pricing", "manage_prices")]]
                )
            else:
                await self.send_message(
                    event.chat_id,
                    f"⚠️ **Country Already Exists**\n\n🌍 **{country_name}** is already in the pricing table.",
                    buttons=[[Button.inline(f"🌍 Configure {country_name}", f"price_country_{country_name}")], [Button.inline("🔙 Back to Pricing", "manage_prices")]]
                )
            
        except Exception as e:
            logger.error(f"Process country name error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to add country. Please try again.")
    
    async def process_buy_price(self, event, user, admin_state, text_value):
        """Process buy price input"""
        try:
            # Clear admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            # Parse admin state: buy_price_country_year
            parts = admin_state.split("_", 3)
            country = parts[2]
            year = parts[3]
            
            # Validate price
            try:
                new_buy_price = int(text_value)
                if new_buy_price < 1 or new_buy_price > 1000:
                    await self.send_message(event.chat_id, "❌ Price must be between ₹1 and ₹1000.")
                    return
            except ValueError:
                await self.send_message(event.chat_id, "❌ Please enter a valid number.")
                return
            
            # Get current prices
            price_doc = await self.db_connection.admin_settings.find_one({"type": "price_table"})
            if price_doc:
                prices = price_doc.get("prices", {})
            else:
                prices = {}
            
            if country not in prices:
                prices[country] = {}
            
            current_data = prices[country].get(year, {"buy": 30, "sell": 40})
            if not isinstance(current_data, dict):
                current_data = {"buy": int(current_data * 0.75), "sell": current_data}
            
            # Update buy price
            current_data['buy'] = new_buy_price
            prices[country][year] = current_data
            
            # Save to database
            await self.db_connection.admin_settings.update_one(
                {"type": "price_table"},
                {"$set": {"prices": prices, "updated_at": utc_now()}},
                upsert=True
            )
            
            profit = current_data.get('sell', 40) - new_buy_price
            await self.send_message(
                event.chat_id,
                f"✅ **Buy Price Updated**\n\n{country} {year}: Buy ₹{new_buy_price} | Sell ₹{current_data.get('sell', 40)} | Profit ₹{profit}",
                buttons=[[Button.inline("🔙 Back", f"price_year_{country}_{year}")]]
            )
            
        except Exception as e:
            logger.error(f"Process buy price error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update buy price. Please try again.")
    
    async def process_sell_price(self, event, user, admin_state, text_value):
        """Process sell price input"""
        try:
            # Clear admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            # Parse admin state: sell_price_country_year
            parts = admin_state.split("_", 3)
            country = parts[2]
            year = parts[3]
            
            # Validate price
            try:
                new_sell_price = int(text_value)
                if new_sell_price < 1 or new_sell_price > 1000:
                    await self.send_message(event.chat_id, "❌ Price must be between ₹1 and ₹1000.")
                    return
            except ValueError:
                await self.send_message(event.chat_id, "❌ Please enter a valid number.")
                return
            
            # Get current prices
            price_doc = await self.db_connection.admin_settings.find_one({"type": "price_table"})
            if price_doc:
                prices = price_doc.get("prices", {})
            else:
                prices = {}
            
            if country not in prices:
                prices[country] = {}
            
            current_data = prices[country].get(year, {"buy": 30, "sell": 40})
            if not isinstance(current_data, dict):
                current_data = {"buy": int(current_data * 0.75), "sell": current_data}
            
            # Update sell price
            current_data['sell'] = new_sell_price
            prices[country][year] = current_data
            
            # Save to database
            await self.db_connection.admin_settings.update_one(
                {"type": "price_table"},
                {"$set": {"prices": prices, "updated_at": utc_now()}},
                upsert=True
            )
            
            profit = new_sell_price - current_data.get('buy', 30)
            await self.send_message(
                event.chat_id,
                f"✅ **Sell Price Updated**\n\n{country} {year}: Buy ₹{current_data.get('buy', 30)} | Sell ₹{new_sell_price} | Profit ₹{profit}",
                buttons=[[Button.inline("🔙 Back", f"price_year_{country}_{year}")]]
            )
            
        except Exception as e:
            logger.error(f"Process sell price error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update sell price. Please try again.")
    
    async def handle_upi_settings(self, event):
        """Handle UPI settings management"""
        try:
            # Get current UPI settings
            settings = await self.db_connection.admin_settings.find_one({"type": "upi_settings"})
            if settings:
                upi_settings = settings.get("settings", {})
            else:
                upi_settings = {
                    "merchant_vpa": "",
                    "merchant_name": "",
                    "enabled": True
                }
            
            settings_message = f"""
💳 **UPI Payment Settings**

Configure UPI payment details:

🏦 **Merchant UPI ID:** {upi_settings.get('merchant_vpa', 'Not set') or 'Not configured'}
🏢 **Merchant Name:** {upi_settings.get('merchant_name', 'Not set') or 'Not configured'}
🔄 **UPI Enabled:** {'Yes' if upi_settings.get('enabled', True) else 'No'}

**Note:** These details appear in UPI payment requests and QR codes.

Click to modify:
            """
            
            buttons = [
                [Button.inline(f"🏦 UPI ID ({upi_settings.get('merchant_vpa', 'Not set')})", "set_upi_vpa")],
                [Button.inline(f"🏢 Name ({upi_settings.get('merchant_name', 'Not set')})", "set_upi_name")],
                [Button.inline(f"🔄 Enable/Disable ({'On' if upi_settings.get('enabled', True) else 'Off'})", "set_upi_enabled")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"UPI settings handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_set_upi_setting(self, event, user, setting_type):
        """Handle UPI setting modification"""
        try:
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "upi_settings"})
            if settings:
                upi_settings = settings.get("settings", {})
            else:
                upi_settings = {
                    "merchant_vpa": "",
                    "merchant_name": "",
                    "enabled": True
                }
            
            if setting_type == "vpa":
                current_vpa = upi_settings.get('merchant_vpa', 'Not set')
                await self.edit_message(
                    event,
                    f"🏦 **Set UPI ID**\n\nCurrent UPI ID: `{current_vpa}`\n\nEnter new UPI ID:\n\n**Examples:**\n• yourname@paytm\n• business@phonepe\n• merchant@googlepay",
                    [[Button.inline("❌ Cancel", "upi_settings")]]
                )
                
                # Set admin state
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$set": {"admin_state": "upi_vpa"}}
                )
                
            elif setting_type == "name":
                current_name = upi_settings.get('merchant_name', 'Not set')
                await self.edit_message(
                    event,
                    f"🏢 **Set Merchant Name**\n\nCurrent name: `{current_name}`\n\nEnter new merchant name:\n\n**Examples:**\n• TelegramMarketplace\n• Your Business Name\n• Account Store",
                    [[Button.inline("❌ Cancel", "upi_settings")]]
                )
                
                # Set admin state
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$set": {"admin_state": "upi_name"}}
                )
                
            elif setting_type == "enabled":
                # Toggle enabled status
                current_enabled = upi_settings.get('enabled', True)
                upi_settings['enabled'] = not current_enabled
                
                # Save to database
                await self.db_connection.admin_settings.update_one(
                    {"type": "upi_settings"},
                    {
                        "$set": {
                            "settings": upi_settings,
                            "updated_at": utc_now(),
                            "updated_by": user.telegram_user_id
                        }
                    },
                    upsert=True
                )
                
                status = "enabled" if not current_enabled else "disabled"
                await self.edit_message(
                    event,
                    f"✅ **UPI {status.title()}**\n\nUPI payments have been {status}.",
                    [[Button.inline("🔙 Back", "upi_settings")]]
                )
            
        except Exception as e:
            logger.error(f"Set UPI setting error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def notify_seller_approval(self, seller_id: int, account_id: str, price: float):
        """Notify seller of account approval"""
        try:
            # This would send notification via seller bot
            logger.info(f"Notifying seller {seller_id} of account {account_id} approval (${price})")
        except Exception as e:
            logger.error(f"Failed to notify seller: {str(e)}")
    
    async def notify_seller_rejection(self, seller_id: int, account_id: str, reason: str):
        """Notify seller of account rejection"""
        try:
            # This would send notification via seller bot
            logger.info(f"Notifying seller {seller_id} of account {account_id} rejection: {reason}")
        except Exception as e:
            logger.error(f"Failed to notify seller: {str(e)}")
    
    async def deliver_account_to_buyer(self, buyer_id: int, account: dict):
        """Deliver account session to buyer"""
        try:
            # This would send the session details via buyer bot
            logger.info(f"Delivering account {account['_id']} to buyer {buyer_id}")
        except Exception as e:
            logger.error(f"Failed to deliver account: {str(e)}")
    
    async def prompt_for_setting_value(self, event, user, setting_type, setting_key):
        """Prompt admin to enter new value for a setting"""
        try:
            # Get current value
            settings_doc = await self.db_connection.admin_settings.find_one({"type": f"{setting_type}_settings"})
            if settings_doc:
                current_settings = settings_doc.get("settings", {})
            else:
                from app.models.bot_settings import BotSettings
                default_attr = f"{setting_type.upper()}_SETTINGS"
                current_settings = getattr(BotSettings, default_attr, {})
            
            current_value = current_settings.get(setting_key, "Not set")
            
            await self.edit_message(
                event,
                f"⚙️ **Change {setting_key.replace('_', ' ').title()}**\n\nCurrent value: `{current_value}`\n\nSend new value:",
                [[Button.inline("❌ Cancel", f"{setting_type}_settings_detailed")]]
            )
            
            # Set admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"admin_state": f"setting_{setting_type}_{setting_key}"}}
            )
            
        except Exception as e:
            logger.error(f"Prompt for setting value error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def prompt_for_limit_value(self, event, limit_type):
        """Prompt admin to enter new limit value"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "verification_limits"})
            if settings:
                limits = settings.get("limits", {})
            else:
                limits = {"max_contacts": 5, "max_bot_chats": 3, "max_active_sessions": 3, "max_groups_owned": 10}
            
            limit_map = {
                "contacts": "max_contacts",
                "bots": "max_bot_chats", 
                "sessions": "max_active_sessions",
                "groups": "max_groups_owned",
                "spam": "require_spam_check",
                "zero_contacts": "require_zero_contacts"
            }
            
            actual_key = limit_map.get(limit_type, limit_type)
            current_value = limits.get(actual_key, "Not set")
            
            await self.edit_message(
                event,
                f"📏 **Change {limit_type.replace('_', ' ').title()} Limit**\n\nCurrent value: `{current_value}`\n\nSend new value:",
                [[Button.inline("❌ Cancel", "verification_settings")]]
            )
            
            # Set admin state
            user = await self.get_or_create_user(event)
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"admin_state": f"limit_{limit_type}"}}
            )
            
        except Exception as e:
            logger.error(f"Prompt for limit value error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def prompt_for_upload_value(self, event, setting_type):
        """Prompt admin to enter new upload setting value"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "upload_limits"})
            if settings:
                limits = settings.get("limits", {})
            else:
                limits = {"enabled": False, "max_per_day": 999}
            
            setting_map = {"enabled": "enabled", "max": "max_per_day"}
            actual_key = setting_map.get(setting_type, setting_type)
            current_value = limits.get(actual_key, "Not set")
            
            await self.edit_message(
                event,
                f"📤 **Change Upload {setting_type.replace('_', ' ').title()}**\n\nCurrent value: `{current_value}`\n\nSend new value:",
                [[Button.inline("❌ Cancel", "upload_limits")]]
            )
            
            # Set admin state
            user = await self.get_or_create_user(event)
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"admin_state": f"upload_{setting_type}"}}
            )
            
        except Exception as e:
            logger.error(f"Prompt for upload value error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def prompt_for_payment_value(self, event, setting_type):
        """Prompt admin to enter new payment setting value"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "payment_settings"})
            if settings:
                payment_settings = settings.get("settings", {})
            else:
                payment_settings = {"upi_enabled": True, "crypto_enabled": True}
            
            current_value = payment_settings.get(setting_type, "Not set")
            
            await self.edit_message(
                event,
                f"💰 **Change Payment {setting_type.replace('_', ' ').title()}**\n\nCurrent value: `{current_value}`\n\nSend new value:",
                [[Button.inline("❌ Cancel", "payment_settings_detailed")]]
            )
            
            # Set admin state
            user = await self.get_or_create_user(event)
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"admin_state": f"payment_{setting_type}"}}
            )
            
        except Exception as e:
            logger.error(f"Prompt for payment value error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def prompt_for_security_value(self, event, setting_type):
        """Prompt admin to enter new security setting value"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "security_settings"})
            if settings:
                security_settings = settings.get("settings", {})
            else:
                security_settings = {"session_encryption_enabled": True, "max_login_attempts": 3}
            
            current_value = security_settings.get(setting_type, "Not set")
            
            await self.edit_message(
                event,
                f"🔒 **Change Security {setting_type.replace('_', ' ').title()}**\n\nCurrent value: `{current_value}`\n\nSend new value:",
                [[Button.inline("❌ Cancel", "security_settings_detailed")]]
            )
            
            # Set admin state
            user = await self.get_or_create_user(event)
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"admin_state": f"security_{setting_type}"}}
            )
            
        except Exception as e:
            logger.error(f"Prompt for security value error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def get_admin_stats(self):
        """Get admin statistics"""
        try:
            stats = {
                'accounts': {
                    'pending': await self.db_connection.accounts.count_documents({'status': 'pending'}),
                    'approved': await self.db_connection.accounts.count_documents({'status': 'approved'}),
                    'rejected': await self.db_connection.accounts.count_documents({'status': 'rejected'}),
                    'sold': await self.db_connection.accounts.count_documents({'status': 'sold'})
                },
                'listings': {
                    'active': await self.db_connection.listings.count_documents({'status': 'active'}),
                    'sold': await self.db_connection.listings.count_documents({'status': 'sold'})
                },
                'transactions': {
                    'pending': await self.db_connection.transactions.count_documents({'status': 'pending'}),
                    'confirmed': await self.db_connection.transactions.count_documents({'status': 'confirmed'})
                },
                'users': {
                    'total': await self.db_connection.users.count_documents({}),
                    'sellers': await self.db_connection.users.count_documents({'upload_count_today': {'$gt': 0}})
                }
            }
            return stats
        except Exception as e:
            logger.error(f"Failed to get admin stats: {str(e)}")
            return {'accounts': {}, 'listings': {}, 'transactions': {}, 'users': {}}
    
    async def handle_manual_review(self, event, user, account_id):
        """Handle manual review request"""
        await self.edit_message(
            event,
            "🔍 **Manual Review**\n\nManual review functionality coming soon...",
            [[Button.inline("🔙 Back", "review_accounts")]]
        )
    
    async def handle_set_price(self, event, user, account_id):
        """Handle setting custom price for account"""
        await self.edit_message(
            event,
            "💲 **Set Custom Price**\n\nCustom pricing functionality coming soon...",
            [[Button.inline("🔙 Back", "review_accounts")]]
        )
    
    async def handle_approve_payout(self, event, user, payout_id):
        """Handle payout approval"""
        await self.edit_message(
            event,
            "💸 **Approve Payout**\n\nPayout approval functionality coming soon...",
            [[Button.inline("🔙 Back", "approve_payouts")]]
        )
    
    async def handle_verify_account(self, event, user, account_id):
        """Handle account verification"""
        from app.services.VerificationService import VerificationService
        from app.utils.encryption import decrypt_session
        
        await self.edit_message(event, "🔍 **Running Verification**\n\nPlease wait...")
        
        try:
            account = await self.db_connection.accounts.find_one({"_id": ObjectId(account_id)})
            if not account:
                await self.edit_message(event, "❌ Account not found", [[Button.inline("🔙 Back", "review_accounts")]])
                return
            
            # Decrypt session string if encrypted
            session_string = account.get("session_string")
            if not session_string:
                await self.edit_message(event, "❌ No session string found", [[Button.inline("🔙 Back", "review_accounts")]])
                return
            
            # Try to decrypt if it's encrypted
            try:
                decrypted_session = decrypt_session(session_string)
                account_data = {**account, "session_string": decrypted_session}
            except:
                # If decryption fails, assume it's already decrypted
                account_data = account
            
            verification_service = VerificationService(self.db_connection)
            results = await verification_service.verify_account(account_data)
            
            if results.get("success"):
                score = results.get("score_percentage", 0)
                passed = results.get("passed", False)
                
                status_emoji = "✅" if passed else "⚠️"
                status_text = "PASSED" if passed else "FAILED"
                
                message = f"{status_emoji} **Verification Results**\n\n"
                message += f"**Score:** {score:.1f}% ({results['score']}/{results['max_score']})\n"
                message += f"**Status:** {status_text}\n\n"
                message += "**Checks:**\n"
                
                for check_name, check_data in results.get("checks", {}).items():
                    check_emoji = "✅" if check_data.get("passed") else "❌"
                    message += f"{check_emoji} {check_name.replace('_', ' ').title()}\n"
                
                message += "\n**Logs:**\n" + "\n".join(results.get("logs", [])[:10])
                
                await self.db_connection.accounts.update_one(
                    {"_id": ObjectId(account_id)},
                    {"$set": {"checks": results.get("checks", {}), "verification_logs": results.get("logs", [])}}
                )
            else:
                message = f"❌ **Verification Failed**\n\nError: {results.get('error', 'Unknown error')}"
            
            await self.edit_message(event, message, [[Button.inline("🔙 Back", "review_accounts")]])
            
        except Exception as e:
            logger.error(f"Verify account error: {str(e)}")
            await self.edit_message(event, f"❌ Error: {str(e)}", [[Button.inline("🔙 Back", "review_accounts")]])
    
    async def handle_auto_price(self, event, user, account_id):
        """Handle auto pricing"""
        await self.edit_message(
            event,
            "💰 **Auto Price**\n\nSetting automatic price based on market data...",
            [[Button.inline("🔙 Back", "review_accounts")]]
        )
    
    async def handle_quality_check(self, event, user, account_id):
        """Handle quality score check"""
        await self.edit_message(event, "📊 **Analyzing Quality**\n\nPlease wait...")
        
        try:
            account = await self.db_connection.accounts.find_one({"_id": ObjectId(account_id)})
            if not account:
                await self.edit_message(event, "❌ Account not found", [[Button.inline("🔙 Back", "review_accounts")]])
                return
            
            checks = account.get("checks", {})
            
            # Check if verification has been run
            if not checks:
                await self.edit_message(
                    event,
                    "⚠️ **No Verification Data**\n\nThis account hasn't been verified yet.\n\nPlease run 'Account Verification' first to generate quality data.",
                    [[Button.inline("🔍 Run Verification", f"admin_verify_{account_id}")], [Button.inline("🔙 Back", "review_accounts")]]
                )
                return
            
            # Use quality_score from account if available, otherwise calculate from checks
            if account.get("quality_score") is not None:
                quality_percentage = account.get("quality_score", 0)
            else:
                quality_score = 0
                max_quality = 100
                
                # Profile completeness (30 points)
                profile_check = checks.get("profile_completeness", {})
                if profile_check.get("passed"):
                    quality_score += 30
                elif profile_check.get("score", 0) >= 2:
                    quality_score += 15
                
                # Account age (20 points)
                age_check = checks.get("account_age", {})
                if age_check.get("passed"):
                    quality_score += 20
                elif age_check.get("estimated_days", 0) >= 7:
                    quality_score += 10
                
                # Clean status (25 points)
                if checks.get("spam_status", {}).get("passed"):
                    quality_score += 25
                
                # Activity (15 points)
                if checks.get("activity_patterns", {}).get("passed"):
                    quality_score += 15
                
                # Security (10 points)
                if checks.get("two_factor_auth", {}).get("passed"):
                    quality_score += 10
                
                quality_percentage = (quality_score / max_quality) * 100
            
            if quality_percentage >= 80:
                grade = "A+ (Excellent)"
                emoji = "🌟"
            elif quality_percentage >= 60:
                grade = "B (Good)"
                emoji = "✅"
            elif quality_percentage >= 40:
                grade = "C (Average)"
                emoji = "⚠️"
            else:
                grade = "D (Poor)"
                emoji = "❌"
            
            message = f"{emoji} **Quality Score Report**\n\n"
            message += f"**Overall Score:** {quality_percentage:.0f}/100\n"
            message += f"**Grade:** {grade}\n\n"
            message += f"**Breakdown:**\n"
            message += f"• Profile: {30 if checks.get('profile_completeness', {}).get('passed') else 0}/30\n"
            message += f"• Age: {20 if checks.get('account_age', {}).get('passed') else 0}/20\n"
            message += f"• Clean Status: {25 if checks.get('spam_status', {}).get('passed') else 0}/25\n"
            message += f"• Activity: {15 if checks.get('activity_patterns', {}).get('passed') else 0}/15\n"
            message += f"• Security: {10 if checks.get('two_factor_auth', {}).get('passed') else 0}/10\n"
            
            await self.edit_message(event, message, [[Button.inline("🔙 Back", "review_accounts")]])
            
        except Exception as e:
            logger.error(f"Quality check error: {str(e)}")
            await self.edit_message(event, f"❌ Error: {str(e)}", [[Button.inline("🔙 Back", "review_accounts")]])
    
    async def handle_security_check(self, event, user, account_id):
        """Handle security check"""
        await self.edit_message(event, "🛡️ **Running Security Analysis**\n\nPlease wait...")
        
        try:
            account = await self.db_connection.accounts.find_one({"_id": ObjectId(account_id)})
            if not account:
                await self.edit_message(event, "❌ Account not found", [[Button.inline("🔙 Back", "review_accounts")]])
                return
            
            checks = account.get("checks", {})
            
            # Check if verification has been run
            if not checks:
                await self.edit_message(
                    event,
                    "⚠️ **No Verification Data**\n\nThis account hasn't been verified yet.\n\nPlease run 'Account Verification' first to generate security data.",
                    [[Button.inline("🔍 Run Verification", f"admin_verify_{account_id}")], [Button.inline("🔙 Back", "review_accounts")]]
                )
                return
            
            security_issues = []
            security_warnings = []
            security_passed = []
            
            # Check spam status
            spam_check = checks.get("spam_status", {})
            if spam_check:
                if not spam_check.get("passed", True):
                    security_issues.append("❌ Account is spam-restricted")
                else:
                    security_passed.append("✅ No spam restrictions")
            else:
                security_passed.append("✅ No spam restrictions (not checked)")
            
            # Check 2FA
            twofa_check = checks.get("two_factor_auth", {})
            if twofa_check:
                if not twofa_check.get("passed", False):
                    security_warnings.append("⚠️ 2FA not enabled")
                else:
                    security_passed.append("✅ 2FA enabled")
            else:
                security_warnings.append("⚠️ 2FA not enabled")
            
            # Check contact count
            contacts = checks.get("contact_count", {})
            contact_value = contacts.get("value", 0)
            if contact_value > 10:
                security_warnings.append(f"⚠️ High contact count: {contact_value}")
            else:
                security_passed.append(f"✅ Contact count: {contact_value}")
            
            # Check owned groups
            owned = checks.get("owned_groups", {})
            owned_value = owned.get("value", 0)
            if owned_value > 5:
                security_warnings.append(f"⚠️ Owns {owned_value} groups/channels")
            else:
                security_passed.append(f"✅ Owned groups: {owned_value}")
            
            # Check bot interactions
            bots = checks.get("bot_chats", {})
            bot_value = bots.get("value", 0)
            if bot_value > 5:
                security_warnings.append(f"⚠️ Many bot interactions: {bot_value}")
            else:
                security_passed.append(f"✅ Bot chats: {bot_value}")
            
            # Check active sessions
            sessions = checks.get("active_sessions", {})
            session_value = sessions.get("value", 1)
            if session_value > 2:
                security_warnings.append(f"⚠️ Multiple active sessions: {session_value}")
            else:
                security_passed.append(f"✅ Active sessions: {session_value}")
            
            # Determine overall security level
            if len(security_issues) > 0:
                level = "🔴 HIGH RISK"
            elif len(security_warnings) > 2:
                level = "🟡 MEDIUM RISK"
            elif len(security_warnings) > 0:
                level = "🟢 LOW RISK"
            else:
                level = "🟢 SECURE"
            
            message = f"🛡️ **Security Analysis**\n\n"
            message += f"**Risk Level:** {level}\n\n"
            
            if security_issues:
                message += "**Critical Issues:**\n" + "\n".join(security_issues) + "\n\n"
            
            if security_warnings:
                message += "**Warnings:**\n" + "\n".join(security_warnings) + "\n\n"
            
            if security_passed:
                message += "**Passed Checks:**\n" + "\n".join(security_passed)
            
            await self.edit_message(event, message, [[Button.inline("🔙 Back", "review_accounts")]])
            
        except Exception as e:
            logger.error(f"Security check error: {str(e)}")
            await self.edit_message(event, f"❌ Error: {str(e)}", [[Button.inline("🔙 Back", "review_accounts")]])
    async def process_upi_vpa(self, event, user, text_value):
        """Process UPI VPA input"""
        try:
            # Clear admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            # Validate UPI VPA format
            if not text_value or "@" not in text_value:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid UPI ID**\n\nPlease enter a valid UPI ID (e.g., yourname@paytm)"
                )
                return
            
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "upi_settings"})
            if settings:
                upi_settings = settings.get("settings", {})
            else:
                upi_settings = {}
            
            # Update UPI VPA
            upi_settings["merchant_vpa"] = text_value.strip()
            
            # Save to database
            await self.db_connection.admin_settings.update_one(
                {"type": "upi_settings"},
                {
                    "$set": {
                        "settings": upi_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                f"✅ **UPI ID Updated**\n\nNew UPI ID: `{text_value.strip()}`",
                buttons=[[Button.inline("🔙 Back", "upi_settings")]]
            )
            
        except Exception as e:
            logger.error(f"Process UPI VPA error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update UPI ID. Please try again.")

    async def process_upi_name(self, event, user, text_value):
        """Process UPI merchant name input"""
        try:
            # Clear admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            # Validate merchant name
            if not text_value or len(text_value.strip()) < 2:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Merchant Name**\n\nPlease enter a valid merchant name (at least 2 characters)"
                )
                return
            
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "upi_settings"})
            if settings:
                upi_settings = settings.get("settings", {})
            else:
                upi_settings = {}
            
            # Update merchant name
            upi_settings["merchant_name"] = text_value.strip()
            
            # Save to database
            await self.db_connection.admin_settings.update_one(
                {"type": "upi_settings"},
                {
                    "$set": {
                        "settings": upi_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                f"✅ **Merchant Name Updated**\n\nNew merchant name: `{text_value.strip()}`",
                buttons=[[Button.inline("🔙 Back", "upi_settings")]]
            )
            
        except Exception as e:
            logger.error(f"Process UPI name error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update merchant name. Please try again.")
    
    async def handle_razorpay_settings(self, event):
        """Handle Razorpay settings management"""
        try:
            # Get current Razorpay settings
            settings = await self.db_connection.admin_settings.find_one({"type": "razorpay_settings"})
            if settings:
                razorpay_settings = settings.get("settings", {})
            else:
                razorpay_settings = {
                    "key_id": "",
                    "key_secret": "",
                    "webhook_secret": "",
                    "enabled": True,
                    "test_mode": True
                }
            
            # Mask sensitive data for display
            display_key_id = razorpay_settings.get('key_id', 'Not set')
            if len(display_key_id) > 10:
                display_key_id = display_key_id[:10] + "..."
            
            settings_message = f"""
🔑 **Razorpay Payment Settings**

Configure Razorpay payment gateway:

🆔 **Key ID:** {display_key_id}
🔐 **Key Secret:** {'Set' if razorpay_settings.get('key_secret') else 'Not set'}
🔗 **Webhook Secret:** {'Set' if razorpay_settings.get('webhook_secret') else 'Not set'}
🔄 **Razorpay Enabled:** {'Yes' if razorpay_settings.get('enabled', True) else 'No'}
🧪 **Test Mode:** {'On' if razorpay_settings.get('test_mode', True) else 'Off'}

**Note:** Keep your API keys secure. Test mode uses sandbox environment.

Click to modify:
            """
            
            buttons = [
                [Button.inline(f"🆔 Key ID ({display_key_id})", "set_razorpay_key_id")],
                [Button.inline("🔐 Key Secret", "set_razorpay_key_secret"), Button.inline("🔗 Webhook Secret", "set_razorpay_webhook_secret")],
                [Button.inline(f"🔄 Enable/Disable ({'On' if razorpay_settings.get('enabled', True) else 'Off'})", "set_razorpay_enabled")],
                [Button.inline(f"🧪 Test Mode ({'On' if razorpay_settings.get('test_mode', True) else 'Off'})", "set_razorpay_test_mode")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"Razorpay settings handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_crypto_settings(self, event):
        """Handle cryptocurrency settings management"""
        try:
            # Get current crypto settings
            settings = await self.db_connection.admin_settings.find_one({"type": "crypto_settings"})
            if settings:
                crypto_settings = settings.get("settings", {})
            else:
                crypto_settings = {
                    "bitcoin_enabled": True,
                    "usdt_enabled": True,
                    "wallet_address": "",
                    "api_key": "",
                    "enabled": True,
                    "confirmation_blocks": 3
                }
            
            # Mask sensitive data
            wallet = crypto_settings.get('wallet_address', 'Not set')
            if len(wallet) > 15:
                wallet = wallet[:8] + "..." + wallet[-4:]
            
            settings_message = f"""
₿ **Cryptocurrency Settings**

Configure crypto payment options:

₿ **Bitcoin:** {'Enabled' if crypto_settings.get('bitcoin_enabled', True) else 'Disabled'}
💰 **USDT (TRC20):** {'Enabled' if crypto_settings.get('usdt_enabled', True) else 'Disabled'}
🏦 **Wallet Address:** {wallet}
🔑 **API Key:** {'Set' if crypto_settings.get('api_key') else 'Not set'}
🔄 **Crypto Enabled:** {'Yes' if crypto_settings.get('enabled', True) else 'No'}
🔢 **Confirmation Blocks:** {crypto_settings.get('confirmation_blocks', 3)}

**Note:** Ensure wallet addresses are correct before enabling.

Click to modify:
            """
            
            buttons = [
                [Button.inline(f"₿ Bitcoin ({'On' if crypto_settings.get('bitcoin_enabled', True) else 'Off'})", "set_crypto_bitcoin"),
                 Button.inline(f"💰 USDT ({'On' if crypto_settings.get('usdt_enabled', True) else 'Off'})", "set_crypto_usdt")],
                [Button.inline(f"🏦 Wallet ({wallet})", "set_crypto_wallet")],
                [Button.inline("🔑 API Key", "set_crypto_api_key"), Button.inline(f"🔢 Confirmations ({crypto_settings.get('confirmation_blocks', 3)})", "set_crypto_confirmations")],
                [Button.inline(f"🔄 Enable/Disable ({'On' if crypto_settings.get('enabled', True) else 'Off'})", "set_crypto_enabled")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"Crypto settings handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_set_razorpay_setting(self, event, user, setting_type):
        """Handle Razorpay setting modification"""
        try:
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "razorpay_settings"})
            if settings:
                razorpay_settings = settings.get("settings", {})
            else:
                razorpay_settings = {
                    "key_id": "",
                    "key_secret": "",
                    "webhook_secret": "",
                    "enabled": True,
                    "test_mode": True
                }
            
            if setting_type == "key_id":
                await self.edit_message(
                    event,
                    f"🆔 **Set Razorpay Key ID**\n\nEnter your Razorpay Key ID:\n\n**Examples:**\n• rzp_test_xxxxxxxxxx (Test)\n• rzp_live_xxxxxxxxxx (Live)\n\n**Note:** Get this from Razorpay Dashboard > Settings > API Keys",
                    [[Button.inline("❌ Cancel", "razorpay_settings")]]
                )
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$set": {"admin_state": "razorpay_key_id"}}
                )
                
            elif setting_type == "key_secret":
                await self.edit_message(
                    event,
                    f"🔐 **Set Razorpay Key Secret**\n\nEnter your Razorpay Key Secret:\n\n**Warning:** Keep this secret secure!\n\n**Note:** Get this from Razorpay Dashboard > Settings > API Keys",
                    [[Button.inline("❌ Cancel", "razorpay_settings")]]
                )
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$set": {"admin_state": "razorpay_key_secret"}}
                )
                
            elif setting_type == "webhook_secret":
                await self.edit_message(
                    event,
                    f"🔗 **Set Webhook Secret**\n\nEnter your Razorpay Webhook Secret:\n\n**Note:** Get this from Razorpay Dashboard > Settings > Webhooks\n\n**Format:** whsec_xxxxxxxxxx",
                    [[Button.inline("❌ Cancel", "razorpay_settings")]]
                )
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$set": {"admin_state": "razorpay_webhook_secret"}}
                )
                
            elif setting_type == "enabled":
                current_enabled = razorpay_settings.get('enabled', True)
                razorpay_settings['enabled'] = not current_enabled
                
                await self.db_connection.admin_settings.update_one(
                    {"type": "razorpay_settings"},
                    {
                        "$set": {
                            "settings": razorpay_settings,
                            "updated_at": utc_now(),
                            "updated_by": user.telegram_user_id
                        }
                    },
                    upsert=True
                )
                
                status = "enabled" if not current_enabled else "disabled"
                await self.edit_message(
                    event,
                    f"✅ **Razorpay {status.title()}**\n\nRazorpay payments have been {status}.",
                    [[Button.inline("🔙 Back", "razorpay_settings")]]
                )
                
            elif setting_type == "test_mode":
                current_test = razorpay_settings.get('test_mode', True)
                razorpay_settings['test_mode'] = not current_test
                
                await self.db_connection.admin_settings.update_one(
                    {"type": "razorpay_settings"},
                    {
                        "$set": {
                            "settings": razorpay_settings,
                            "updated_at": utc_now(),
                            "updated_by": user.telegram_user_id
                        }
                    },
                    upsert=True
                )
                
                mode = "test" if not current_test else "live"
                await self.edit_message(
                    event,
                    f"✅ **Switched to {mode.title()} Mode**\n\nRazorpay is now in {mode} mode.",
                    [[Button.inline("🔙 Back", "razorpay_settings")]]
                )
            
        except Exception as e:
            logger.error(f"Set Razorpay setting error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_set_crypto_setting(self, event, user, setting_type):
        """Handle crypto setting modification"""
        try:
            # Get current settings
            settings = await self.db_connection.admin_settings.find_one({"type": "crypto_settings"})
            if settings:
                crypto_settings = settings.get("settings", {})
            else:
                crypto_settings = {
                    "bitcoin_enabled": True,
                    "usdt_enabled": True,
                    "wallet_address": "",
                    "api_key": "",
                    "enabled": True,
                    "confirmation_blocks": 3
                }
            
            if setting_type == "bitcoin":
                current = crypto_settings.get('bitcoin_enabled', True)
                crypto_settings['bitcoin_enabled'] = not current
                
            elif setting_type == "usdt":
                current = crypto_settings.get('usdt_enabled', True)
                crypto_settings['usdt_enabled'] = not current
                
            elif setting_type == "enabled":
                current = crypto_settings.get('enabled', True)
                crypto_settings['enabled'] = not current
                
            elif setting_type == "wallet":
                await self.edit_message(
                    event,
                    f"🏦 **Set Wallet Address**\n\nEnter your cryptocurrency wallet address:\n\n**Examples:**\n• Bitcoin: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa\n• USDT (TRC20): TQn9Y2khEsLJW1ChVWFMSMeRDow5KDHPUW\n\n**Warning:** Double-check the address!",
                    [[Button.inline("❌ Cancel", "crypto_settings")]]
                )
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$set": {"admin_state": "crypto_wallet"}}
                )
                return
                
            elif setting_type == "api_key":
                await self.edit_message(
                    event,
                    f"🔑 **Set API Key**\n\nEnter your blockchain API key:\n\n**Note:** Used for transaction verification\n**Providers:** BlockCypher, Tron Grid, etc.",
                    [[Button.inline("❌ Cancel", "crypto_settings")]]
                )
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$set": {"admin_state": "crypto_api_key"}}
                )
                return
                
            elif setting_type == "confirmations":
                current = crypto_settings.get('confirmation_blocks', 3)
                new_value = {1: 3, 3: 6, 6: 12, 12: 1}.get(current, 3)
                crypto_settings['confirmation_blocks'] = new_value
            
            # Save settings for toggle operations
            await self.db_connection.admin_settings.update_one(
                {"type": "crypto_settings"},
                {
                    "$set": {
                        "settings": crypto_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.handle_crypto_settings(event)
            
        except Exception as e:
            logger.error(f"Set crypto setting error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def process_razorpay_key_id(self, event, user, text_value):
        """Process Razorpay Key ID input"""
        try:
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            if not text_value or not text_value.startswith("rzp_"):
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Key ID**\n\nRazorpay Key ID must start with 'rzp_'"
                )
                return
            
            settings = await self.db_connection.admin_settings.find_one({"type": "razorpay_settings"})
            if settings:
                razorpay_settings = settings.get("settings", {})
            else:
                razorpay_settings = {}
            
            razorpay_settings["key_id"] = text_value.strip()
            
            await self.db_connection.admin_settings.update_one(
                {"type": "razorpay_settings"},
                {
                    "$set": {
                        "settings": razorpay_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                f"✅ **Razorpay Key ID Updated**\n\nKey ID: `{text_value.strip()[:10]}...`",
                buttons=[[Button.inline("🔙 Back", "razorpay_settings")]]
            )
            
        except Exception as e:
            logger.error(f"Process Razorpay Key ID error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update Key ID. Please try again.")
    
    async def process_razorpay_key_secret(self, event, user, text_value):
        """Process Razorpay Key Secret input"""
        try:
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            if not text_value or len(text_value.strip()) < 10:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Key Secret**\n\nKey Secret must be at least 10 characters"
                )
                return
            
            settings = await self.db_connection.admin_settings.find_one({"type": "razorpay_settings"})
            if settings:
                razorpay_settings = settings.get("settings", {})
            else:
                razorpay_settings = {}
            
            razorpay_settings["key_secret"] = text_value.strip()
            
            await self.db_connection.admin_settings.update_one(
                {"type": "razorpay_settings"},
                {
                    "$set": {
                        "settings": razorpay_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                "✅ **Razorpay Key Secret Updated**\n\nKey Secret has been securely saved.",
                buttons=[[Button.inline("🔙 Back", "razorpay_settings")]]
            )
            
        except Exception as e:
            logger.error(f"Process Razorpay Key Secret error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update Key Secret. Please try again.")
    
    async def process_razorpay_webhook_secret(self, event, user, text_value):
        """Process Razorpay Webhook Secret input"""
        try:
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            if not text_value or not text_value.startswith("whsec_"):
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Webhook Secret**\n\nWebhook Secret must start with 'whsec_'"
                )
                return
            
            settings = await self.db_connection.admin_settings.find_one({"type": "razorpay_settings"})
            if settings:
                razorpay_settings = settings.get("settings", {})
            else:
                razorpay_settings = {}
            
            razorpay_settings["webhook_secret"] = text_value.strip()
            
            await self.db_connection.admin_settings.update_one(
                {"type": "razorpay_settings"},
                {
                    "$set": {
                        "settings": razorpay_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                "✅ **Webhook Secret Updated**\n\nWebhook Secret has been securely saved.",
                buttons=[[Button.inline("🔙 Back", "razorpay_settings")]]
            )
            
        except Exception as e:
            logger.error(f"Process Razorpay Webhook Secret error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update Webhook Secret. Please try again.")
    
    async def process_crypto_wallet(self, event, user, text_value):
        """Process crypto wallet address input"""
        try:
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            if not text_value or len(text_value.strip()) < 20:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Wallet Address**\n\nWallet address must be at least 20 characters"
                )
                return
            
            settings = await self.db_connection.admin_settings.find_one({"type": "crypto_settings"})
            if settings:
                crypto_settings = settings.get("settings", {})
            else:
                crypto_settings = {}
            
            crypto_settings["wallet_address"] = text_value.strip()
            
            await self.db_connection.admin_settings.update_one(
                {"type": "crypto_settings"},
                {
                    "$set": {
                        "settings": crypto_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            wallet_display = text_value.strip()
            if len(wallet_display) > 15:
                wallet_display = wallet_display[:8] + "..." + wallet_display[-4:]
            
            await self.send_message(
                event.chat_id,
                f"✅ **Wallet Address Updated**\n\nWallet: `{wallet_display}`",
                buttons=[[Button.inline("🔙 Back", "crypto_settings")]]
            )
            
        except Exception as e:
            logger.error(f"Process crypto wallet error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update wallet address. Please try again.")
    
    async def process_crypto_api_key(self, event, user, text_value):
        """Process crypto API key input"""
        try:
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            if not text_value or len(text_value.strip()) < 10:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid API Key**\n\nAPI Key must be at least 10 characters"
                )
                return
            
            settings = await self.db_connection.admin_settings.find_one({"type": "crypto_settings"})
            if settings:
                crypto_settings = settings.get("settings", {})
            else:
                crypto_settings = {}
            
            crypto_settings["api_key"] = text_value.strip()
            
            await self.db_connection.admin_settings.update_one(
                {"type": "crypto_settings"},
                {
                    "$set": {
                        "settings": crypto_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                "✅ **API Key Updated**\n\nAPI Key has been securely saved.",
                buttons=[[Button.inline("🔙 Back", "crypto_settings")]]
            )
            
        except Exception as e:
            logger.error(f"Process crypto API key error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update API key. Please try again.")
    
    async def handle_payment_gateways(self, event):
        """Handle payment gateways configuration overview"""
        try:
            # Get all payment gateway settings
            upi_settings = await self.db_connection.admin_settings.find_one({"type": "upi_settings"})
            razorpay_settings = await self.db_connection.admin_settings.find_one({"type": "razorpay_settings"})
            crypto_settings = await self.db_connection.admin_settings.find_one({"type": "crypto_settings"})
            
            # Extract status
            upi_status = "Configured" if upi_settings and upi_settings.get("settings", {}).get("merchant_vpa") else "Not configured"
            razorpay_status = "Configured" if razorpay_settings and razorpay_settings.get("settings", {}).get("key_id") else "Not configured"
            crypto_status = "Configured" if crypto_settings and crypto_settings.get("settings", {}).get("wallet_address") else "Not configured"
            
            settings_message = f"""
🔧 **Payment Gateway Configuration**

Configure all payment methods:

💳 **UPI Payments**
Status: {upi_status}
Direct UPI ID payments with QR codes

🔑 **Razorpay Gateway**
Status: {razorpay_status}
Professional payment gateway with cards, UPI, wallets

₿ **Cryptocurrency**
Status: {crypto_status}
Bitcoin and USDT payments with blockchain verification

**Note:** Configure each gateway individually for secure payments.

Select gateway to configure:
            """
            
            buttons = [
                [Button.inline(f"💳 UPI Settings ({upi_status})", "upi_settings")],
                [Button.inline(f"🔑 Razorpay Settings ({razorpay_status})", "razorpay_settings")],
                [Button.inline(f"₿ Crypto Settings ({crypto_status})", "crypto_settings")],
                [Button.inline("🔙 Back", "payment_settings_detailed")]
            ]
            
            await self.edit_message(event, settings_message, buttons)
            
        except Exception as e:
            logger.error(f"Payment gateways handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_payment_timeout_setting(self, event, user):
        """Handle payment timeout setting"""
        try:
            # Get current timeout
            settings = await self.db_connection.admin_settings.find_one({"type": "payment_settings"})
            if settings:
                payment_settings = settings.get("settings", {})
            else:
                payment_settings = {}
            
            current_timeout = payment_settings.get('payment_timeout_minutes', 15)
            
            # Cycle through timeout options: 5, 10, 15, 30, 60 minutes
            new_timeout = {5: 10, 10: 15, 15: 30, 30: 60, 60: 5}.get(current_timeout, 15)
            payment_settings['payment_timeout_minutes'] = new_timeout
            
            # Save to database
            await self.db_connection.admin_settings.update_one(
                {"type": "payment_settings"},
                {
                    "$set": {
                        "settings": payment_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.edit_message(
                event,
                f"✅ **Payment Timeout Updated**\n\nNew timeout: {new_timeout} minutes\n\nPayments will expire after {new_timeout} minutes if not completed.",
                [[Button.inline("🔙 Back", "payment_settings_detailed")]]
            )
            
        except Exception as e:
            logger.error(f"Payment timeout setting error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def process_payment_timeout(self, event, user, text_value):
        """Process payment timeout input"""
        try:
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            try:
                timeout_minutes = int(text_value)
                if timeout_minutes < 1 or timeout_minutes > 120:
                    await self.send_message(
                        event.chat_id,
                        "❌ **Invalid Timeout**\n\nTimeout must be between 1 and 120 minutes"
                    )
                    return
            except ValueError:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Input**\n\nPlease enter a valid number of minutes"
                )
                return
            
            settings = await self.db_connection.admin_settings.find_one({"type": "payment_settings"})
            if settings:
                payment_settings = settings.get("settings", {})
            else:
                payment_settings = {}
            
            payment_settings["payment_timeout_minutes"] = timeout_minutes
            
            await self.db_connection.admin_settings.update_one(
                {"type": "payment_settings"},
                {
                    "$set": {
                        "settings": payment_settings,
                        "updated_at": utc_now(),
                        "updated_by": user.telegram_user_id
                    }
                },
                upsert=True
            )
            
            await self.send_message(
                event.chat_id,
                f"✅ **Payment Timeout Updated**\n\nNew timeout: {timeout_minutes} minutes",
                buttons=[[Button.inline("🔙 Back", "payment_settings_detailed")]]
            )
            
        except Exception as e:
            logger.error(f"Process payment timeout error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to update timeout. Please try again.")
    
    async def handle_payment_dashboard(self, event):
        """Handle comprehensive payment dashboard"""
        try:
            # Get all payment method statuses
            available_methods = await self.payment_settings_service.get_available_payment_methods()
            payment_settings = await self.payment_settings_service.get_payment_settings()
            
            # Get validation status for each method
            razorpay_validation = await self.payment_settings_service.validate_razorpay_config()
            crypto_validation = await self.payment_settings_service.validate_crypto_config()
            
            # Count enabled methods
            enabled_count = len(available_methods)
            total_methods = 3  # UPI, Razorpay, Crypto
            
            dashboard_message = f"""
📊 **Payment Methods Dashboard**

**Overview:**
✅ **Active Methods:** {enabled_count}/{total_methods}
⏱️ **Payment Timeout:** {payment_settings.get('payment_timeout_minutes', 15)} minutes
🔄 **Auto Refund:** {'Enabled' if payment_settings.get('auto_refund_enabled', True) else 'Disabled'}
🧪 **Simulation Mode:** {'On' if payment_settings.get('simulate_payments', True) else 'Off'}

**Payment Methods Status:**

💳 **UPI Payments**
Status: {'Active' if any(m['id'] == 'upi' for m in available_methods) else 'Inactive'}
Direct UPI ID payments with QR codes

🔑 **Razorpay Gateway**
Status: {'Active' if any(m['id'] == 'razorpay' for m in available_methods) else 'Inactive'}
Config: {'Valid' if razorpay_validation['valid'] else 'Invalid'}
Professional gateway with cards, UPI, wallets

₿ **Cryptocurrency**
Status: {'Active' if any(m['id'] == 'crypto' for m in available_methods) else 'Inactive'}
Config: {'Valid' if crypto_validation['valid'] else 'Invalid'}
Bitcoin and USDT with blockchain verification

**Quick Actions:**
            """
            
            buttons = [
                [Button.inline("💳 UPI Settings", "upi_settings"), Button.inline("🔑 Razorpay Settings", "razorpay_settings")],
                [Button.inline("₿ Crypto Settings", "crypto_settings"), Button.inline("⚙️ Payment Settings", "payment_settings_detailed")],
                [Button.inline("📊 Refresh Dashboard", "payment_dashboard")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, dashboard_message, buttons)
            
        except Exception as e:
            logger.error(f"Payment dashboard handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_approve_upi_payment(self, event, user, order_id):
        """Handle UPI payment approval with amount input"""
        try:
            # Get UPI order
            order = await self.db_connection.upi_orders.find_one({"order_id": order_id})
            if not order:
                await self.answer_callback(event, "❌ Order not found", alert=True)
                return
            
            # Get user info
            user_info = await self.db_connection.users.find_one({"telegram_user_id": order["user_id"]})
            user_name = user_info.get("first_name", "Unknown") if user_info else "Unknown"
            
            # Send amount input prompt as a new message (don't edit the screenshot)
            await self.send_message(
                event.chat_id,
                f"💰 **Approve UPI Payment**\n\n"
                f"👤 **User:** {user_name} (ID: {order['user_id']})\n"
                f"🆔 **Order ID:** {order_id}\n"
                f"💳 **Type:** Quick Deposit (Any Amount)\n\n"
                f"Please enter the verified amount from the screenshot:\n\n"
                f"**Format:** Enter amount in rupees (e.g., 100, 250.50)"
            )
            
            # Set admin state for amount input
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"admin_state": f"approve_upi_amount_{order_id}"}}
            )
            logger.info(f"[ADMIN] Set admin state to approve_upi_amount_{order_id} for user {user.telegram_user_id}")
            
            await self.answer_callback(event, "💰 Enter amount to approve")
            
        except Exception as e:
            logger.error(f"Approve UPI payment error: {str(e)}")
            await self.answer_callback(event, "❌ Error occurred", alert=True)
    
    async def handle_reject_upi_payment(self, event, user, order_id):
        """Handle UPI payment rejection"""
        try:
            # Update order status to rejected
            await self.db_connection.upi_orders.update_one(
                {"order_id": order_id},
                {
                    "$set": {
                        "status": "rejected",
                        "rejected_at": utc_now().isoformat() + "Z",
                        "rejected_by": user.telegram_user_id,
                        "rejection_reason": "Payment verification failed"
                    }
                }
            )
            
            # Get order details for notification
            order = await self.db_connection.upi_orders.find_one({"order_id": order_id})
            if order:
                # Notify user about rejection
                await self.notify_user_payment_rejected(order["user_id"], order_id)
            
            # Send confirmation message
            await self.send_message(
                event.chat_id,
                f"❌ **UPI Payment Rejected**\n\nOrder {order_id} has been rejected.\n\nUser will be notified about the rejection."
            )
            
            await self.answer_callback(event, "❌ Payment rejected")
            
        except Exception as e:
            logger.error(f"Reject UPI payment error: {str(e)}")
            await self.answer_callback(event, "❌ Error occurred", alert=True)
    
    async def handle_verify_upi_payment(self, event, order_id):
        """Handle UPI payment verification details"""
        try:
            order = await self.db_connection.upi_orders.find_one({"order_id": order_id})
            if not order:
                await self.edit_message(
                    event,
                    "❌ **UPI Order Not Found**\n\nThe payment order could not be found.",
                    [[Button.inline("🔙 Back", "approve_payments")]]
                )
                return
            
            # Get user info
            user_info = await self.db_connection.users.find_one({"telegram_user_id": order["user_id"]})
            user_name = user_info.get("first_name", "Unknown") if user_info else "Unknown"
            
            # Send screenshot directly with approve/reject buttons
            if order.get('screenshot_file_id'):
                try:
                    # Convert file ID to proper format if needed
                    file_id = order['screenshot_file_id']
                    if isinstance(file_id, (int, float)):
                        file_id = str(int(file_id))
                    
                    await self.client.send_file(
                        event.chat_id,
                        file_id,
                        caption=f"📸 **UPI Payment Screenshot**\n\n**Order ID:** {order_id}\n**User:** {user_name} (ID: {order['user_id']})\n**Type:** Quick Deposit (Any Amount)\n**Method:** UPI\n**Submitted:** {order.get('screenshot_uploaded_at', 'Unknown')}",
                        buttons=[
                            [Button.inline("✅ Approve Payment", f"approve_upi_{order_id}")],
                            [Button.inline("❌ Reject Payment", f"reject_upi_{order_id}")],
                            [Button.inline("🔙 Back", "approve_payments")]
                        ]
                    )
                    # Delete the original message
                    await self.client.delete_messages(event.chat_id, event.message_id)
                except Exception as e:
                    logger.error(f"Error sending UPI screenshot: {str(e)}")
                    # Fallback: show details without screenshot
                    await self.edit_message(
                        event,
                        f"📸 **UPI Payment Details**\n\n**Order ID:** {order_id}\n**User:** {user_name} (ID: {order['user_id']})\n**Type:** Quick Deposit (Any Amount)\n**Method:** UPI\n**Submitted:** {order.get('screenshot_uploaded_at', 'Unknown')}\n\n❌ Screenshot could not be displayed, but you can still approve/reject the payment.",
                        [
                            [Button.inline("✅ Approve Payment", f"approve_upi_{order_id}")],
                            [Button.inline("❌ Reject Payment", f"reject_upi_{order_id}")],
                            [Button.inline("🔙 Back", "approve_payments")]
                        ]
                    )
            else:
                await self.edit_message(
                    event,
                    f"❌ **No Screenshot Found**\n\nOrder {order_id} does not have a screenshot attached.",
                    [[Button.inline("🔙 Back", "approve_payments")]]
                )
            
        except Exception as e:
            logger.error(f"Verify UPI payment error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def notify_user_payment_rejected(self, user_id: int, order_id: str):
        """Notify user about payment rejection"""
        try:
            # This would send notification via buyer bot
            logger.info(f"Notifying user {user_id} about UPI payment rejection for order {order_id}")
            # Implementation would send message through buyer bot
        except Exception as e:
            logger.error(f"Failed to notify user about payment rejection: {str(e)}")
    
    async def process_upi_approval_amount(self, event, user, order_id, text_value):
        """Process UPI approval amount input"""
        try:
            logger.info(f"[ADMIN] Processing UPI approval amount: {text_value} for order {order_id}")
            
            # Clear admin state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"admin_state": ""}}
            )
            
            # Validate amount
            try:
                amount = float(text_value.replace('₹', '').replace(',', '').strip())
                if amount <= 0 or amount > 100000:
                    await self.send_message(
                        event.chat_id,
                        "❌ **Invalid Amount**\n\nAmount must be between ₹1 and ₹100,000.",
                        buttons=[[Button.inline("🔙 Back", "approve_payments")]]
                    )
                    return
            except ValueError:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Amount Format**\n\nPlease enter a valid amount (e.g., 100, 250.50).",
                    buttons=[[Button.inline("🔙 Back", "approve_payments")]]
                )
                return
            
            # Show processing message
            processing_msg = await self.send_message(
                event.chat_id,
                f"⏳ **Processing Payment Approval...**\n\n"
                f"💰 Amount: ₹{amount:.2f}\n"
                f"🆔 Order ID: {order_id}\n\n"
                f"Please wait while we update the user's balance..."
            )
            
            # Approve payment with verified amount
            from app.services.UpiPaymentService import UpiPaymentService
            upi_service = UpiPaymentService(self.db_connection)
            
            logger.info(f"[ADMIN] Calling approve_payment_with_amount with order_id={order_id}, amount={amount}")
            result = await upi_service.approve_payment_with_amount(order_id, amount)
            logger.info(f"[ADMIN] UPI service result: {result}")
            
            if result.get("success"):
                logger.info(f"[ADMIN] UPI payment approved successfully: {order_id}, amount: ₹{amount}, user: {result['user_id']}, new_balance: {result.get('new_balance', 'unknown')}")
                
                # Update the processing message with success
                await self.client.edit_message(
                    event.chat_id,
                    processing_msg.id,
                    f"✅ **UPI Payment Approved Successfully!**\n\n"
                    f"💰 **Amount Deposited:** ₹{amount:.2f}\n"
                    f"🆔 **Order ID:** {order_id}\n"
                    f"👤 **User ID:** {result['user_id']}\n"
                    f"💳 **User's New Balance:** ₹{result.get('new_balance', 0):.2f}\n\n"
                    f"✅ **Status:** Balance updated successfully\n"
                    f"📱 **Notification:** User will be notified automatically\n\n"
                    f"The payment has been processed and the user's account has been credited.",
                    buttons=[[Button.inline("💰 Verify More Payments", "approve_payments")], [Button.inline("🔙 Main Menu", "back_to_main")]]
                )
                
                logger.info(f"[ADMIN] Admin {user.telegram_user_id} successfully approved UPI payment {order_id} for ₹{amount}")
                
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"[ADMIN] UPI approval failed: {error_msg}")
                
                # Update the processing message with error
                await self.client.edit_message(
                    event.chat_id,
                    processing_msg.id,
                    f"❌ **Payment Approval Failed**\n\n"
                    f"🆔 **Order ID:** {order_id}\n"
                    f"💰 **Amount:** ₹{amount:.2f}\n"
                    f"❌ **Error:** {error_msg}\n\n"
                    f"Please check the order details and try again.",
                    buttons=[[Button.inline("🔄 Try Again", "approve_payments")], [Button.inline("🔙 Main Menu", "back_to_main")]]
                )
            
        except Exception as e:
            logger.error(f"[ADMIN] Process UPI approval amount error: {str(e)}")
            await self.send_message(
                event.chat_id, 
                f"❌ **System Error**\n\nFailed to process approval: {str(e)}\n\nPlease try again or contact technical support.",
                buttons=[[Button.inline("🔄 Try Again", "approve_payments")], [Button.inline("🔙 Main Menu", "back_to_main")]]
            )
    
    async def notify_user_balance_deposited(self, user_id: int, amount: float, order_id: str):
        """Notify user that balance has been deposited"""
        try:
            logger.info(f"[ADMIN] User {user_id} should be notified: ₹{amount} deposited for order {order_id}")
            # TODO: Implement actual notification through buyer bot
        except Exception as e:
            logger.error(f"Error notifying user about balance deposit: {str(e)}")
    

    
    # ========== Manual Account Management (from AuthBot) ==========
    
    async def handle_add_interceptor_account(self, event):
        """Add account for code interception (from AuthBot)"""
        try:
            is_admin, user = await self.check_admin_access(event)
            if not is_admin:
                return
            
            usage_msg = """📝 **Add Account for Code Interception**

**Usage:**
/add ACCOUNT_ID
session_string=<encrypted_session>
buyer_id=<telegram_user_id>

**Example:**
/add 507f1f77bcf86cd799439011
session_string=1BVtsOJwBu7...
buyer_id=123456789

This will start intercepting login codes for the account."""
            
            parts = event.text.split('\n', 1)
            if len(parts) < 2:
                await self.send_message(event.chat_id, usage_msg)
                return
            
            account_id = parts[0].replace('/add', '').strip()
            if not account_id:
                await self.send_message(event.chat_id, "❌ Account ID required")
                return
            
            # Parse parameters
            params = {}
            for line in parts[1].strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    params[key.strip()] = value.strip()
            
            session_string = params.get('session_string')
            buyer_id = params.get('buyer_id')
            
            if not session_string or not buyer_id:
                await self.send_message(event.chat_id, "❌ Missing required fields: session_string, buyer_id")
                return
            
            # Start code interception
            from app.services.CodeInterceptorService import CodeInterceptorService
            # from app.main import code_interceptor
            
            result = await self.code_interceptor.start_intercepting_account(
                account_id, session_string, int(buyer_id)
            )
            
            if result:
                await self.send_message(
                    event.chat_id,
                    f"✅ **Code Interception Started**\n\n"
                    f"🆔 Account: {account_id}\n"
                    f"👤 Buyer: {buyer_id}\n\n"
                    f"Login codes will be forwarded to buyer automatically."
                )
            else:
                await self.send_message(event.chat_id, "❌ Failed to start code interception")
            
        except Exception as e:
            logger.error(f"Add interceptor account error: {str(e)}")
            await self.send_message(event.chat_id, f"❌ Error: {str(e)}")
    
    async def handle_list_interceptor_accounts(self, event):
        """List accounts being intercepted (from AuthBot)"""
        try:
            is_admin, user = await self.check_admin_access(event)
            if not is_admin:
                return
            
            # from app.main import code_interceptor
            
            active_accounts = await self.code_interceptor.get_active_interceptions()
            
            if not active_accounts:
                await self.send_message(
                    event.chat_id,
                    "📋 **Active Code Interceptions**\n\n✅ No accounts currently being intercepted."
                )
                return
            
            message = f"📋 **Active Code Interceptions** ({len(active_accounts)})\n\n"
            
            for account_id in active_accounts[:10]:
                # Get account details
                from bson import ObjectId
                account = await self.db_connection.accounts.find_one({"_id": ObjectId(account_id)})
                if account:
                    username = account.get('username', 'No username')
                    phone = account.get('phone_number', 'Hidden')
                    message += f"🆔 {account_id}\n"
                    message += f"   👤 {username}\n"
                    message += f"   📱 {phone}\n\n"
                else:
                    message += f"🆔 {account_id}\n\n"
            
            await self.send_message(event.chat_id, message)
            
        except Exception as e:
            logger.error(f"List interceptor accounts error: {str(e)}")
            await self.send_message(event.chat_id, f"❌ Error: {str(e)}")
    
    async def handle_interceptor_stats(self, event):
        """Show code interception statistics (from AuthBot)"""
        try:
            is_admin, user = await self.check_admin_access(event)
            if not is_admin:
                return
            
            # from app.main import code_interceptor
            
            active_accounts = await self.code_interceptor.get_active_interceptions()
            total_sold = await self.db_connection.accounts.count_documents({"status": "sold"})
            
            message = f"""📊 **Code Interception Statistics**

📱 **Active Interceptions:** {len(active_accounts)}
💰 **Total Sold Accounts:** {total_sold}
🔄 **Interception Rate:** {(len(active_accounts)/total_sold*100) if total_sold > 0 else 0:.1f}%

**Commands:**
/add - Add account for interception
/list - List active interceptions
/stats - Show statistics"""
            
            await self.send_message(event.chat_id, message)
            
        except Exception as e:
            logger.error(f"Interceptor stats error: {str(e)}")
            await self.send_message(event.chat_id, f"❌ Error: {str(e)}")

    
    async def handle_toggle_seller_setting(self, event, user, setting_key):
        """Toggle seller setting"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "seller_settings"})
            if settings:
                seller_settings = settings.get("settings", {})
            else:
                seller_settings = {}
            
            # Toggle boolean setting
            current = seller_settings.get(setting_key, True)
            seller_settings[setting_key] = not current
            
            # Save
            await self.db_connection.admin_settings.update_one(
                {"type": "seller_settings"},
                {"$set": {"settings": seller_settings, "updated_at": utc_now(), "updated_by": user.telegram_user_id}},
                upsert=True
            )
            
            await self.handle_seller_settings(event)
            
        except Exception as e:
            logger.error(f"Toggle seller setting error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)
    
    async def handle_set_seller_max_uploads(self, event, user):
        """Set max daily uploads"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "seller_settings"})
            if settings:
                seller_settings = settings.get("settings", {})
            else:
                seller_settings = {}
            
            # Cycle through values: 5, 10, 20, 50, 100, unlimited
            current = seller_settings.get("max_daily_uploads", 10)
            new_value = {5: 10, 10: 20, 20: 50, 50: 100, 100: 999, 999: 5}.get(current, 10)
            seller_settings["max_daily_uploads"] = new_value
            
            # Save
            await self.db_connection.admin_settings.update_one(
                {"type": "seller_settings"},
                {"$set": {"settings": seller_settings, "updated_at": utc_now(), "updated_by": user.telegram_user_id}},
                upsert=True
            )
            
            await self.handle_seller_settings(event)
            
        except Exception as e:
            logger.error(f"Set seller max uploads error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)

    
    async def handle_toggle_buyer_setting(self, event, user, setting_key):
        """Toggle buyer setting"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "buyer_settings"})
            if settings:
                buyer_settings = settings.get("settings", {})
            else:
                buyer_settings = {}
            
            # Toggle boolean setting
            current = buyer_settings.get(setting_key, True)
            buyer_settings[setting_key] = not current
            
            # Save
            await self.db_connection.admin_settings.update_one(
                {"type": "buyer_settings"},
                {"$set": {"settings": buyer_settings, "updated_at": utc_now(), "updated_by": user.telegram_user_id}},
                upsert=True
            )
            
            await self.handle_buyer_settings(event)
            
        except Exception as e:
            logger.error(f"Toggle buyer setting error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)
    
    async def handle_set_buyer_max_purchases(self, event, user):
        """Set max daily purchases"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "buyer_settings"})
            if settings:
                buyer_settings = settings.get("settings", {})
            else:
                buyer_settings = {}
            
            # Cycle through values: 1, 3, 5, 10, 20, unlimited
            current = buyer_settings.get("max_purchases_per_day", 5)
            new_value = {1: 3, 3: 5, 5: 10, 10: 20, 20: 999, 999: 1}.get(current, 5)
            buyer_settings["max_purchases_per_day"] = new_value
            
            # Save
            await self.db_connection.admin_settings.update_one(
                {"type": "buyer_settings"},
                {"$set": {"settings": buyer_settings, "updated_at": utc_now(), "updated_by": user.telegram_user_id}},
                upsert=True
            )
            
            await self.handle_buyer_settings(event)
            
        except Exception as e:
            logger.error(f"Set buyer max purchases error: {e}")
            await self.answer_callback(event, "❌ Error", alert=True)

    async def handle_logs_filter(self, event, user, level):
        """Filter logs by level"""
        try:
            query = {"level": level} if level else {}
            logs = await self.db_connection.error_logs.find(query).sort("timestamp", -1).limit(20).to_list(20)
            
            if not logs:
                message = f"📝 **System Logs** ({level or 'All'})\\n\\n✅ No logs found."
            else:
                message = f"📝 **System Logs** ({level or 'All'}) - Last 20\\n\\n"
                for log in logs:
                    log_level = log.get('level', 'INFO')
                    emoji = {'ERROR': '🔴', 'WARNING': '⚠️', 'INFO': 'ℹ️'}.get(log_level, 'ℹ️')
                    timestamp = log.get('timestamp', utc_now()).strftime('%m/%d %H:%M')
                    message_text = log.get('message', 'No message')[:50]
                    message += f"{emoji} {timestamp} - {message_text}\\n"
            
            buttons = [
                [Button.inline("🔴 Errors Only", "logs_filter_error")],
                [Button.inline("⚠️ Warnings", "logs_filter_warning"), Button.inline("ℹ️ All Logs", "logs_filter_all")],
                [Button.inline("🔄 Refresh", "logs_refresh"), Button.inline("🗑️ Clear Logs", "logs_clear")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, message, buttons)
            
        except Exception as e:
            logger.error(f"Logs filter error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_clear_logs(self, event, user):
        """Clear all logs"""
        try:
            result = await self.db_connection.error_logs.delete_many({})
            
            await self.edit_message(
                event,
                f"✅ **Logs Cleared**\\n\\n{result.deleted_count} log entries have been deleted.",
                [[Button.inline("🔙 Back", "view_logs")]]
            )
            
        except Exception as e:
            logger.error(f"Clear logs error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")

    async def handle_login_account(self, event, user, account_id):
        """Test login to account"""
        try:
            from bson import ObjectId
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            from app.utils.encryption import decrypt_data
            
            account = await self.db_connection.accounts.find_one({"_id": ObjectId(account_id)})
            if not account:
                await self.edit_message(event, "❌ Account not found", [[Button.inline("🔙 Back", "review_accounts")]])
                return
            
            await self.edit_message(event, "🔐 **Logging in...**\n\nPlease wait...")
            
            # Decrypt session
            session_string = account.get("session_string")
            try:
                decrypted_session = decrypt_data(session_string)
            except:
                decrypted_session = session_string
            
            # Get proxy if available
            proxy = None
            seller_id = account.get("seller_id")
            if seller_id:
                proxy_doc = await self.db_connection.seller_proxies.find_one({"seller_id": seller_id})
                if proxy_doc:
                    proxy = {
                        "proxy_type": proxy_doc["proxy_type"],
                        "addr": proxy_doc["proxy_host"],
                        "port": proxy_doc["proxy_port"],
                        "username": proxy_doc.get("proxy_username"),
                        "password": proxy_doc.get("proxy_password")
                    }
            
            # Login
            client = TelegramClient(StringSession(decrypted_session), self.api_id, self.api_hash, proxy=proxy)
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                await self.edit_message(event, "❌ **Login Failed**\n\nSession not authorized", [[Button.inline("🔙 Back", "review_accounts")]])
                return
            
            # Get account info
            me = await client.get_me()
            dialogs = await client.get_dialogs(limit=5)
            
            await client.disconnect()
            
            # Format message
            message = f"✅ **Login Successful!**\n\n"
            message += f"👤 **Name:** {me.first_name} {me.last_name or ''}\n"
            message += f"🆔 **Username:** @{me.username or 'None'}\n"
            message += f"📱 **Phone:** {me.phone}\n"
            message += f"🆔 **ID:** {me.id}\n"
            message += f"💎 **Premium:** {'Yes' if me.premium else 'No'}\n"
            message += f"🤖 **Bot:** {'Yes' if me.bot else 'No'}\n\n"
            message += f"💬 **Recent Chats:** {len(dialogs)}\n"
            
            await self.edit_message(event, message, [[Button.inline("🔙 Back", "review_accounts")]])
            
        except Exception as e:
            logger.error(f"Login account error: {str(e)}")
            await self.edit_message(event, f"❌ **Login Error**\n\n{str(e)}", [[Button.inline("🔙 Back", "review_accounts")]])
