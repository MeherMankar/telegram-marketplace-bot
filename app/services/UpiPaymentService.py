import json
import random
import qrcode
import base64
import io
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import urllib.parse
import logging
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="razorpay")
import razorpay
import aiohttp
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class UpiPaymentService:
    """UPI Payment Order Microservice for Telegram Bot"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
        self.merchant_vpa = None
        self.merchant_name = None
        
        # Initialize Razorpay client (will be loaded from database)
        self.razorpay_client = None
        self.razorpay_key_id = None
        self.razorpay_key_secret = None
        self.razorpay_webhook_secret = None
    
    async def load_upi_settings(self):
        """Load UPI settings from database"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "upi_settings"})
            if settings:
                upi_config = settings.get("settings", {})
                self.merchant_vpa = upi_config.get("merchant_vpa")
                self.merchant_name = upi_config.get("merchant_name")
        except Exception as e:
            logger.error(f"Failed to load UPI settings: {str(e)}")
    
    async def load_razorpay_settings(self):
        """Load Razorpay settings from database"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "razorpay_settings"})
            if settings:
                razorpay_config = settings.get("settings", {})
                self.razorpay_key_id = razorpay_config.get("key_id")
                self.razorpay_key_secret = razorpay_config.get("key_secret")
                self.razorpay_webhook_secret = razorpay_config.get("webhook_secret")
                
                # Initialize Razorpay client if keys are available
                if self.razorpay_key_id and self.razorpay_key_secret:
                    self.razorpay_client = razorpay.Client(
                        auth=(self.razorpay_key_id, self.razorpay_key_secret)
                    )
        except Exception as e:
            logger.error(f"Failed to load Razorpay settings: {str(e)}")
    
    async def create_deposit_order(self, amount, user_id: int, user_display_name: str) -> Dict[str, Any]:
        """Create UPI deposit order with Razorpay"""
        try:
            # Convert amount to float if it's a string
            if isinstance(amount, str):
                if amount == "deposit":
                    # Handle special case for quick deposit
                    amount = 0.0  # Will be handled differently
                else:
                    try:
                        amount = float(amount.replace('₹', '').replace(',', '').strip())
                    except (ValueError, AttributeError):
                        return {
                            "error": "INVALID_AMOUNT",
                            "message": "Invalid amount format"
                        }
            
            # For quick deposit (open amount), create different flow
            if amount == 0.0 or isinstance(amount, str) and amount == "deposit":
                return await self._create_quick_deposit_order(user_id, user_display_name)
            
            # Validate amount
            if amount < 1.0:
                return {
                    "error": "INVALID_AMOUNT",
                    "message": "Amount must be >= ₹1.00"
                }
            
            # Generate order ID
            order_id = self._generate_order_id()
            
            # Load Razorpay settings
            await self.load_razorpay_settings()
            
            if not self.razorpay_client:
                return {
                    "error": "RAZORPAY_NOT_CONFIGURED",
                    "message": "Razorpay is not configured. Please contact admin."
                }
            
            # Create Razorpay order
            razorpay_order = self.razorpay_client.order.create({
                "amount": int(amount * 100),  # Amount in paise
                "currency": "INR",
                "receipt": order_id,
                "payment_capture": 1
            })
            
            # Create timestamps
            created_at = utc_now()
            expires_at = created_at + timedelta(minutes=15)
            
            # Load UPI settings
            await self.load_upi_settings()
            
            # Create UPI payment link
            merchant_vpa = self.merchant_vpa
            merchant_name = self.merchant_name
            
            if not merchant_vpa or not merchant_name:
                return {
                    "error": "UPI_NOT_CONFIGURED",
                    "message": "UPI is not configured. Please contact admin to set merchant details."
                }
            upi_link = f"upi://pay?pa={merchant_vpa}&pn={merchant_name}&tr={order_id}&am={amount:.2f}&cu=INR&tn=Account Deposit"
            
            # Generate QR code
            upi_qr_b64 = self._generate_qr_code(upi_link)
            if not upi_qr_b64:
                return {
                    "error": "INTERNAL_ERROR",
                    "message": "Could not generate QR code"
                }
            
            # Create DB document
            db_document = {
                "order_id": order_id,
                "razorpay_order_id": razorpay_order['id'],
                "user_id": user_id,
                "amount": amount,
                "currency": "INR",
                "status": "pending",
                "created_at": created_at.isoformat() + "Z",
                "expires_at": expires_at.isoformat() + "Z",
                "gateway": "razorpay_upi",
                "gateway_payload": razorpay_order
            }
            
            # Create receipt message
            receipt_message = self._create_receipt_message(order_id, user_display_name, amount)
            
            return {
                "order_id": order_id,
                "razorpay_order_id": razorpay_order['id'],
                "upi_link": upi_link,
                "upi_qr_b64": upi_qr_b64,
                "expires_at": expires_at.isoformat() + "Z",
                "receipt_message": receipt_message,
                "db_document": db_document
            }
            
        except Exception as e:
            logger.error(f"Failed to create deposit order: {str(e)}")
            return {
                "error": "INTERNAL_ERROR",
                "message": "Could not create order"
            }
    
    async def _create_quick_deposit_order(self, user_id: int, user_display_name: str) -> Dict[str, Any]:
        """Create quick deposit order (open amount)"""
        try:
            # Generate order ID
            order_id = self._generate_order_id()
            
            # Create timestamps
            created_at = utc_now()
            expires_at = created_at + timedelta(minutes=15)
            
            # Load UPI settings
            await self.load_upi_settings()
            
            # Create UPI payment link (without amount for open payment)
            merchant_vpa = self.merchant_vpa
            merchant_name = self.merchant_name
            
            if not merchant_vpa or not merchant_name:
                return {
                    "error": "UPI_NOT_CONFIGURED",
                    "message": "UPI is not configured. Please contact admin to set merchant details."
                }
            upi_link = f"upi://pay?pa={merchant_vpa}&pn={merchant_name}&tr={order_id}&cu=INR&tn=Account Deposit"
            
            # Generate QR code
            upi_qr_b64 = self._generate_qr_code(upi_link)
            if not upi_qr_b64:
                return {
                    "error": "INTERNAL_ERROR",
                    "message": "Could not generate QR code"
                }
            
            # Create DB document
            db_document = {
                "order_id": order_id,
                "user_id": user_id,
                "amount": 0.0,  # Open amount
                "currency": "INR",
                "status": "pending",
                "created_at": created_at.isoformat() + "Z",
                "expires_at": expires_at.isoformat() + "Z",
                "gateway": "upi_direct",
                "type": "quick_deposit"
            }
            
            # Create receipt message for quick deposit
            receipt_message = f"""💳 **UPI Quick Deposit**

