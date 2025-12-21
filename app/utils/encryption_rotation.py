"""Session encryption key rotation utility"""
import os
from cryptography.fernet import Fernet
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class EncryptionKeyManager:
    """Manage encryption key rotation"""
    
    def __init__(self, db_connection):
        self.db = db_connection
        self.current_key = os.getenv('SESSION_ENCRYPTION_KEY', Fernet.generate_key().decode())
    
    async def should_rotate(self) -> bool:
        """Check if key should be rotated (every 90 days)"""
        key_doc = await self.db.encryption_keys.find_one({"current": True})
        if not key_doc:
            return True
        
        created_at = key_doc.get("created_at")
        if not created_at:
            return True
        
        age = datetime.utcnow() - created_at
        return age > timedelta(days=90)
    
    async def rotate_key(self) -> str:
        """Generate new key and mark old as archived"""
        new_key = Fernet.generate_key().decode()
        
        # Archive current key
        await self.db.encryption_keys.update_many(
            {"current": True},
            {"$set": {"current": False, "archived_at": datetime.utcnow()}}
        )
        
        # Save new key
        await self.db.encryption_keys.insert_one({
            "key": new_key,
            "current": True,
            "created_at": datetime.utcnow()
        })
        
        logger.info("Encryption key rotated successfully")
        return new_key
    
    async def get_key_for_decryption(self, encrypted_at: datetime) -> str:
        """Get appropriate key for decrypting old data"""
        key_doc = await self.db.encryption_keys.find_one({
            "created_at": {"$lte": encrypted_at}
        }, sort=[("created_at", -1)])
        
        return key_doc["key"] if key_doc else self.current_key
