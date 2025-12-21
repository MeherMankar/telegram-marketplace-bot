"""Caching service for improved performance"""
import json
from datetime import datetime, timedelta
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)

class CacheService:
    """In-memory cache with TTL support"""
    
    def __init__(self):
        self.cache = {}
        self.ttl = {}
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Set cache value with TTL"""
        self.cache[key] = value
        self.ttl[key] = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        logger.debug(f"Cache set: {key} (TTL: {ttl_seconds}s)")
    
    def get(self, key: str) -> Optional[Any]:
        """Get cache value if not expired"""
        if key not in self.cache:
            return None
        
        # Check TTL
        if key in self.ttl and datetime.utcnow() > self.ttl[key]:
            self.delete(key)
            return None
        
        logger.debug(f"Cache hit: {key}")
        return self.cache[key]
    
    def delete(self, key: str):
        """Delete cache entry"""
        if key in self.cache:
            del self.cache[key]
        if key in self.ttl:
            del self.ttl[key]
        logger.debug(f"Cache deleted: {key}")
    
    def clear(self):
        """Clear all cache"""
        self.cache.clear()
        self.ttl.clear()
        logger.info("Cache cleared")
    
    def cleanup_expired(self):
        """Remove expired entries"""
        now = datetime.utcnow()
        expired_keys = [key for key, expiry in self.ttl.items() if now > expiry]
        for key in expired_keys:
            self.delete(key)
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")

# Global cache instance
cache_service = CacheService()