**Order ID:** {order_id}
**User:** {user_display_name}
**Amount:** Any amount you want
**Expires:** 15 minutes

**Payment Instructions:**
1️⃣ Scan QR code with any UPI app
2️⃣ Enter any amount you want to deposit
3️⃣ Complete payment with your UPI PIN
4️⃣ Upload payment screenshot for verification

📸 **Manual verification required**
Upload screenshot after payment for admin verification.

🔒 **Secure Payment**
Powered by UPI - India's trusted payment system"""
            
            return {
                "order_id": order_id,
                "upi_link": upi_link,
                "upi_qr_b64": upi_qr_b64,
                "expires_at": expires_at.isoformat() + "Z",
                "receipt_message": receipt_message,
                "db_document": db_document,
                "inline_button": {
                    "text": "📸 Submit Screenshot",
                    "callback_data": f"upload_screenshot_{order_id}"
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to create quick deposit order: {str(e)}")
            return {
                "error": "INTERNAL_ERROR",
                "message": "Could not create order"
            }
    
    async def save_order(self, db_document: Dict[str, Any]) -> bool:
        """Save order to database"""
        try:
            await self.db_connection.upi_orders.insert_one(db_document)
            return True
        except Exception as e:
            logger.error(f"Failed to save order: {str(e)}")
            return False
    
    async def check_payment_status(self, order_id: str) -> Dict[str, Any]:
        """Check payment status with Razorpay API"""
        try:
            order = await self.db_connection.upi_orders.find_one({"order_id": order_id})
            if not order:
                return {"status": "not_found"}
            
            # Check if already processed
            if order["status"] == "success":
                return {
                    "status": "paid",
                    "amount": order["amount"],
                    "txn_id": order.get("payment_id", "N/A")
                }
            
            # Check if expired
            expires_at = datetime.fromisoformat(order["expires_at"].replace("Z", ""))
            if utc_now() > expires_at:
                await self.db_connection.upi_orders.update_one(
                    {"order_id": order_id},
                    {"$set": {"status": "expired"}}
                )
                return {"status": "expired"}
            
            # Check with Razorpay API
            if order["status"] == "pending":
                try:
                    razorpay_order_id = order.get("razorpay_order_id")
                    if razorpay_order_id:
                        # Get payments for this order
                        payments = self.razorpay_client.order.payments(razorpay_order_id)
                        
                        for payment in payments['items']:
                            if payment['status'] == 'captured':
                                # Payment successful
                                await self.db_connection.upi_orders.update_one(
                                    {"order_id": order_id},
                                    {
                                        "$set": {
                                            "status": "success",
                                            "payment_id": payment['id'],
                                            "verified_at": utc_now().isoformat() + "Z"
                                        }
                                    }
                                )
                                
                                return {
                                    "status": "paid",
                                    "amount": order["amount"],
                                    "txn_id": payment['id']
                                }
                except Exception as e:
                    logger.error(f"Razorpay API error: {str(e)}")
                
                return {"status": "pending"}
            
            return {"status": "pending"}
            
        except Exception as e:
            logger.error(f"Failed to check payment status: {str(e)}")
            return {"status": "error"}
    
    def create_success_message(self, order_id: str, user_display_name: str, amount: float, txn_id: str) -> str:
        """Create success message when payment is confirmed"""
        return f"""✅ **Payment Successful!**

**Amount:** ₹{amount:.2f}
**Transaction ID:** {txn_id}
**Order ID:** {order_id}
**Status:** Completed

💰 **₹{amount:.2f} credits added to your account**

Thank you for your payment! 🎉"""
    
    def parse_amount(self, amount_text: str) -> Optional[float]:
        """Parse and validate amount from text input"""
        try:
            # Remove currency symbols and whitespace
            clean_text = str(amount_text).strip().replace('₹', '').replace(',', '')
            amount = float(clean_text)
            
            if amount < 1.0:
                return None
            if amount > 100000:  # Max limit
                return None
                
            return round(amount, 2)
        except (ValueError, TypeError):
            return None
    
    def _generate_order_id(self) -> str:
        """Generate order ID in format ORD{YYYYMMDDHHMMSS}{8DIGITS_RANDOM}"""
        timestamp = utc_now().strftime("%Y%m%d%H%M%S")
        random_digits = f"{random.randint(10000000, 99999999)}"
        return f"ORD{timestamp}{random_digits}"
    
    async def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Verify Razorpay webhook signature"""
        try:
            await self.load_razorpay_settings()
            if not self.razorpay_webhook_secret:
                logger.error("Razorpay webhook secret not configured")
                return False
            return razorpay.utility.verify_webhook_signature(payload, signature, self.razorpay_webhook_secret)
        except Exception as e:
            logger.error(f"Webhook verification error: {str(e)}")
            return False
    
    async def handle_webhook(self, payload: dict) -> Dict[str, Any]:
        """Handle Razorpay webhook events"""
        try:
            event = payload.get('event')
            payment_data = payload.get('payload', {}).get('payment', {}).get('entity', {})
            
            if event == 'payment.captured':
                # Payment successful
                order_id = payment_data.get('notes', {}).get('order_id')
                if order_id:
                    await self.db_connection.upi_orders.update_one(
                        {"order_id": order_id},
                        {
                            "$set": {
                                "status": "success",
                                "payment_id": payment_data.get('id'),
                                "verified_at": utc_now().isoformat() + "Z"
                            }
                        }
                    )
                    return {"status": "success", "order_id": order_id}
            
            return {"status": "ignored"}
        except Exception as e:
            logger.error(f"Webhook handling error: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    async def approve_payment_with_amount(self, order_id: str, verified_amount: float) -> Dict[str, Any]:
        """Approve UPI payment with verified amount and add to user balance"""
        try:
            # Get the order
            order = await self.db_connection.upi_orders.find_one({"order_id": order_id})
            if not order:
                return {"error": "Order not found"}
            
            if order["status"] != "pending_verification":
                return {"error": "Order is not pending verification"}
            
            # Update order status
            await self.db_connection.upi_orders.update_one(
                {"order_id": order_id},
                {
                    "$set": {
                        "status": "success",
                        "verified_amount": verified_amount,
                        "verified_at": utc_now().isoformat() + "Z",
                        "admin_verified": True
                    }
                }
            )
            
            # Add balance to user account
            user_id = order["user_id"]
            
            # First ensure the user has a balance field
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": user_id})
            if not user_doc:
                # Create user if doesn't exist
                await self.db_connection.users.insert_one({
                    "telegram_user_id": user_id,
                    "balance": verified_amount,
                    "created_at": utc_now()
                })
                new_balance = verified_amount
            else:
                # Update existing user balance
                current_balance = user_doc.get("balance", 0)
                new_balance = current_balance + verified_amount
                await self.db_connection.users.update_one(
                    {"telegram_user_id": user_id},
                    {"$set": {"balance": new_balance}}
                )
            
            # Create transaction record
            transaction_data = {
                "user_id": user_id,
                "type": "deposit",
                "amount": verified_amount,
                "payment_method": "upi",
                "status": "confirmed",
                "order_id": order_id,
                "created_at": utc_now(),
                "verified_at": utc_now()
            }
            
            await self.db_connection.transactions.insert_one(transaction_data)
            
            # Create notification for user
            try:
                await self.db_connection.admin_notifications.insert_one({
                    "type": "balance_deposited",
                    "user_id": user_id,
                    "amount": verified_amount,
                    "new_balance": new_balance,
                    "order_id": order_id,
                    "created_at": utc_now(),
                    "processed": False
                })
                logger.info(f"Created balance notification for user {user_id}: ₹{verified_amount}")
            except Exception as e:
                logger.error(f"Failed to create notification record: {str(e)}")
            
            return {
                "success": True,
                "user_id": user_id,
                "amount": verified_amount,
                "order_id": order_id,
                "new_balance": new_balance
            }
            
        except Exception as e:
            logger.error(f"Error approving payment: {str(e)}")
            return {"error": "Failed to approve payment"}
    
    def _generate_qr_code(self, data: str) -> str:
        """Generate QR code as base64 PNG"""
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_str = base64.b64encode(buffer.getvalue()).decode()
            
            return img_str
            
        except Exception as e:
            logger.error(f"Failed to generate QR code: {str(e)}")
            return ""
    
    def _create_receipt_message(self, order_id: str, user_display_name: str, amount: float) -> str:
        """Create professional payment receipt message"""
        return f"""💳 **UPI Payment**

**Amount:** ₹{amount:.2f}
**Order ID:** {order_id}
**User:** {user_display_name}
**Expires:** 15 minutes

**Payment Instructions:**
1️⃣ Scan QR code with any UPI app
2️⃣ Amount is pre-filled (₹{amount:.2f})
3️⃣ Enter your UPI PIN to complete
4️⃣ Credits added automatically

⚡ **Auto-verification active**
Payment will be verified automatically within 30 seconds.

🔒 **Secure Payment Gateway**
Powered by Razorpay UPI"""