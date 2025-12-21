from datetime import datetime
import logging
from typing import Dict, Any, Optional
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class PaymentSettingsService:
    """Service for managing all payment-related settings"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
    
    async def get_upi_settings(self) -> Dict[str, Any]:
        """Get UPI payment settings"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "upi_settings"})
            if settings:
                return settings.get("settings", {})
            
            # Default UPI settings
            return {
                "merchant_vpa": "merchant@paytm",
                "merchant_name": "TelegramMarketplace",
                "enabled": True
            }
        except Exception as e:
            logger.error(f"Failed to get UPI settings: {str(e)}")
            return {}
    
    async def get_razorpay_settings(self) -> Dict[str, Any]:
        """Get Razorpay payment settings"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "razorpay_settings"})
            if settings:
                return settings.get("settings", {})
            
            # Default Razorpay settings
            return {
                "key_id": "",
                "key_secret": "",
                "webhook_secret": "",
                "enabled": False,
                "test_mode": True
            }
        except Exception as e:
            logger.error(f"Failed to get Razorpay settings: {str(e)}")
            return {}
    
    async def get_crypto_settings(self) -> Dict[str, Any]:
        """Get cryptocurrency payment settings"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "crypto_settings"})
            if settings:
                return settings.get("settings", {})
            
            # Default crypto settings
            return {
                "bitcoin_enabled": True,
                "usdt_enabled": True,
                "wallet_address": "",
                "api_key": "",
                "enabled": False,
                "confirmation_blocks": 3
            }
        except Exception as e:
            logger.error(f"Failed to get crypto settings: {str(e)}")
            return {}
    
    async def get_payment_settings(self) -> Dict[str, Any]:
        """Get general payment settings"""
        try:
            settings = await self.db_connection.admin_settings.find_one({"type": "payment_settings"})
            if settings:
                return settings.get("settings", {})
            
            # Default payment settings
            return {
                "upi_enabled": True,
                "razorpay_enabled": True,
                "crypto_enabled": True,
                "simulate_payments": True,
                "payment_confirmation_required": True,
                "payment_timeout_minutes": 15,
                "auto_refund_enabled": True
            }
        except Exception as e:
            logger.error(f"Failed to get payment settings: {str(e)}")
            return {}
    
    async def update_upi_settings(self, settings: Dict[str, Any], updated_by: int) -> bool:
        """Update UPI settings"""
        try:
            await self.db_connection.admin_settings.update_one(
                {"type": "upi_settings"},
                {
                    "$set": {
                        "settings": settings,
                        "updated_at": utc_now(),
                        "updated_by": updated_by
                    }
                },
                upsert=True
            )
            logger.info(f"UPI settings updated by admin {updated_by}")
            return True
        except Exception as e:
            logger.error(f"Failed to update UPI settings: {str(e)}")
            return False
    
    async def update_razorpay_settings(self, settings: Dict[str, Any], updated_by: int) -> bool:
        """Update Razorpay settings"""
        try:
            await self.db_connection.admin_settings.update_one(
                {"type": "razorpay_settings"},
                {
                    "$set": {
                        "settings": settings,
                        "updated_at": utc_now(),
                        "updated_by": updated_by
                    }
                },
                upsert=True
            )
            logger.info(f"Razorpay settings updated by admin {updated_by}")
            return True
        except Exception as e:
            logger.error(f"Failed to update Razorpay settings: {str(e)}")
            return False
    
    async def update_crypto_settings(self, settings: Dict[str, Any], updated_by: int) -> bool:
        """Update crypto settings"""
        try:
            await self.db_connection.admin_settings.update_one(
                {"type": "crypto_settings"},
                {
                    "$set": {
                        "settings": settings,
                        "updated_at": utc_now(),
                        "updated_by": updated_by
                    }
                },
                upsert=True
            )
            logger.info(f"Crypto settings updated by admin {updated_by}")
            return True
        except Exception as e:
            logger.error(f"Failed to update crypto settings: {str(e)}")
            return False
    
    async def update_payment_settings(self, settings: Dict[str, Any], updated_by: int) -> bool:
        """Update general payment settings"""
        try:
            await self.db_connection.admin_settings.update_one(
                {"type": "payment_settings"},
                {
                    "$set": {
                        "settings": settings,
                        "updated_at": utc_now(),
                        "updated_by": updated_by
                    }
                },
                upsert=True
            )
            logger.info(f"Payment settings updated by admin {updated_by}")
            return True
        except Exception as e:
            logger.error(f"Failed to update payment settings: {str(e)}")
            return False
    
    async def is_payment_method_enabled(self, method: str) -> bool:
        """Check if a payment method is enabled"""
        try:
            payment_settings = await self.get_payment_settings()
            
            if method == "upi":
                upi_settings = await self.get_upi_settings()
                return (payment_settings.get("upi_enabled", True) and 
                       upi_settings.get("enabled", True) and
                       upi_settings.get("merchant_vpa"))
            
            elif method == "razorpay":
                razorpay_settings = await self.get_razorpay_settings()
                return (payment_settings.get("razorpay_enabled", True) and 
                       razorpay_settings.get("enabled", False) and
                       razorpay_settings.get("key_id") and
                       razorpay_settings.get("key_secret"))
            
            elif method == "crypto":
                crypto_settings = await self.get_crypto_settings()
                return (payment_settings.get("crypto_enabled", True) and 
                       crypto_settings.get("enabled", False) and
                       crypto_settings.get("wallet_address"))
            
            return False
        except Exception as e:
            logger.error(f"Failed to check payment method {method}: {str(e)}")
            return False
    
    async def get_available_payment_methods(self) -> list:
        """Get list of available payment methods"""
        try:
            methods = []
            
            # Always include UPI if enabled (default enabled)
            if await self.is_payment_method_enabled("upi"):
                methods.append({
                    "id": "upi",
                    "name": "UPI Payment",
                    "icon": "💳",
                    "description": "Pay using UPI ID"
                })
            
            # Include Razorpay only if properly configured
            if await self.is_payment_method_enabled("razorpay"):
                methods.append({
                    "id": "razorpay",
                    "name": "Razorpay Gateway",
                    "icon": "🔐",
                    "description": "Cards, UPI, Wallets"
                })
            
            # Include crypto only if properly configured
            if await self.is_payment_method_enabled("crypto"):
                methods.append({
                    "id": "crypto",
                    "name": "Cryptocurrency",
                    "icon": "₿",
                    "description": "Bitcoin, USDT"
                })
            
            # Ensure at least one method is available
            if not methods:
                # Fallback to UPI with default settings
                methods.append({
                    "id": "upi",
                    "name": "UPI Payment",
                    "icon": "💳",
                    "description": "Pay using UPI ID"
                })
            
            return methods
        except Exception as e:
            logger.error(f"Failed to get available payment methods: {str(e)}")
            # Return UPI as fallback
            return [{
                "id": "upi",
                "name": "UPI Payment",
                "icon": "💳",
                "description": "Pay using UPI ID"
            }]
    
    async def validate_razorpay_config(self) -> Dict[str, Any]:
        """Validate Razorpay configuration"""
        try:
            settings = await self.get_razorpay_settings()
            
            validation = {
                "valid": True,
                "errors": []
            }
            
            if not settings.get("key_id"):
                validation["valid"] = False
                validation["errors"].append("Key ID is required")
            elif not settings["key_id"].startswith("rzp_"):
                validation["valid"] = False
                validation["errors"].append("Invalid Key ID format")
            
            if not settings.get("key_secret"):
                validation["valid"] = False
                validation["errors"].append("Key Secret is required")
            
            if not settings.get("webhook_secret"):
                validation["valid"] = False
                validation["errors"].append("Webhook Secret is required")
            elif not settings["webhook_secret"].startswith("whsec_"):
                validation["valid"] = False
                validation["errors"].append("Invalid Webhook Secret format")
            
            return validation
        except Exception as e:
            logger.error(f"Failed to validate Razorpay config: {str(e)}")
            return {"valid": False, "errors": ["Configuration validation failed"]}
    
    async def validate_crypto_config(self) -> Dict[str, Any]:
        """Validate cryptocurrency configuration"""
        try:
            settings = await self.get_crypto_settings()
            
            validation = {
                "valid": True,
                "errors": []
            }
            
            if not settings.get("wallet_address"):
                validation["valid"] = False
                validation["errors"].append("Wallet address is required")
            elif len(settings["wallet_address"]) < 20:
                validation["valid"] = False
                validation["errors"].append("Invalid wallet address format")
            
            if not settings.get("api_key"):
                validation["valid"] = False
                validation["errors"].append("API key is required for transaction verification")
            
            confirmation_blocks = settings.get("confirmation_blocks", 3)
            if not isinstance(confirmation_blocks, int) or confirmation_blocks < 1:
                validation["valid"] = False
                validation["errors"].append("Invalid confirmation blocks setting")
            
            return validation
        except Exception as e:
            logger.error(f"Failed to validate crypto config: {str(e)}")
            return {"valid": False, "errors": ["Configuration validation failed"]}
    
    async def get_payment_timeout(self) -> int:
        """Get payment timeout in minutes"""
        try:
            settings = await self.get_payment_settings()
            return settings.get("payment_timeout_minutes", 15)
        except Exception as e:
            logger.error(f"Failed to get payment timeout: {str(e)}")
            return 15
    
    async def requires_admin_confirmation(self) -> bool:
        """Check if payments require admin confirmation"""
        try:
            settings = await self.get_payment_settings()
            return settings.get("payment_confirmation_required", True)
        except Exception as e:
            logger.error(f"Failed to check admin confirmation requirement: {str(e)}")
            return True
    
    async def is_simulation_enabled(self) -> bool:
        """Check if payment simulation is enabled"""
        try:
            settings = await self.get_payment_settings()
            return settings.get("simulate_payments", True)
        except Exception as e:
            logger.error(f"Failed to check simulation status: {str(e)}")
            return True