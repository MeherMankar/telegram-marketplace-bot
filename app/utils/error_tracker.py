"""Error tracking and monitoring utility"""
import logging
import traceback
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

class ErrorTracker:
    """Track and log errors with context"""
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def log_error(self, error: Exception, context: dict, user_id: Optional[int] = None):
        """Log error with full context"""
        error_doc = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "context": context,
            "user_id": user_id,
            "timestamp": datetime.utcnow(),
            "resolved": False
        }
        
        try:
            await self.db.error_logs.insert_one(error_doc)
            logger.error(f"Error logged: {error_doc['error_type']} - {error_doc['error_message']}")
        except Exception as e:
            logger.critical(f"Failed to log error to database: {str(e)}")
    
    async def get_recent_errors(self, limit: int = 50):
        """Get recent unresolved errors"""
        return await self.db.error_logs.find(
            {"resolved": False}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
    
    async def mark_resolved(self, error_id):
        """Mark error as resolved"""
        await self.db.error_logs.update_one(
            {"_id": error_id},
            {"$set": {"resolved": True, "resolved_at": datetime.utcnow()}}
        )
