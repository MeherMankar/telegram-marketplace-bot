"""Account preview service for buyers"""
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class AccountPreviewService:
    """Generate account previews for buyers"""
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    def mask_username(self, username: str) -> str:
        """Mask username for privacy"""
        if not username:
            return "No username"
        if len(username) <= 4:
            return "*" * len(username)
        return username[:2] + "*" * (len(username) - 4) + username[-2:]
    
    def mask_phone(self, phone: str) -> str:
        """Mask phone number"""
        if not phone:
            return "Hidden"
        if len(phone) <= 6:
            return "*" * len(phone)
        return phone[:3] + "*" * (len(phone) - 6) + phone[-3:]
    
    async def generate_preview(self, account_id) -> dict:
        """Generate account preview with limited info"""
        account = await self.db.accounts.find_one({"_id": account_id})
        if not account:
            return None
        
        # Get verification checks
        checks = account.get("checks", {})
        passed_checks = sum(1 for check in checks.values() if check.get("passed"))
        total_checks = len(checks)
        
        preview = {
            "username": self.mask_username(account.get("username")),
            "phone": self.mask_phone(account.get("phone_number")),
            "country": account.get("country", "Unknown"),
            "creation_year": account.get("creation_year", "Unknown"),
            "obtained_via": account.get("obtained_via", "upload"),
            "premium": account.get("premium", False),
            "verified": account.get("verified", False),
            "quality_score": round((passed_checks / total_checks * 100) if total_checks > 0 else 0, 1),
            "checks_passed": f"{passed_checks}/{total_checks}",
            "features": {
                "zero_contacts": checks.get("zero_contacts", {}).get("passed", False),
                "no_spam": checks.get("spam_status", {}).get("passed", False),
                "clean_groups": checks.get("group_count", {}).get("passed", False),
                "active": checks.get("last_seen", {}).get("passed", False)
            }
        }
        
        return preview
    
    async def generate_detailed_preview(self, account_id) -> dict:
        """Generate detailed preview after purchase intent"""
        preview = await self.generate_preview(account_id)
        if not preview:
            return None
        
        account = await self.db.accounts.find_one({"_id": account_id})
        
        # Add more details
        preview.update({
            "bio": account.get("bio", "")[:50] + "..." if account.get("bio") else "No bio",
            "profile_photo": bool(account.get("profile_photo")),
            "two_factor": bool(account.get("tfa_password")),
            "sessions_count": len(account.get("active_sessions", [])),
            "last_activity": account.get("last_seen", "Unknown")
        })
        
        return preview
