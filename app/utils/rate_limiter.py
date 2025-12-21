"""Rate limiting utility for preventing abuse"""
import time
from collections import defaultdict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self.requests = defaultdict(list)
        self.blocked_users = {}
    
    def is_allowed(self, user_id: int, action: str, max_requests: int = 10, window_seconds: int = 60) -> tuple[bool, str]:
        """
        Check if user is allowed to perform action
        Returns: (allowed: bool, message: str)
        """
        # Check if user is blocked
        if user_id in self.blocked_users:
            block_until = self.blocked_users[user_id]
            if datetime.utcnow() < block_until:
                remaining = (block_until - datetime.utcnow()).seconds
                return False, f"Too many requests. Try again in {remaining} seconds."
            else:
                del self.blocked_users[user_id]
        
        key = f"{user_id}:{action}"
        now = time.time()
        
        # Clean old requests
        self.requests[key] = [req_time for req_time in self.requests[key] if now - req_time < window_seconds]
        
        # Check limit
        if len(self.requests[key]) >= max_requests:
            # Block user for 5 minutes
            self.blocked_users[user_id] = datetime.utcnow() + timedelta(minutes=5)
            logger.warning(f"User {user_id} rate limited for action {action}")
            return False, f"Rate limit exceeded. Blocked for 5 minutes."
        
        # Add request
        self.requests[key].append(now)
        return True, ""
    
    def reset_user(self, user_id: int):
        """Reset rate limit for user"""
        keys_to_delete = [key for key in self.requests.keys() if key.startswith(f"{user_id}:")]
        for key in keys_to_delete:
            del self.requests[key]
        if user_id in self.blocked_users:
            del self.blocked_users[user_id]

# Global rate limiter instance
rate_limiter = RateLimiter()
