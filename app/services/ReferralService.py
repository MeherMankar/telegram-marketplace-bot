"""Referral system service"""
from datetime import datetime
import secrets
import logging

logger = logging.getLogger(__name__)

class ReferralService:
    """Manage referral system"""
    
    def __init__(self, db_connection):
        self.db = db_connection
        self.referrer_bonus = 10.0  # Bonus for referrer
        self.referee_bonus = 5.0    # Bonus for new user
    
    async def generate_referral_code(self, user_id: int) -> str:
        """Generate unique referral code for user"""
        # Check if user already has code
        user = await self.db.users.find_one({"telegram_user_id": user_id})
        if user and user.get("referral_code"):
            return user["referral_code"]
        
        # Generate new code
        code = secrets.token_urlsafe(6).upper()
        
        # Ensure uniqueness
        while await self.db.users.find_one({"referral_code": code}):
            code = secrets.token_urlsafe(6).upper()
        
        # Save code
        await self.db.users.update_one(
            {"telegram_user_id": user_id},
            {"$set": {"referral_code": code}}
        )
        
        return code
    
    async def apply_referral(self, new_user_id: int, referral_code: str) -> dict:
        """Apply referral code for new user"""
        # Find referrer
        referrer = await self.db.users.find_one({"referral_code": referral_code})
        if not referrer:
            return {"success": False, "error": "Invalid referral code"}
        
        # Check if user already used a referral
        new_user = await self.db.users.find_one({"telegram_user_id": new_user_id})
        if new_user and new_user.get("referred_by"):
            return {"success": False, "error": "You already used a referral code"}
        
        # Can't refer yourself
        if referrer["telegram_user_id"] == new_user_id:
            return {"success": False, "error": "Cannot use your own referral code"}
        
        # Apply referral
        await self.db.users.update_one(
            {"telegram_user_id": new_user_id},
            {
                "$set": {
                    "referred_by": referrer["telegram_user_id"],
                    "referral_applied_at": datetime.utcnow()
                },
                "$inc": {"balance": self.referee_bonus}
            }
        )
        
        # Give bonus to referrer
        await self.db.users.update_one(
            {"telegram_user_id": referrer["telegram_user_id"]},
            {
                "$inc": {
                    "balance": self.referrer_bonus,
                    "total_referrals": 1
                }
            }
        )
        
        # Log referral
        await self.db.referrals.insert_one({
            "referrer_id": referrer["telegram_user_id"],
            "referee_id": new_user_id,
            "referrer_bonus": self.referrer_bonus,
            "referee_bonus": self.referee_bonus,
            "created_at": datetime.utcnow()
        })
        
        logger.info(f"Referral applied: {referrer['telegram_user_id']} -> {new_user_id}")
        
        return {
            "success": True,
            "referrer_bonus": self.referrer_bonus,
            "referee_bonus": self.referee_bonus
        }
    
    async def get_referral_stats(self, user_id: int) -> dict:
        """Get referral statistics for user"""
        referrals = await self.db.referrals.find(
            {"referrer_id": user_id}
        ).to_list(length=None)
        
        total_referrals = len(referrals)
        total_earned = sum(r.get("referrer_bonus", 0) for r in referrals)
        
        return {
            "total_referrals": total_referrals,
            "total_earned": total_earned,
            "referrals": referrals
        }
