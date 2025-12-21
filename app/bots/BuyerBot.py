from datetime import datetime
from telethon import events, Button
from .BaseBot import BaseBot
from app.database.connection import db
from app.models import Listing, Transaction, TransactionType, PaymentMethod, TransactionStatus, SettingsManager
from app.services import PaymentService, OtpService
from app.services.UpiPaymentService import UpiPaymentService
from app.services.ListingService import ListingService
from app.services.AccountTransferService import AccountTransferService
from app.services.AccountLoginService import AccountLoginService
from app.utils import create_main_menu, create_country_menu, create_year_menu, create_payment_keyboard, create_otp_verification_keyboard
import logging
import os
import asyncio
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class BuyerBot(BaseBot):
    def __init__(self, api_id: int, api_hash: str, bot_token: str, db_connection, otp_service, marketing_service, social_service, support_service):
        super().__init__(api_id, api_hash, bot_token, db_connection, "Buyer")
        self.payment_service = PaymentService(db_connection)
        self.listing_service = ListingService(db_connection)
        self.transfer_service = AccountTransferService(db_connection)
        self.account_login_service = AccountLoginService(db_connection, api_id, api_hash)
        self.otp_service = otp_service
        self.marketing_service = marketing_service
        self.social_service = social_service
        self.support_service = support_service
        self.settings_manager = SettingsManager(db_connection)
    
    async def get_purchase_settings(self):
        """Get purchase settings from admin settings"""
        return await self.settings_manager.get_setting("buyer_purchase_settings")
    
    async def get_browsing_settings(self):
        """Get browsing settings from admin settings"""
        return await self.settings_manager.get_setting("buyer_browsing_settings")
    
    async def get_general_settings(self):
        """Get general settings from admin settings"""
        return await self.settings_manager.get_setting("general_settings")
    
    async def get_payment_settings(self):
        """Get payment settings from admin settings"""
        return await self.settings_manager.get_setting("payment_settings")
    
    def register_handlers(self):
        """Register buyer bot event handlers"""
        
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await self.handle_start(event)
        
        @self.client.on(events.CallbackQuery)
        async def callback_handler(event):
            await self.handle_callback(event)
        
        @self.client.on(events.NewMessage(func=lambda e: e.text and not e.text.startswith('/')))
        async def text_handler(event):
            await self.handle_text(event)
        
        @self.client.on(events.NewMessage(func=lambda e: e.photo or (e.document and e.document.mime_type and e.document.mime_type.startswith('image/'))))
        async def photo_handler(event):
            await self.handle_photo(event)
        
        # Start notification processing task
        asyncio.create_task(self.process_notifications())
    
    async def handle_start(self, event):
        """Handle /start command"""
        try:
            # Check if maintenance mode is enabled
            general_settings = await self.get_general_settings()
            if general_settings.get('maintenance_mode', False):
                await self.send_message(
                    event.chat_id,
                    "🔧 **Maintenance Mode**\n\nThe system is currently under maintenance.\nPlease try again later."
                )
                return
            
            user = await self.get_or_create_user(event)
            
            # Get payment methods from admin settings
            payment_settings = await self.get_payment_settings()
            available_methods = []
            if payment_settings.get('upi_enabled', True):
                available_methods.append('UPI')
            if payment_settings.get('crypto_enabled', True):
                available_methods.append('Crypto')
            if payment_settings.get('otp_payment_enabled', True):
                available_methods.append('OTP')
            
            payment_methods_text = '/'.join(available_methods) if available_methods else 'Contact Admin'
            
            # Check if welcome message is enabled
            if not general_settings.get('welcome_message_enabled', True):
                buttons = create_main_menu(is_seller=False)
                await self.send_message(event.chat_id, "🛒 **Telegram Account Marketplace**\n\nWhat would you like to do?", buttons)
                return
            
            welcome_message = f"""
🛒 **Welcome to Telegram Account Marketplace - Buyer Bot**

Hello {user.first_name}! 👋

Find and purchase high-quality Telegram accounts:

**Available Features:**
• Browse by country and creation year
• Verified accounts only
• Secure payment ({payment_methods_text})
• Instant delivery after payment
• Full account ownership transfer

**How to Buy:**
🛒 **Browse Marketplace**: Choose from our verified accounts

**Account Quality:**
✅ Zero contacts
✅ No spam history
✅ Clean group/channel history
✅ Active and verified
✅ Admin approved

Ready to find your perfect account?
            """
            
            buttons = create_main_menu(is_seller=False)
            await self.send_message(event.chat_id, welcome_message, buttons)
            
        except Exception as e:
            logger.error(f"Start handler error: {str(e)}")
            await self.send_message(event.chat_id, "❌ An error occurred. Please try again.")
    
    async def handle_callback(self, event):
        """Handle callback queries"""
        try:
            data = event.data.decode('utf-8')
            user = await self.get_or_create_user(event)
            
            if data == "browse_accounts":
                await self.handle_browse_accounts(event)

            elif data == "my_purchases":
                await self.handle_my_purchases(event, user)
            elif data == "my_balance":
                await self.handle_my_balance(event, user)
            elif data == "add_funds":
                await self.handle_add_funds(event, user)
            elif data == "help":
                await self.handle_help(event)
            elif data.startswith("country_"):
                country = data.split("_", 1)[1]
                await self.handle_country_selection(event, country)
            elif data.startswith("year_"):
                parts = data.split("_")
                country = parts[1]
                year = int(parts[2])
                await self.handle_year_selection(event, country, year)
            elif data.startswith("listing_"):
                listing_id = data.split("_", 1)[1]
                await self.handle_listing_details(event, listing_id)
            elif data.startswith("buy_"):
                listing_id = data.split("_", 1)[1]
                await self.handle_buy_listing(event, user, listing_id)
            elif data.startswith("pay_"):
                parts = data.split("_")
                method = parts[1]  # upi, crypto, razorpay, bitcoin, usdt, wallet, otp
                listing_id = parts[2]
                # Map payment methods
                if method in ["bitcoin", "usdt"]:
                    method = "crypto"
                elif method == "wallet":
                    method = "wallet_balance"
                await self.handle_payment_method(event, user, method, listing_id)
            elif data.startswith("resend_buyer_otp_"):
                user_id = int(data.split("_", 3)[3])
                await self.handle_resend_buyer_otp(event, user_id)
            elif data == "cancel_otp_purchase":
                await self.handle_cancel_otp_purchase(event, user)
            elif data == "back_to_main":
                await self.handle_back_to_main(event)
            elif data == "contact_support":
                await self.handle_contact_support(event)
            elif data == "faq":
                await self.handle_faq(event)
            elif data.startswith("deposit_"):
                method = data.split("_", 1)[1]
                await self.handle_deposit_method(event, user, method)
            elif data.startswith("deposit_sent_"):
                transaction_id = data.split("_", 2)[2]
                await self.handle_deposit_sent(event, user, transaction_id)
            elif data.startswith("check:"):
                order_id = data.split(":", 1)[1]
                await self.handle_check_payment(event, user, order_id)
            elif data == "upi_quick_deposit":
                await self.handle_upi_quick_deposit(event, user)
            elif data == "upi_fixed_amount":
                await self.handle_upi_fixed_amount(event, user)
            elif data.startswith("payment_sent_"):
                transaction_id = data.split("_", 2)[2]
                await self.handle_payment_sent(event, user, transaction_id)
            elif data.startswith("cancel_payment_"):
                transaction_id = data.split("_", 2)[2]
                await self.handle_cancel_payment(event, user, transaction_id)
            elif data.startswith("discount_"):
                listing_id = data.split("_", 1)[1]
                await self.handle_discount_code(event, user, listing_id)
            elif data.startswith("upload_screenshot_"):
                order_id = data.split("_", 2)[2]
                await self.handle_upload_screenshot_request(event, order_id)
            
            try:
                await self.answer_callback(event)
            except:
                pass  # Ignore callback answer errors
            
        except Exception as e:
            logger.error(f"Callback handler error: {str(e)}")
            try:
                await self.answer_callback(event, "❌ An error occurred", alert=True)
            except:
                pass  # Ignore callback answer errors
    

    
    async def handle_text(self, event):
        """Handle text messages"""
        try:
            user = await self.get_or_create_user(event)
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
            
            if not user_doc or not user_doc.get("state"):
                # No state - ignore random text messages
                return
            
            state = user_doc["state"]
            
            if state == "awaiting_buyer_otp":
                await self.process_buyer_otp(event, user, event.text.strip())
            elif state == "awaiting_buyer_2fa":
                await self.process_buyer_2fa_password(event, user, event.text.strip())
            elif state.startswith("awaiting_deposit_amount_"):
                method = state.split("_")[-1]
                await self.process_deposit_amount(event, user, method, event.text.strip())
            elif state.startswith("awaiting_discount_"):
                listing_id = state.split("_", 2)[2]
                await self.process_discount_code(event, user, listing_id, event.text.strip())
            elif state == "awaiting_deposit_amount":
                await self.process_upi_deposit_amount(event, user, event.text.strip())
            elif state == "awaiting_upi_deposit_amount":
                await self.process_upi_deposit_amount(event, user, event.text.strip())
            
        except Exception as e:
            logger.error(f"Text handler error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to process your input. Please try again.")
    
    async def handle_photo(self, event):
        """Handle photo uploads for payment screenshots"""
        try:
            user = await self.get_or_create_user(event)
            
            # Check if user has pending UPI order awaiting screenshot
            pending_upi_order = await self.db_connection.upi_orders.find_one({
                "user_id": user.telegram_user_id,
                "status": "pending",
                "type": "quick_deposit"
            })
            
            # Check if user has pending payment order awaiting screenshot
            pending_payment_order = None
            try:
                if hasattr(self.db_connection, 'payment_orders'):
                    pending_payment_order = await self.db_connection.payment_orders.find_one({
                        "user_id": user.telegram_user_id,
                        "status": "pending",
                        "requires_screenshot": True,
                        "screenshot_uploaded": False
                    })
            except (AttributeError, Exception):
                # payment_orders collection doesn't exist or error, skip this check
                pass
            
            if not pending_upi_order and not pending_payment_order:
                await self.send_message(event.chat_id, "❌ No pending payment found that requires a screenshot.")
                return
            
            # Get the photo file
            photo = event.photo or event.document
            if not photo:
                await self.send_message(event.chat_id, "❌ Please send a valid image.")
                return
            
            # Get file ID from photo or document
            try:
                if hasattr(photo, 'file_id'):
                    file_id = photo.file_id
                elif hasattr(photo, 'id'):
                    file_id = photo.id
                else:
                    await self.send_message(event.chat_id, "❌ Could not process the image.")
                    return
            except Exception as e:
                logger.error(f"Error getting file ID: {e}")
                await self.send_message(event.chat_id, "❌ Could not process the image.")
                return
            
            # Handle UPI order screenshot
            if pending_upi_order:
                # Update UPI order with screenshot
                await self.db_connection.upi_orders.update_one(
                    {"order_id": pending_upi_order["order_id"]},
                    {
                        "$set": {
                            "screenshot_file_id": file_id,
                            "screenshot_uploaded_at": utc_now().isoformat() + "Z",
                            "status": "pending_verification"
                        }
                    }
                )
                
                # Forward screenshot to admin bot
                try:
                    await self.forward_upi_screenshot_to_admin(pending_upi_order, event.message, user)
                except Exception as e:
                    logger.error(f"Failed to forward UPI screenshot to admin: {e}")
                
                await self.send_message(
                    event.chat_id,
                    "✅ **Payment Screenshot Uploaded!**\n\n"
                    "📸 Your payment screenshot has been submitted for verification.\n"
                    "⏰ Admin will verify your payment within 24 hours.\n\n"
                    "You will be notified once the verification is complete."
                )
                return
            
            # Handle regular payment order screenshot
            if pending_payment_order:
                # Submit payment proof with screenshot
                from app.services.PaymentService import PaymentService
                payment_service = PaymentService(self.db_connection)
                
                proof_data = {
                    "screenshot_file_id": file_id,
                    "uploaded_at": utc_now().isoformat()
                }
                
                result = await payment_service.submit_payment_proof(
                    pending_payment_order["order_id"], 
                    proof_data
                )
                
                if result.get("success"):
                    # Forward screenshot to admin bot
                    try:
                        await self.forward_screenshot_to_admin(pending_payment_order, event.message, user)
                    except Exception as e:
                        logger.error(f"Failed to forward screenshot to admin: {e}")
                    
                    await self.send_message(
                        event.chat_id,
                        "✅ **Payment Screenshot Uploaded!**\n\n"
                        "📸 Your payment screenshot has been submitted for verification.\n"
                        "⏰ Admin will verify your payment within 24 hours.\n\n"
                        "You will be notified once the verification is complete."
                    )
                else:
                    await self.send_message(
                        event.chat_id,
                        f"❌ Failed to upload screenshot: {result.get('error', 'Unknown error')}"
                    )
                
        except Exception as e:
            logger.error(f"[BUYER] Photo handler error: {str(e)}")
            await self.send_message(event.chat_id, "❌ An error occurred while uploading screenshot.")
    
    async def forward_upi_screenshot_to_admin(self, order, message, user):
        """Forward UPI payment screenshot to admin bot"""
        try:
            # Get admin user IDs and admin bot token
            import os
            admin_user_ids_str = os.getenv('ADMIN_USER_IDS', '')
            admin_bot_token = os.getenv('ADMIN_BOT_TOKEN')
            
            if not admin_user_ids_str or not admin_bot_token:
                logger.warning("Admin configuration missing, cannot forward screenshot")
                return
            
            admin_user_ids = [int(uid.strip()) for uid in admin_user_ids_str.split(',') if uid.strip()]
            
            # Create admin bot client to send screenshot
            from telethon import TelegramClient, Button
            admin_client = TelegramClient('admin_screenshot', int(os.getenv('API_ID')), os.getenv('API_HASH'))
            await admin_client.start(bot_token=admin_bot_token)
            
            # Download the screenshot from the original message
            screenshot_file = None
            try:
                screenshot_file = await self.client.download_media(message, file=bytes)
                logger.info(f"Downloaded screenshot for order {order['order_id']}")
            except Exception as e:
                logger.error(f"Failed to download screenshot: {e}")
                await admin_client.disconnect()
                return
            
            # Send screenshot to all admin users
            for admin_id in admin_user_ids:
                try:
                    # Create caption with all details
                    caption = (
                        f"🔔 **UPI Payment Verification Required**\n\n"
                        f"👤 **User:** {user.first_name} (@{user.username or 'N/A'})\n"
                        f"💰 **Amount:** Any Amount (Quick Deposit)\n"
                        f"🆔 **Order ID:** {order['order_id']}\n"
                        f"📅 **Date:** {order.get('created_at', 'N/A')}\n\n"
                        f"Please verify the payment screenshot above."
                    )
                    
                    buttons = [
                        [Button.inline("✅ Approve", f"approve_upi_{order['order_id']}")],
                        [Button.inline("❌ Reject", f"reject_upi_{order['order_id']}")]
                    ]
                    
                    # Send the screenshot as compressed photo with caption and buttons
                    await admin_client.send_file(
                        admin_id,
                        screenshot_file,
                        caption=caption,
                        buttons=buttons,
                        force_document=False
                    )
                    
                    logger.info(f"UPI screenshot sent to admin {admin_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to send UPI screenshot to admin {admin_id}: {e}")
            
            await admin_client.disconnect()
                    
        except Exception as e:
            logger.error(f"Error in forward_upi_screenshot_to_admin: {e}")
    
    async def forward_screenshot_to_admin(self, order, message, user):
        """Forward payment screenshot to admin bot"""
        try:
            # Get admin user IDs and admin bot token
            import os
            admin_user_ids_str = os.getenv('ADMIN_USER_IDS', '')
            admin_bot_token = os.getenv('ADMIN_BOT_TOKEN')
            
            if not admin_user_ids_str or not admin_bot_token:
                logger.warning("Admin configuration missing, cannot forward screenshot")
                return
            
            admin_user_ids = [int(uid.strip()) for uid in admin_user_ids_str.split(',') if uid.strip()]
            
            # Create admin bot client to send screenshot
            from telethon import TelegramClient, Button
            admin_client = TelegramClient('admin_screenshot2', int(os.getenv('API_ID')), os.getenv('API_HASH'))
            await admin_client.start(bot_token=admin_bot_token)
            
            # Download the screenshot from the original message
            screenshot_file = None
            try:
                screenshot_file = await self.client.download_media(message, file=bytes)
                logger.info(f"Downloaded screenshot for order {order['order_id']}")
            except Exception as e:
                logger.error(f"Failed to download screenshot: {e}")
                await admin_client.disconnect()
                return
            
            # Send screenshot to all admin users
            for admin_id in admin_user_ids:
                try:
                    # Create caption with all details
                    caption = (
                        f"🔔 **Payment Verification Required**\n\n"
                        f"👤 **User:** {user.first_name} (@{user.username or 'N/A'})\n"
                        f"💰 **Amount:** ₹{order.get('amount', 'N/A')}\n"
                        f"🆔 **Order ID:** {order['order_id']}\n"
                        f"📅 **Date:** {order.get('created_at', 'N/A')}\n\n"
                        f"Please verify the payment screenshot above."
                    )
                    
                    buttons = [
                        [Button.inline("✅ Approve Payment", f"approve_payment_{order['order_id']}")],
                        [Button.inline("❌ Reject Payment", f"reject_payment_{order['order_id']}")]
                    ]
                    
                    # Send the screenshot as compressed photo with caption and buttons
                    await admin_client.send_file(
                        admin_id,
                        screenshot_file,
                        caption=caption,
                        buttons=buttons,
                        force_document=False
                    )
                    
                    logger.info(f"Payment screenshot sent to admin {admin_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to send screenshot to admin {admin_id}: {e}")
            
            await admin_client.disconnect()
                    
        except Exception as e:
            logger.error(f"Error in forward_screenshot_to_admin: {e}")
    
    async def handle_upload_screenshot_request(self, event, order_id):
        """Handle screenshot upload request"""
        try:
            await self.answer_callback(event, "📸 Please send screenshot")
            await self.send_message(
                event.chat_id,
                "📸 **Upload Payment Screenshot**\n\n"
                "Please send the screenshot of your payment confirmation as an image.\n\n"
                "Make sure the screenshot clearly shows:\n"
                "• Payment amount\n"
                "• Transaction ID/Reference\n"
                "• Date and time\n"
                "• Payment method used"
            )
        except Exception as e:
            logger.error(f"[BUYER] Screenshot request error: {str(e)}")
    
    async def notify_balance_deposited(self, user_id: int, amount: float, order_id: str):
        """Notify user when balance is successfully deposited"""
        try:
            success_message = f"""✅ **Payment Verified Successfully!**

💰 **Amount:** ₹{amount:.2f} has been deposited into your funds
🆔 **Order ID:** {order_id}
📅 **Date:** {utc_now().strftime('%Y-%m-%d %H:%M:%S')} UTC

🎉 Your balance has been updated and is ready to use!

Thank you for your payment! 💚"""
            
            buttons = [
                [Button.inline("💰 Check Balance", "my_balance")],
                [Button.inline("🛒 Browse Accounts", "browse_accounts")],
                [Button.inline("🔙 Main Menu", "back_to_main")]
            ]
            
            await self.send_message(user_id, success_message, buttons)
            
        except Exception as e:
            logger.error(f"Error notifying balance deposit: {str(e)}")
    

    
    async def handle_payment_method(self, event, user, method, listing_id):
        """Handle payment method selection"""
        try:
            # Get listing
            listing = await self.db_connection.listings.find_one({"_id": listing_id})
            if not listing or listing["status"] != "active":
                await self.edit_message(
                    event,
                    "❌ **Listing Not Available**\n\nThis account is no longer available for sale.",
                    [[Button.inline("🔙 Back", "browse_accounts")]]
                )
                return
            
            # Check if payment method is available
            from app.services.PaymentSettingsService import PaymentSettingsService
            payment_settings_service = PaymentSettingsService(self.db_connection)
            
            if not await payment_settings_service.is_payment_method_enabled(method):
                # Get available methods for fallback
                available_methods = await payment_settings_service.get_available_payment_methods()
                method_list = ", ".join([m['name'] for m in available_methods])
                
                await self.edit_message(
                    event,
                    f"❌ **Payment Method Unavailable**\n\n{method.upper()} is not configured.\n\n**Available methods:** {method_list}",
                    [[Button.inline("🔙 Back", f"buy_{listing_id}")]]
                )
                return
            
            # Handle different payment methods
            if method == "upi":
                await self.handle_upi_payment(event, listing_id, listing["price"])
            elif method == "razorpay":
                await self.handle_razorpay_payment(event, listing_id, listing["price"])
            elif method == "crypto":
                await self.handle_crypto_payment(event, listing_id, listing["price"])
            elif method == "otp":
                await self.handle_otp_payment_and_transfer(event, user, listing, "")
            else:
                # Get available methods for error message
                available_methods = await payment_settings_service.get_available_payment_methods()
                method_list = ", ".join([m['name'] for m in available_methods])
                
                await self.edit_message(
                    event,
                    f"❌ **Unsupported Payment Method**\n\n{method} is not supported.\n\n**Available methods:** {method_list}",
                    [[Button.inline("🔙 Back", f"buy_{listing_id}")]]
                )
            
        except Exception as e:
            logger.error(f"Payment method handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_otp_payment_and_transfer(self, event, user, listing, transaction_id):
        """Handle OTP-based payment and account transfer"""
        try:
            # Get account details
            account = await self.db_connection.accounts.find_one({"_id": listing["account_id"]})
            
            if not account:
                await self.edit_message(
                    event,
                    "❌ **Account Not Found**\n\nThe account details could not be retrieved.",
                    [[Button.inline("🔙 Back", "browse_accounts")]]
                )
                return
            
            # Show OTP transfer process
            otp_transfer_message = f"""
📱 **OTP Payment & Transfer**

💰 **Price:** ${listing['price']:.2f}
📱 **Account Phone:** {account.get('phone_number', 'Hidden')}

**Process:**
1. **Payment**: Complete payment first
2. **OTP Verification**: Receive OTP on your phone
3. **Account Transfer**: Get full account access

**Important:**
• You'll receive OTP on the account's phone number
• Make sure you have access to that phone number
• Transfer is instant after OTP verification

**Payment Methods:**
            """
            
            buttons = [
                [Button.inline("💳 Pay with UPI", f"otp_pay_upi_{transaction_id}")],
                [Button.inline("₿ Pay with Crypto", f"otp_pay_crypto_{transaction_id}")],
                [Button.inline("🔙 Cancel", "cancel_otp_purchase")]
            ]
            
            await self.edit_message(event, otp_transfer_message, buttons)
            
        except Exception as e:
            logger.error(f"OTP payment and transfer handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_upi_payment(self, event, listing_id, amount):
        """Handle UPI payment process"""
        try:
            user = await self.get_or_create_user(event)
            
            # Create payment order using PaymentService
            from app.services.PaymentService import PaymentService
            payment_service = PaymentService(self.db_connection)
            
            payment_result = await payment_service.create_payment_order(
                user.telegram_user_id, amount, "upi_direct", "account_purchase"
            )
            
            if payment_result.get("error"):
                await self.edit_message(
                    event,
                    f"❌ {payment_result['error']}",
                    [[Button.inline("🔙 Back", f"buy_{listing_id}")]]
                )
                return
            
            # Get UPI settings
            from app.services.PaymentSettingsService import PaymentSettingsService
            payment_settings_service = PaymentSettingsService(self.db_connection)
            upi_settings = await payment_settings_service.get_upi_settings()
            
            if not upi_settings.get("enabled") or not upi_settings.get("merchant_vpa"):
                # Get available methods for fallback
                from app.services.PaymentSettingsService import PaymentSettingsService
                payment_settings_service = PaymentSettingsService(self.db_connection)
                available_methods = await payment_settings_service.get_available_payment_methods()
                method_list = ", ".join([m['name'] for m in available_methods])
                
                await self.edit_message(
                    event,
                    f"❌ **UPI Not Available**\n\nUPI is not configured.\n\n**Available methods:** {method_list}",
                    [[Button.inline("🔙 Back", f"buy_{listing_id}")]]
                )
                return
            
            calculation = payment_result["calculation"]
            
            # Create UPI payment link
            upi_id = upi_settings.get("merchant_vpa")
            merchant_name = upi_settings.get("merchant_name", "Telegram Marketplace")
            
            # Generate UPI link
            upi_link = f"upi://pay?pa={upi_id}&pn={merchant_name}&am={calculation['total_amount']:.2f}&cu=INR&tn=Account Purchase {payment_result['order_id']}"
            
            message = f"""💳 **UPI Payment**

{payment_service.create_payment_summary_message(calculation)}

**Payment Details:**
• UPI ID: `{upi_id}`
• Amount: ₹{calculation['total_amount']:.2f}
• Reference: {payment_result['order_id']}

**Instructions:**
1. Click the UPI link below or scan QR code
2. Complete payment in your UPI app
3. Upload payment screenshot (REQUIRED)
4. Wait for admin verification

[Pay with UPI]({upi_link})"""
            
            buttons = [
                [Button.url("💳 Pay with UPI", upi_link)],
                [Button.inline("📸 Upload Screenshot", f"upload_screenshot_{payment_result['order_id']}")],
                [Button.inline("❌ Cancel", f"buy_{listing_id}")]
            ]
            
            await self.edit_message(event, message, buttons)
            
        except Exception as e:
            logger.error(f"[BUYER] UPI payment error: {str(e)}")
            await self.edit_message(event, "❌ UPI payment setup failed. Please try again.")
    
    async def handle_razorpay_payment(self, event, listing_id, amount):
        """Handle Razorpay payment process"""
        try:
            user = await self.get_or_create_user(event)
            
            # Create payment order using PaymentService
            from app.services.PaymentService import PaymentService
            payment_service = PaymentService(self.db_connection)
            
            payment_result = await payment_service.create_payment_order(
                user.telegram_user_id, amount, "razorpay", "account_purchase"
            )
            
            if payment_result.get("error"):
                await self.edit_message(
                    event,
                    f"❌ {payment_result['error']}",
                    [[Button.inline("🔙 Back", f"buy_{listing_id}")]]
                )
                return
            
            calculation = payment_result["calculation"]
            
            message = f"""🔐 **Razorpay Payment**

{payment_service.create_payment_summary_message(calculation)}

**Payment Options:**
• Credit/Debit Cards
• UPI (PhonePe, GPay, Paytm)
• Net Banking
• Wallets

**Order ID:** {payment_result['order_id']}

Click below to proceed with secure payment:"""
            
            buttons = [
                [Button.inline("🔐 Pay with Razorpay", f"razorpay_pay_{payment_result['order_id']}")],
                [Button.inline("❌ Cancel", f"buy_{listing_id}")]
            ]
            
            await self.edit_message(event, message, buttons)
            
        except Exception as e:
            logger.error(f"[BUYER] Razorpay payment error: {str(e)}")
            await self.edit_message(event, "❌ Razorpay payment setup failed. Please try again.")
    
    async def handle_crypto_payment(self, event, listing_id, amount):
        """Handle cryptocurrency payment process"""
        try:
            user = await self.get_or_create_user(event)
            
            # Create payment order using PaymentService
            from app.services.PaymentService import PaymentService
            payment_service = PaymentService(self.db_connection)
            
            payment_result = await payment_service.create_payment_order(
                user.telegram_user_id, amount, "crypto", "account_purchase"
            )
            
            if payment_result.get("error"):
                await self.edit_message(
                    event,
                    f"❌ {payment_result['error']}",
                    [[Button.inline("🔙 Back", f"buy_{listing_id}")]]
                )
                return
            
            # Get crypto settings
            from app.services.PaymentSettingsService import PaymentSettingsService
            payment_settings_service = PaymentSettingsService(self.db_connection)
            crypto_settings = await payment_settings_service.get_crypto_settings()
            
            if not crypto_settings.get("enabled") or not crypto_settings.get("wallet_address"):
                # Get available methods for fallback
                from app.services.PaymentSettingsService import PaymentSettingsService
                payment_settings_service = PaymentSettingsService(self.db_connection)
                available_methods = await payment_settings_service.get_available_payment_methods()
                method_list = ", ".join([m['name'] for m in available_methods])
                
                await self.edit_message(
                    event,
                    f"❌ **Crypto Not Available**\n\nCryptocurrency payments are not configured.\n\n**Available methods:** {method_list}",
                    [[Button.inline("🔙 Back", f"buy_{listing_id}")]]
                )
                return
            
            calculation = payment_result["calculation"]
            
            # Get crypto addresses
            wallet_address = crypto_settings.get("wallet_address")
            
            message = f"""₿ **Cryptocurrency Payment**

{payment_service.create_payment_summary_message(calculation)}

**Payment Options:**

**Wallet Address:**
`{wallet_address}`

**Amount:** ${calculation['total_amount']:.2f} USD equivalent
**Reference:** {payment_result['order_id']}

**Instructions:**
1. Send exact amount to the address above
2. Upload transaction screenshot (REQUIRED)
3. Wait for blockchain confirmation
4. Admin will verify within 24 hours"""
            
            buttons = [
                [Button.inline("📸 Upload Screenshot", f"upload_screenshot_{payment_result['order_id']}")],
                [Button.inline("❌ Cancel", f"buy_{listing_id}")]
            ]
            
            await self.edit_message(event, message, buttons)
            
        except Exception as e:
            logger.error(f"[BUYER] Crypto payment error: {str(e)}")
            await self.edit_message(event, "❌ Crypto payment setup failed. Please try again.")
    
    async def process_buyer_otp(self, event, user, otp_code):
        """Process buyer OTP for account transfer"""
        try:
            # Show processing message
            processing_msg = await self.send_message(
                event.chat_id,
                "🔍 **Verifying OTP...**\n\nPlease wait while we complete the account transfer."
            )
            
            # Transfer account to buyer using AccountLoginService
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
            transaction_id = user_doc.get("temp_transaction")
            
            if not transaction_id:
                await self.client.edit_message(event.chat_id, processing_msg.id, "❌ Session expired. Please start over.")
                return
            
            # Get transaction to find account
            transaction = await self.db_connection.transactions.find_one({"_id": transaction_id})
            if not transaction:
                await self.client.edit_message(event.chat_id, processing_msg.id, "❌ Transaction not found.")
                return
            
            # Transfer account ownership
            transfer_result = await self.account_login_service.transfer_account_to_buyer(
                str(transaction["account_id"]), user.telegram_user_id
            )
            
            if transfer_result['success']:
                # Clear user state
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$unset": {"state": "", "temp_transaction": ""}}
                )
                
                await self.client.edit_message(
                    event.chat_id,
                    processing_msg.id,
                    f"""
✅ **Account Transfer Completed!**

🎉 **Congratulations!** You now own this Telegram account.

**Your Account Details:**
📱 **Session String:** `{transfer_result['session_string'][:50]}...`

**Next Steps:**
1. Save the session string securely
2. Use it with Telegram clients (Telethon, Pyrogram)
3. The account is now fully yours

**Important:**
• Keep your session string private
• You have full account access
• Previous owner has been logged out

Thank you for your purchase! 🎉
                    """,
                    buttons=[[Button.inline("🛒 Buy Another", "browse_accounts")], 
                             [Button.inline("🔙 Main Menu", "back_to_main")]]
                )
                
            elif transfer_result.get('requires_password'):
                await self.client.edit_message(
                    event.chat_id,
                    processing_msg.id,
                    """
🔐 **Two-Factor Authentication Required**

The account has 2FA enabled. Please enter the password:

**Note:** Your password is encrypted and not stored.
                    """,
                    buttons=[[Button.inline("❌ Cancel", "cancel_otp_purchase")]]
                )
                
                # Set state for 2FA password
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$set": {"state": "awaiting_buyer_2fa", "temp_otp": otp_code}}
                )
                
            else:
                await self.client.edit_message(
                    event.chat_id,
                    processing_msg.id,
                    f"❌ **Transfer Failed**\n\n{transfer_result['error']}\n\nPlease contact support for assistance."
                )
            
        except Exception as e:
            logger.error(f"Process buyer OTP error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to process OTP. Please try again.")
    
    async def process_buyer_2fa_password(self, event, user, password):
        """Process buyer 2FA password"""
        try:
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
            temp_otp = user_doc.get("temp_otp")
            
            if not temp_otp:
                await self.send_message(event.chat_id, "❌ Session expired. Please start over.")
                return
            
            # Show processing message
            processing_msg = await self.send_message(
                event.chat_id,
                "🔐 **Verifying Password...**\n\nPlease wait while we complete the transfer."
            )
            
            # Complete transfer with password
            transfer_result = await self.otp_service.complete_account_transfer(
                user.telegram_user_id,
                temp_otp,
                password
            )
            
            if transfer_result['success']:
                # Clear user state
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$unset": {"state": "", "temp_otp": "", "temp_transaction": ""}}
                )
                
                await self.client.edit_message(
                    event.chat_id,
                    processing_msg.id,
                    f"""
✅ **Account Transfer Completed!**

🎉 **Congratulations!** You now own this Telegram account.

**Your Account Details:**
📱 **Session String:** `{transfer_result['session_string'][:50]}...`

**Next Steps:**
1. Save the session string securely
2. Use it with Telegram clients
3. The account is now fully yours

Thank you for your purchase! 🎉
                    """,
                    buttons=[[Button.inline("🛒 Buy Another", "browse_accounts")], 
                             [Button.inline("🔙 Main Menu", "back_to_main")]]
                )
                
            else:
                await self.client.edit_message(
                    event.chat_id,
                    processing_msg.id,
                    f"❌ **Transfer Failed**\n\n{transfer_result['error']}\n\nPlease contact support."
                )
            
        except Exception as e:
            logger.error(f"Process buyer 2FA password error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to verify password. Please try again.")
    
    async def handle_resend_buyer_otp(self, event, user_id):
        """Handle buyer OTP resend"""
        try:
            # This would resend OTP for buyer verification
            await self.edit_message(
                event,
                "📱 **OTP Resent**\n\nPlease check your phone for the new verification code.",
                buttons=create_otp_verification_keyboard(user_id)
            )
            
        except Exception as e:
            logger.error(f"Resend buyer OTP error: {str(e)}")
            await self.edit_message(event, "❌ Failed to resend OTP. Please try again.")
    
    async def handle_cancel_otp_purchase(self, event, user):
        """Handle OTP purchase cancellation"""
        try:
            # Clear user state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"state": "", "temp_otp": "", "temp_transaction": ""}}
            )
            
            await self.edit_message(
                event,
                "❌ **Purchase Cancelled**\n\nYour OTP purchase has been cancelled.",
                [[Button.inline("🛒 Browse Accounts", "browse_accounts")], 
                 [Button.inline("🔙 Main Menu", "back_to_main")]]
            )
            
        except Exception as e:
            logger.error(f"Cancel OTP purchase error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    # Keep existing methods from original buyer_bot.py
    async def handle_browse_accounts(self, event):
        """Handle browse accounts"""
        try:
            # Get available countries from active listings
            pipeline = [
                {"$match": {"status": "active"}},
                {"$group": {"_id": "$country", "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}}
            ]
            
            countries_data = await self.db_connection.listings.aggregate(pipeline).to_list(length=None)
            
            if not countries_data:
                await self.edit_message(
                    event,
                    "🛒 **Browse Accounts**\n\n❌ No accounts available for sale at the moment.\n\nPlease check back later!",
                    [[Button.inline("🔙 Back", "back_to_main")]]
                )
                return
            
            countries = [item["_id"] for item in countries_data]
            
            browse_message = """
🛒 **Browse Accounts by Country**

Select a country to see available accounts:
            """
            
            buttons = create_country_menu(countries)
            await self.edit_message(event, browse_message, buttons)
            
        except Exception as e:
            logger.error(f"Browse accounts handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_country_selection(self, event, country):
        """Handle country selection"""
        try:
            # Get available years for this country
            pipeline = [
                {"$match": {"status": "active", "country": country}},
                {"$group": {"_id": "$creation_year", "count": {"$sum": 1}}},
                {"$sort": {"_id": -1}}
            ]
            
            years_data = await self.db_connection.listings.aggregate(pipeline).to_list(length=None)
            
            if not years_data:
                await self.edit_message(
                    event,
                    f"🌍 **{country} Accounts**\n\n❌ No accounts available for {country} at the moment.",
                    [[Button.inline("🔙 Back", "browse_accounts")]]
                )
                return
            
            years = [item["_id"] for item in years_data]
            
            country_message = f"""
🌍 **{country} Accounts**

Select creation year:
            """
            
            buttons = create_year_menu(years, country)
            await self.edit_message(event, country_message, buttons)
            
        except Exception as e:
            logger.error(f"Country selection handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_year_selection(self, event, country, year):
        """Handle year selection and show listings"""
        try:
            # Get listings for this country and year
            listings = await self.db_connection.listings.find({
                "status": "active",
                "country": country,
                "creation_year": year
            }).sort("created_at", -1).to_list(length=20)
            
            if not listings:
                await self.edit_message(
                    event,
                    f"📅 **{country} {year} Accounts**\n\n❌ No accounts available for {country} {year}.",
                    [[Button.inline("🔙 Back", f"country_{country}")]]
                )
                return
            
            listings_message = f"📅 **{country} {year} Accounts** ({len(listings)} available)\n\n"
            
            buttons = []
            for i, listing in enumerate(listings[:10]):  # Show max 10 listings
                # Get account details (limited info for privacy)
                account = await self.db_connection.accounts.find_one({"_id": listing["account_id"]})
                
                username_display = "No username"
                if account and account.get("username"):
                    # Mask username for privacy
                    username = account["username"]
                    if len(username) > 4:
                        username_display = username[:2] + "*" * (len(username) - 4) + username[-2:]
                    else:
                        username_display = "*" * len(username)
                
                method_emoji = "📱" if account and account.get("obtained_via") == "otp" else "📤"
                listing_text = f"{method_emoji} {username_display} - ${listing['price']:.2f}"
                buttons.append([Button.inline(listing_text, f"listing_{listing['_id']}")])
            
            # Add navigation buttons
            buttons.append([Button.inline("🔙 Back", f"country_{country}")])
            
            await self.edit_message(event, listings_message, buttons)
            
        except Exception as e:
            logger.error(f"Year selection handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_listing_details(self, event, listing_id):
        """Show listing details"""
        try:
            # Get listing
            listing = await self.db_connection.listings.find_one({"_id": listing_id})
            if not listing or listing["status"] != "active":
                await self.edit_message(
                    event,
                    "❌ **Listing Not Available**\n\nThis account is no longer available for sale.",
                    [[Button.inline("🔙 Back", "browse_accounts")]]
                )
                return
            
            # Get account details (limited for privacy)
            account = await self.db_connection.accounts.find_one({"_id": listing["account_id"]})
            
            username_display = "No username"
            if account and account.get("username"):
                username = account["username"]
                if len(username) > 4:
                    username_display = username[:2] + "*" * (len(username) - 4) + username[-2:]
                else:
                    username_display = "*" * len(username)
            
            method = account.get("obtained_via", "upload") if account else "upload"
            method_text = "Phone + OTP Verified" if method == "otp" else "Session Upload"
            method_emoji = "📱" if method == "otp" else "📤"
            
            details_message = f"""
💎 **Account Details**

{method_emoji} **Method:** {method_text}
🌍 **Country:** {listing['country']}
📅 **Creation Year:** {listing['creation_year']}
👤 **Username:** {username_display}
💰 **Price:** ${listing['price']:.2f}

✅ **Verified Features:**
• Zero contacts
• Clean spam status
• No bot memberships
• Active sessions cleared
• Admin approved

🔒 **What You Get:**
• Full session access
• Complete account ownership
• All login credentials
• Instant delivery

Ready to purchase this account?
            """
            
            buttons = [
                [Button.inline("🛒 Buy Now", f"buy_{listing_id}")],
                [Button.inline("🔙 Back", f"year_{listing['country']}_{listing['creation_year']}")]
            ]
            
            await self.edit_message(event, details_message, buttons)
            
        except Exception as e:
            logger.error(f"Listing details handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_buy_listing(self, event, user, listing_id):
        """Handle buy listing"""
        try:
            # Get listing
            listing = await self.db_connection.listings.find_one({"_id": listing_id})
            if not listing or listing["status"] != "active":
                await self.edit_message(
                    event,
                    "❌ **Listing Not Available**\n\nThis account is no longer available for sale.",
                    [[Button.inline("🔙 Back", "browse_accounts")]]
                )
                return
            
            # Get available payment methods
            from app.services.PaymentSettingsService import PaymentSettingsService
            payment_settings_service = PaymentSettingsService(self.db_connection)
            available_methods = await payment_settings_service.get_available_payment_methods()
            
            # Create payment method description
            method_descriptions = []
            for method in available_methods:
                method_descriptions.append(f"{method['icon']} **{method['name']}**: {method['description']}")
            
            buy_message = f"""
🛒 **Purchase Account**

💰 **Price:** ${listing['price']:.2f}
🌍 **Country:** {listing['country']}
📅 **Year:** {listing['creation_year']}

**Available Payment Methods:**
{chr(10).join(method_descriptions)}

After payment confirmation:
1. Account session will be delivered
2. Full ownership transferred to you
3. OTP destroyer will be disabled
4. You can start using immediately
            """
            
            # Create payment buttons based on available methods
            buttons = []
            for method in available_methods:
                if method['id'] == 'upi':
                    buttons.append([Button.inline(f"{method['icon']} {method['name']}", f"pay_upi_{listing_id}")])
                elif method['id'] == 'razorpay':
                    buttons.append([Button.inline(f"{method['icon']} {method['name']}", f"pay_razorpay_{listing_id}")])
                elif method['id'] == 'crypto':
                    buttons.append([Button.inline(f"{method['icon']} {method['name']}", f"pay_crypto_{listing_id}")])
            
            buttons.append([Button.inline("🔙 Back", f"listing_{listing_id}")])
            
            await self.edit_message(event, buy_message, buttons)
            
        except Exception as e:
            logger.error(f"Buy listing handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_my_purchases(self, event, user):
        """Show user's purchases"""
        try:
            # Get user's purchase transactions
            purchases = await self.db_connection.transactions.find({
                "user_id": user.telegram_user_id,
                "type": "account_sale"
            }).sort("created_at", -1).to_list(length=10)
            
            if not purchases:
                await self.edit_message(
                    event,
                    "💰 **My Purchases**\n\nYou haven't purchased any accounts yet.",
                    [[Button.inline("🛒 Browse Accounts", "browse_accounts")], 
                     [Button.inline("📱 Buy via OTP", "buy_via_otp")],
                     [Button.inline("🔙 Back", "back_to_main")]]
                )
                return
            
            purchases_message = "💰 **My Purchases**\n\n"
            
            for purchase in purchases:
                status_emoji = {
                    "pending": "⏳",
                    "confirmed": "✅",
                    "failed": "❌",
                    "cancelled": "🚫"
                }.get(purchase["status"], "❓")
                
                # Get account info if available
                account_info = "Account"
                method_emoji = "📤"
                if purchase.get("account_id"):
                    account = await self.db_connection.accounts.find_one({"_id": purchase["account_id"]})
                    if account:
                        if account.get("username"):
                            username = account["username"]
                            if len(username) > 4:
                                account_info = username[:2] + "*" * (len(username) - 4) + username[-2:]
                            else:
                                account_info = "*" * len(username)
                        method_emoji = "📱" if account.get("obtained_via") == "otp" else "📤"
                
                purchases_message += f"{status_emoji} {method_emoji} **{account_info}** - ${purchase['amount']:.2f}\n"
                purchases_message += f"   Status: {purchase['status'].title()}\n"
                purchases_message += f"   Date: {purchase['created_at'].strftime('%Y-%m-%d %H:%M')}\n\n"
            
            buttons = [
                [Button.inline("🛒 Buy More", "browse_accounts")],
                [Button.inline("📱 Buy via OTP", "buy_via_otp")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, purchases_message, buttons)
            
        except Exception as e:
            logger.error(f"My purchases handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_my_balance(self, event, user):
        """Handle my balance"""
        try:
            # Get user's current balance from user document
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user.telegram_user_id})
            current_balance = user_doc.get("balance", 0) if user_doc else 0
            
            # Get transaction history for display
            deposits = await self.db_connection.transactions.find({
                "user_id": user.telegram_user_id,
                "type": "deposit",
                "status": "confirmed"
            }).to_list(length=None)
            
            purchases = await self.db_connection.transactions.find({
                "user_id": user.telegram_user_id,
                "type": "account_sale",
                "status": "confirmed"
            }).to_list(length=None)
            
            total_deposits = sum(t["amount"] for t in deposits)
            total_spent = sum(t["amount"] for t in purchases)
            balance = current_balance  # Use actual balance from user document
            
            balance_message = f"""
💰 **My Balance**

💵 **Current Balance:** ₹{balance:.2f}

💳 **Total Deposits:** ₹{total_deposits:.2f}
💸 **Total Spent:** ₹{total_spent:.2f}

📈 **Recent Activity:**
            """
            
            # Show recent transactions
            recent = await self.db_connection.transactions.find({
                "user_id": user.telegram_user_id
            }).sort("created_at", -1).limit(5).to_list(length=5)
            
            if recent:
                for tx in recent:
                    emoji = "⬆️" if tx["type"] == "deposit" else "⬇️"
                    status_emoji = "✅" if tx["status"] == "confirmed" else "⏳"
                    balance_message += f"{emoji} {status_emoji} ₹{tx['amount']:.2f} - {tx['type'].title()}\n"
            else:
                balance_message += "No recent transactions\n"
            
            buttons = [
                [Button.inline("💸 Add Funds", "add_funds")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, balance_message, buttons)
            
        except Exception as e:
            logger.error(f"My balance handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_add_funds(self, event, user):
        """Handle add funds"""
        try:
            # Check available payment methods
            from app.services.PaymentSettingsService import PaymentSettingsService
            payment_settings_service = PaymentSettingsService(self.db_connection)
            available_methods = await payment_settings_service.get_available_payment_methods()
            
            # Show available deposit methods
            method_buttons = []
            for method in available_methods:
                if method['id'] == 'upi':
                    method_buttons.append([Button.inline(f"{method['icon']} {method['name']}", "deposit_upi")])
                elif method['id'] == 'razorpay':
                    method_buttons.append([Button.inline(f"{method['icon']} {method['name']}", "deposit_razorpay")])
                elif method['id'] == 'crypto':
                    method_buttons.append([Button.inline(f"{method['icon']} {method['name']}", "deposit_crypto")])
            
            method_buttons.append([Button.inline("❌ Cancel", "back_to_main")])
            
            method_descriptions = [f"{method['icon']} **{method['name']}**: {method['description']}" for method in available_methods]
            
            await self.edit_message(
                event,
                f"💰 **Add Funds to Your Account**\n\n**Available Payment Methods:**\n{chr(10).join(method_descriptions)}\n\nChoose your preferred payment method:",
                method_buttons
            )
            
        except Exception as e:
            logger.error(f"Add funds handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_help(self, event):
        """Handle help"""
        try:
            help_message = """
❓ **Help & Support**

**How to Buy Accounts:**
1. Browse accounts by country/year
2. Select an account you like
3. Choose payment method
4. Complete payment
5. Receive account instantly

**Payment Methods:**
💳 **UPI**: Instant Indian payments
₿ **Bitcoin**: Cryptocurrency payments
💎 **USDT**: Stable cryptocurrency
📱 **OTP Transfer**: Direct phone transfer

**Account Quality:**
✅ All accounts are verified
✅ Zero contacts guaranteed
✅ Clean spam history
✅ Admin approved

**Need More Help?**
Contact our support team for assistance.
            """
            
            buttons = [
                [Button.inline("🎆 Contact Support", "contact_support")],
                [Button.inline("📜 FAQ", "faq")],
                [Button.inline("🔙 Back", "back_to_main")]
            ]
            
            await self.edit_message(event, help_message, buttons)
            
        except Exception as e:
            logger.error(f"Help handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_back_to_main(self, event):
        """Handle back to main menu"""
        try:
            buttons = create_main_menu(is_seller=False)
            await self.edit_message(
                event,
                "🛒 **Telegram Account Marketplace**\n\nWhat would you like to do?",
                buttons
            )
            
        except Exception as e:
            logger.error(f"Back to main handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_contact_support(self, event):
        """Handle contact support"""
        try:
            support_message = """
🎆 **Contact Support**

Our support team is here to help you!

**Available Support:**
• Account purchase issues
• Payment problems
• Technical difficulties
• General questions

**Response Time:** Usually within 2-4 hours

Please describe your issue and we'll get back to you soon.
            """
            
            await self.edit_message(
                event,
                support_message,
                [[Button.inline("🔙 Back to Help", "help")]]
            )
            
        except Exception as e:
            logger.error(f"Contact support handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_faq(self, event):
        """Handle FAQ"""
        try:
            faq_message = """
📜 **Frequently Asked Questions**

**Q: How do I buy an account?**
A: Browse accounts, select one, choose payment method, and complete payment.

**Q: Are accounts safe to use?**
A: Yes, all accounts are verified and have clean history.

**Q: What payment methods do you accept?**
A: UPI, Bitcoin, USDT, and OTP transfer.

**Q: How long does delivery take?**
A: Instant delivery after payment confirmation.

**Q: Can I get a refund?**
A: Refunds are processed case-by-case. Contact support.

**Q: What if the account doesn't work?**
A: We provide 24-hour replacement guarantee.
            """
            
            await self.edit_message(
                event,
                faq_message,
                [[Button.inline("🔙 Back to Help", "help")]]
            )
            
        except Exception as e:
            logger.error(f"FAQ handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_deposit_method(self, event, user, method):
        """Handle deposit method selection"""
        try:
            # Check if method is available
            from app.services.PaymentSettingsService import PaymentSettingsService
            payment_settings_service = PaymentSettingsService(self.db_connection)
            
            if not await payment_settings_service.is_payment_method_enabled(method):
                # Get available methods for fallback
                available_methods = await payment_settings_service.get_available_payment_methods()
                method_list = ", ".join([m['name'] for m in available_methods])
                
                await self.edit_message(
                    event,
                    f"❌ **{method.upper()} Not Available**\n\n{method.upper()} is not configured.\n\n**Available methods:** {method_list}",
                    [[Button.inline("🔙 Back", "add_funds")]]
                )
                return
            
            if method == "upi":
                # Show UPI deposit options
                deposit_message = """
💳 **UPI Deposit**

Choose deposit method:

🎯 **Quick Deposit**: Pay any amount you want
💵 **Fixed Amount**: Enter specific amount

**Features:**
• Instant processing
• Auto-verification for 5 minutes
• Minimum: ₹1
• QR code + UPI link provided
                """
                
                buttons = [
                    [Button.inline("🎯 Quick Deposit (Any Amount)", "upi_quick_deposit")],
                    [Button.inline("💵 Fixed Amount", "upi_fixed_amount")],
                    [Button.inline("❌ Cancel", "add_funds")]
                ]
                
                await self.edit_message(
                    event,
                    deposit_message,
                    buttons
                )
            elif method == "razorpay":
                # Handle Razorpay deposit
                await self.edit_message(
                    event,
                    "🔐 **Razorpay Deposit**\n\nEnter the amount you want to deposit:\n\n**Examples:** 100, 500, 1000\n**Range:** ₹1 - ₹100,000\n\nSecure payment via Razorpay gateway.",
                    [[Button.inline("❌ Cancel", "add_funds")]]
                )
                
                # Set user state for amount input
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$set": {"state": f"awaiting_deposit_amount_{method}"}}
                )
            elif method == "crypto":
                # Handle crypto deposit
                deposit_message = """
₿ **Cryptocurrency Deposit**

Add funds via cryptocurrency:

**Minimum:** $10
**Maximum:** $1000
**Processing:** 1-3 confirmations
**Supported:** Bitcoin, USDT (TRC20)

Enter the amount you want to deposit (in USD):
                """
                
                await self.edit_message(
                    event,
                    deposit_message,
                    [[Button.inline("❌ Cancel", "add_funds")]]
                )
                
                # Set user state for amount input
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {"$set": {"state": f"awaiting_deposit_amount_{method}"}}
                )
            else:
                await self.edit_message(
                    event,
                    f"❌ **Unsupported Method**\n\n{method} is not supported.",
                    [[Button.inline("🔙 Back", "add_funds")]]
                )
            
        except Exception as e:
            logger.error(f"Deposit method handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def process_deposit_amount(self, event, user, method, amount_text):
        """Process deposit amount input"""
        try:
            # Clear user state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"state": ""}}
            )
            
            # Validate amount
            try:
                amount = float(amount_text.replace("$", "").replace(",", ""))
            except ValueError:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Amount**\n\nPlease enter a valid number.\nExample: 25 or $25"
                )
                return
            
            # Check minimum and maximum limits
            min_amount = 5 if method == "upi" else 10
            max_amount = 500 if method == "upi" else 1000
            
            if amount < min_amount:
                await self.send_message(
                    event.chat_id,
                    f"❌ **Amount Too Low**\n\nMinimum deposit: ${min_amount}"
                )
                return
            
            if amount > max_amount:
                await self.send_message(
                    event.chat_id,
                    f"❌ **Amount Too High**\n\nMaximum deposit: ${max_amount}"
                )
                return
            
            # Create deposit payment (using dummy listing_id for deposits)
            deposit_listing_id = "deposit_" + str(user.telegram_user_id)
            
            if method == "upi":
                payment_result = await self.payment_service.create_upi_payment(
                    user.telegram_user_id, amount, deposit_listing_id
                )
            else:
                currency = "BTC" if method == "bitcoin" else "USDT"
                payment_result = await self.payment_service.create_crypto_payment(
                    user.telegram_user_id, amount, deposit_listing_id, currency
                )
            
            if not payment_result.get("success"):
                await self.send_message(
                    event.chat_id,
                    f"❌ **Payment Error**\n\n{payment_result.get('error', 'Unknown error')}"
                )
                return
            
            # Create deposit transaction
            transaction_data = {
                "user_id": user.telegram_user_id,
                "type": "deposit",
                "amount": amount,
                "payment_method": method,
                "status": "pending",
                "payment_reference": payment_result.get("payment_id"),
                "created_at": utc_now()
            }
            
            result = await self.db_connection.transactions.insert_one(transaction_data)
            transaction_id = str(result.inserted_id)
            
            # Show payment instructions
            if method == "upi":
                payment_message = f"""
💳 **UPI Deposit**

💰 **Amount:** ₹{amount * 80:.2f} (${amount:.2f})
🆔 **Payment ID:** {payment_result['payment_id']}

**Payment Instructions:**
1. Click the UPI link below
2. Complete payment in your UPI app
3. Send screenshot after payment
4. Funds added after verification

🔗 **UPI Link:** {payment_result.get('upi_url', 'N/A')}

⏰ **Expires in 15 minutes**
                """
            else:
                currency = payment_result.get('crypto_currency', 'USDT')
                crypto_amount = payment_result.get('crypto_amount', amount)
                address = payment_result.get('address', 'N/A')
                network = payment_result.get('network', 'TRC20')
                
                payment_message = f"""
{'₿' if currency == 'BTC' else '💎'} **{currency} Deposit**

💰 **Amount:** {crypto_amount:.6f} {currency}
🏦 **Network:** {network}
📍 **Address:** `{address}`

**Payment Instructions:**
1. Send exactly {crypto_amount:.6f} {currency}
2. To the address above
3. Send transaction hash after payment
4. Funds added after confirmation

⏰ **Expires in 30 minutes**
                """
            
            buttons = [
                [Button.inline("✅ Payment Sent", f"deposit_sent_{transaction_id}")],
                [Button.inline("❌ Cancel", "add_funds")]
            ]
            
            await self.send_message(event.chat_id, payment_message, buttons)
            
        except Exception as e:
            logger.error(f"Process deposit amount error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to process deposit. Please try again.")
    
    async def handle_deposit_sent(self, event, user, transaction_id):
        """Handle deposit sent confirmation"""
        try:
            # Update transaction status
            await self.db_connection.transactions.update_one(
                {"_id": transaction_id},
                {"$set": {"status": "pending_verification", "updated_at": utc_now()}}
            )
            
            await self.edit_message(
                event,
                """
✅ **Payment Confirmation Received**

Thank you! We've received your payment confirmation.

**Next Steps:**
1. Our team will verify your payment
2. Funds will be added to your account
3. You'll receive a confirmation message

**Processing Time:**
• UPI: 5-15 minutes
• Crypto: 30-60 minutes

You can check your balance anytime from the main menu.
                """,
                [[Button.inline("💰 Check Balance", "my_balance")], 
                 [Button.inline("🔙 Main Menu", "back_to_main")]]
            )
            
        except Exception as e:
            logger.error(f"Deposit sent handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_payment_sent(self, event, user, transaction_id):
        """Handle payment sent confirmation"""
        try:
            await self.db_connection.transactions.update_one(
                {"_id": transaction_id},
                {"$set": {"status": "pending_verification", "updated_at": utc_now()}}
            )
            
            await self.edit_message(
                event,
                """
✅ **Payment Confirmation Received**

Thank you! We've received your payment confirmation.

**Next Steps:**
1. Admin will verify your payment
2. Account will be delivered after confirmation
3. You'll receive session details

**Processing Time:** 5-30 minutes

You'll be notified once the payment is verified.
                """,
                [[Button.inline("🔙 Main Menu", "back_to_main")]]
            )
            
        except Exception as e:
            logger.error(f"Payment sent handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_cancel_payment(self, event, user, transaction_id):
        """Handle payment cancellation"""
        try:
            await self.db_connection.transactions.update_one(
                {"_id": transaction_id},
                {"$set": {"status": "cancelled", "updated_at": utc_now()}}
            )
            
            await self.edit_message(
                event,
                "❌ **Payment Cancelled**\n\nYour payment has been cancelled.",
                [[Button.inline("🛒 Browse Accounts", "browse_accounts")], 
                 [Button.inline("🔙 Main Menu", "back_to_main")]]
            )
            
        except Exception as e:
            logger.error(f"Cancel payment handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_discount_code(self, event, user, listing_id):
        """Handle discount code application"""
        try:
            await self.edit_message(
                event,
                "🎫 **Discount Code**\n\nEnter your discount code:",
                [[Button.inline("❌ Cancel", f"listing_{listing_id}")]]
            )
            
            # Set user state for discount code input
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"state": f"awaiting_discount_{listing_id}"}}
            )
            
        except Exception as e:
            logger.error(f"Discount code handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def process_discount_code(self, event, user, listing_id, discount_code):
        """Process discount code input"""
        try:
            # Clear user state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"state": ""}}
            )
            
            # Validate discount code (simple validation)
            if not discount_code or len(discount_code) < 3:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Discount Code**\n\nPlease enter a valid discount code."
                )
                return
            
            # Check if discount code exists (placeholder logic)
            discount_codes = {"SAVE10": 10, "WELCOME": 5, "FIRST": 15}
            discount_percent = discount_codes.get(discount_code.upper(), 0)
            
            if discount_percent == 0:
                await self.send_message(
                    event.chat_id,
                    f"❌ **Invalid Discount Code**\n\nThe code '{discount_code}' is not valid or has expired.",
                    buttons=[[Button.inline("🔙 Back", f"listing_{listing_id}")]]
                )
                return
            
            # Get listing to calculate discount
            listing = await self.db_connection.listings.find_one({"_id": listing_id})
            if not listing:
                await self.send_message(
                    event.chat_id,
                    "❌ **Listing Not Found**\n\nThe account is no longer available."
                )
                return
            
            original_price = listing["price"]
            discount_amount = original_price * (discount_percent / 100)
            final_price = original_price - discount_amount
            
            await self.send_message(
                event.chat_id,
                f"""
✅ **Discount Applied Successfully!**

🎫 **Code:** {discount_code.upper()}
💰 **Original Price:** ${original_price:.2f}
💸 **Discount ({discount_percent}%):** -${discount_amount:.2f}
💵 **Final Price:** ${final_price:.2f}

Proceed with discounted purchase?
                """,
                buttons=[
                    [Button.inline("🛒 Buy Now", f"buy_{listing_id}")],
                    [Button.inline("🔙 Back", f"listing_{listing_id}")]
                ]
            )
            
        except Exception as e:
            logger.error(f"Process discount code error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to process discount code. Please try again.")
    
    async def handle_check_payment(self, event, user, order_id):
        """Handle check payment callback"""
        try:
            from app.services.UpiPaymentService import UpiPaymentService
            upi_service = UpiPaymentService(self.db_connection)
            
            # Check payment status
            status_result = await upi_service.check_payment_status(order_id)
            
            if status_result["status"] == "paid":
                # Payment confirmed - add credits and show success
                amount = status_result["amount"]
                txn_id = status_result["txn_id"]
                
                # Add credits to user balance (ensure balance field exists)
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user.telegram_user_id},
                    {
                        "$inc": {"balance": amount},
                        "$setOnInsert": {"balance": 0}
                    },
                    upsert=True
                )
                
                # Create success message
                success_message = upi_service.create_success_message(
                    order_id, 
                    user.first_name or "User", 
                    amount, 
                    txn_id
                )
                
                await self.edit_message(
                    event,
                    success_message,
                    [[Button.inline("💰 Check Balance", "my_balance")], 
                     [Button.inline("🔙 Main Menu", "back_to_main")]]
                )
                
            elif status_result["status"] == "pending":
                await self.edit_message(
                    event,
                    "⏳ **No payment found yet**\n\nTry again in a moment.",
                    [[Button.inline("🔄 Check Again", f"check:{order_id}")], 
                     [Button.inline("🔙 Back", "add_funds")]]
                )
                
            elif status_result["status"] == "expired":
                await self.edit_message(
                    event,
                    "⏰ **Order expired**\n\nPlease start a new deposit.",
                    [[Button.inline("💸 New Deposit", "add_funds")], 
                     [Button.inline("🔙 Main Menu", "back_to_main")]]
                )
            
        except Exception as e:
            logger.error(f"Check payment handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def process_upi_deposit_amount(self, event, user, amount_text):
        """Process UPI deposit with specific amount"""
        try:
            # Clear user state
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$unset": {"state": ""}}
            )
            
            # Check if UPI is configured before processing
            from app.services.PaymentSettingsService import PaymentSettingsService
            payment_settings_service = PaymentSettingsService(self.db_connection)
            
            if not await payment_settings_service.is_payment_method_enabled("upi"):
                await self.send_message(
                    event.chat_id,
                    "❌ **UPI Not Configured**\n\nUPI payments are not available. Please contact admin."
                )
                return
            
            from app.services.UpiPaymentService import UpiPaymentService
            upi_service = UpiPaymentService(self.db_connection)
            
            # Parse amount
            amount = upi_service.parse_amount(amount_text)
            if not amount:
                await self.send_message(
                    event.chat_id,
                    "❌ **Invalid Amount**\n\nPlease enter a valid amount between ₹1 and ₹100,000."
                )
                return
            
            # Create deposit order
            order_result = await upi_service.create_deposit_order(
                amount,
                user.telegram_user_id, 
                user.first_name or "User"
            )
            
            if "error" in order_result:
                await self.send_message(
                    event.chat_id,
                    f"❌ **Error**\n\n{order_result['message']}"
                )
                return
            
            # Save order to database
            await upi_service.save_order(order_result["db_document"])
            
            # Show payment interface with QR code
            await self.show_payment_interface(event.chat_id, order_result)
            
        except Exception as e:
            logger.error(f"Process UPI deposit amount error: {str(e)}")
            await self.send_message(event.chat_id, "❌ Failed to process deposit. Please try again.")
    
    async def handle_upi_quick_deposit(self, event, user):
        """Handle UPI quick deposit (any amount)"""
        try:
            # Check if UPI is configured before processing
            from app.services.PaymentSettingsService import PaymentSettingsService
            payment_settings_service = PaymentSettingsService(self.db_connection)
            
            if not await payment_settings_service.is_payment_method_enabled("upi"):
                await self.edit_message(
                    event,
                    "❌ **UPI Not Configured**\n\nUPI payments are not available. Please contact admin.",
                    [[Button.inline("🔙 Back", "add_funds")]]
                )
                return
            
            from app.services.UpiPaymentService import UpiPaymentService
            upi_service = UpiPaymentService(self.db_connection)
            
            # Create open amount deposit order
            order_result = await upi_service.create_deposit_order(
                "deposit", 
                user.telegram_user_id, 
                user.first_name or "User"
            )
            
            if "error" in order_result:
                await self.edit_message(
                    event,
                    f"❌ **Error**\n\n{order_result['message']}",
                    [[Button.inline("🔙 Back", "add_funds")]]
                )
                return
            
            # Save order to database
            await upi_service.save_order(order_result["db_document"])
            
            # Delete current message and show payment interface with QR code
            await self.client.delete_messages(event.chat_id, event.message_id)
            await self.show_payment_interface(event.chat_id, order_result)
            
        except Exception as e:
            logger.error(f"UPI quick deposit handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    
    async def handle_upi_fixed_amount(self, event, user):
        """Handle UPI fixed amount deposit"""
        try:
            # Check if UPI is configured before processing
            from app.services.PaymentSettingsService import PaymentSettingsService
            payment_settings_service = PaymentSettingsService(self.db_connection)
            
            if not await payment_settings_service.is_payment_method_enabled("upi"):
                await self.edit_message(
                    event,
                    "❌ **UPI Not Configured**\n\nUPI payments are not available. Please contact admin.",
                    [[Button.inline("🔙 Back", "add_funds")]]
                )
                return
            
            await self.edit_message(
                event,
                "💵 **Fixed Amount UPI Deposit**\n\nEnter the amount you want to deposit in rupees:\n\n**Examples:**\n• 100\n• 250.50\n• 1000\n\n**Minimum:** ₹1",
                [[Button.inline("❌ Cancel", "add_funds")]]
            )
            
            # Set user state for amount input
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"state": "awaiting_deposit_amount"}}
            )
            
        except Exception as e:
            logger.error(f"UPI fixed amount handler error: {str(e)}")
            await self.edit_message(event, "❌ An error occurred. Please try again.")
    async def show_payment_interface(self, chat_id, order_result):
        """Show payment interface with QR code"""
        try:
            import base64
            import io
            from PIL import Image
            
            # Decode QR code
            qr_data = base64.b64decode(order_result["upi_qr_b64"])
            
            # Create BytesIO object and ensure it's a proper image
            qr_image = io.BytesIO(qr_data)
            qr_image.name = "qr_code.png"
            qr_image.seek(0)
            
            # Send QR code as compressed photo
            await self.client.send_file(
                chat_id,
                qr_image,
                caption=order_result["receipt_message"] + f"\n\n**UPI Link:** `{order_result['upi_link']}`\n\n*Copy the link above and paste in any UPI app*",
                buttons=[
                    [Button.inline("📸 Submit Screenshot", f"upload_screenshot_{order_result['order_id']}")],
                    [Button.inline("❌ Cancel", "add_funds")]
                ],
                force_document=False
            )
            
        except Exception as e:
            logger.error(f"Show payment interface error: {str(e)}")
            # Fallback to text message
            await self.send_message(
                chat_id,
                order_result["receipt_message"] + f"\n\n**UPI Link:** `{order_result['upi_link']}`\n\n*Copy the link above and paste in any UPI app*",
                [
                    [Button.inline("📸 Submit Screenshot", f"upload_screenshot_{order_result['order_id']}")],
                    [Button.inline("❌ Cancel", "add_funds")]
                ]
            )
    
    async def process_notifications(self):
        """Process pending admin notifications"""
        while True:
            try:
                # Check for unprocessed notifications every 5 seconds
                notifications = await self.db_connection.admin_notifications.find({
                    "processed": False
                }).to_list(length=10)
                
                for notification in notifications:
                    try:
                        if notification["type"] == "balance_deposited":
                            await self.send_balance_notification(
                                notification["user_id"],
                                notification["amount"],
                                notification["new_balance"]
                            )
                        
                        # Mark as processed
                        await self.db_connection.admin_notifications.update_one(
                            {"_id": notification["_id"]},
                            {"$set": {"processed": True, "processed_at": utc_now()}}
                        )
                        
                    except Exception as e:
                        logger.error(f"Error processing notification {notification['_id']}: {str(e)}")
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in notification processing: {str(e)}")
                await asyncio.sleep(10)  # Wait longer on error
    
    async def send_balance_notification(self, user_id: int, amount: float, new_balance: float):
        """Send balance deposit notification to user"""
        try:
            message = f"🎉 You received ₹{amount:.2f} points!\n💳 Updated Balance: ₹{new_balance:.2f}"
            await self.send_message(user_id, message)
            logger.info(f"Sent balance notification to user {user_id}: ₹{amount}")
        except Exception as e:
            logger.error(f"Failed to send balance notification to user {user_id}: {str(e)}")
    
    async def show_payment_interface_edit(self, event, order_result):
        """Show payment interface with QR code (edit message)"""
        try:
            import base64
            import io
            
            # Decode QR code
            qr_data = base64.b64decode(order_result["upi_qr_b64"])
            
            # Delete current message and send new one with image
            await self.client.delete_messages(event.chat_id, event.message_id)
            
            await self.client.send_file(
                event.chat_id,
                io.BytesIO(qr_data),
                caption=order_result["receipt_message"] + f"\n\n**UPI Link:** `{order_result['upi_link']}`\n\n*Copy the link above and paste in any UPI app*",
                buttons=[
                    [Button.inline("📸 Submit Screenshot", f"upload_screenshot_{order_result['order_id']}")],
                    [Button.inline("❌ Cancel", "add_funds")]
                ],
                force_document=False
            )
            
        except Exception as e:
            logger.error(f"Show payment interface edit error: {str(e)}")
            # Fallback to edit message
            await self.edit_message(
                event,
                order_result["receipt_message"] + f"\n\n**UPI Link:** `{order_result['upi_link']}`\n\n*Copy the link above and paste in any UPI app*",
                [
                    [Button.inline("📸 Submit Screenshot", f"upload_screenshot_{order_result['order_id']}")],
                    [Button.inline("❌ Cancel", "add_funds")]
                ]
            )