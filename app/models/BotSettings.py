from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass
from app.utils.datetime_utils import utc_now

@dataclass
class BotSettings:
    """Bot settings model for admin-managed configuration"""
    
    # Seller Bot Settings
    SELLER_UPLOAD_LIMITS = {
        "enabled": False,
        "max_per_day": 999,
        "max_file_size_mb": 50,
        "allowed_formats": ["session", "json", "tdata", "string"]
    }
    
    SELLER_VERIFICATION_SETTINGS = {
        "max_contacts": 5,
        "max_bot_chats": 3,
        "max_active_sessions": 3,
        "max_groups_owned": 10,
        "require_spam_check": True,
        "require_zero_contacts": False,
        "auto_approve_threshold": 0.8,
        "manual_review_required": True
    }
    
    SELLER_PAYOUT_SETTINGS = {
        "min_payout_amount": 10.0,
        "payout_methods": ["upi", "crypto", "bank"],
        "auto_payout_enabled": False,
        "payout_fee_percentage": 2.0
    }
    
    # Buyer Bot Settings
    BUYER_PURCHASE_SETTINGS = {
        "payment_methods": ["upi", "crypto", "otp"],
        "payment_timeout_minutes": 15,
        "auto_delivery_enabled": True,
        "require_payment_proof": True
    }
    
    BUYER_BROWSING_SETTINGS = {
        "max_listings_per_page": 10,
        "show_seller_info": False,
        "allow_direct_phone_purchase": True,
        "require_account_verification": True
    }
    
    # General Bot Settings
    GENERAL_SETTINGS = {
        "maintenance_mode": False,
        "welcome_message_enabled": True,
        "tos_acceptance_required": True,
        "rate_limiting_enabled": True,
        "logging_level": "INFO"
    }
    
    SECURITY_SETTINGS = {
        "session_encryption_enabled": True,
        "otp_destroyer_auto_enable": True,
        "admin_approval_required": True,
        "suspicious_activity_detection": True,
        "max_login_attempts": 3
    }
    
    PAYMENT_SETTINGS = {
        "upi_enabled": True,
        "crypto_enabled": True,
        "otp_payment_enabled": True,
        "simulate_payments": True,
        "payment_confirmation_required": True
    }

class SettingsManager:
    """Manages bot settings from database"""
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def get_setting(self, setting_type: str, key: str = None) -> Any:
        """Get a specific setting value"""
        try:
            settings_doc = await self.db.admin_settings.find_one({"type": setting_type})
            
            if not settings_doc:
                # Return default values
                defaults = getattr(BotSettings, setting_type.upper(), {})
                return defaults.get(key) if key else defaults
            
            settings = settings_doc.get("settings", {})
            return settings.get(key) if key else settings
            
        except Exception as e:
            # Return default on error
            defaults = getattr(BotSettings, setting_type.upper(), {})
            return defaults.get(key) if key else defaults
    
    async def update_setting(self, setting_type: str, key: str, value: Any, admin_id: int) -> bool:
        """Update a specific setting"""
        try:
            # Get current settings
            current_settings = await self.get_setting(setting_type)
            current_settings[key] = value
            
            # Update in database
            await self.db.admin_settings.update_one(
                {"type": setting_type},
                {
                    "$set": {
                        "settings": current_settings,
                        "updated_at": utc_now(),
                        "updated_by": admin_id
                    }
                },
                upsert=True
            )
            
            return True
            
        except Exception as e:
            return False
    
    async def get_all_settings(self) -> Dict[str, Any]:
        """Get all bot settings"""
        try:
            settings = {}
            
            # Get all setting types
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
            
            for setting_type in setting_types:
                settings[setting_type] = await self.get_setting(setting_type)
            
            return settings
            
        except Exception as e:
            return {}
    
    async def reset_to_defaults(self, setting_type: str, admin_id: int) -> bool:
        """Reset settings to default values"""
        try:
            defaults = getattr(BotSettings, setting_type.upper(), {})
            
            await self.db.admin_settings.update_one(
                {"type": setting_type},
                {
                    "$set": {
                        "settings": defaults,
                        "updated_at": utc_now(),
                        "updated_by": admin_id,
                        "reset_to_defaults": True
                    }
                },
                upsert=True
            )
            
            return True
            
        except Exception as e:
            return False
    
    async def get_verification_limits(self) -> Dict[str, Any]:
        """Get verification limits from settings"""
        return await self.get_setting("seller_verification_settings")