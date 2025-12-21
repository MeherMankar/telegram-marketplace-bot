from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

class SellerProxy(BaseModel):
    """Seller's proxy configuration"""
    seller_id: int
    proxy_type: Literal["socks5", "socks4", "http"] = "socks5"
    proxy_host: str
    proxy_port: int
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    accounts_count: int = 0  # Number of accounts using this proxy
    max_accounts: int = 10  # Max accounts per proxy
    created_at: datetime = Field(default_factory=datetime.utcnow)

class SellerProxyManager:
    """Manage seller proxies"""
    def __init__(self, db_connection):
        self.db = db_connection
        self.collection = self.db.seller_proxies
    
    async def add_proxy(self, seller_id: int, proxy: SellerProxy) -> bool:
        """Add proxy for seller"""
        await self.collection.insert_one(proxy.dict())
        return True
    
    async def get_available_proxy(self, seller_id: int) -> Optional[SellerProxy]:
        """Get available proxy for seller (not at max capacity)"""
        doc = await self.collection.find_one({
            "seller_id": seller_id,
            "accounts_count": {"$lt": 10}
        })
        return SellerProxy(**doc) if doc else None
    
    async def increment_proxy_usage(self, seller_id: int, proxy_host: str) -> bool:
        """Increment account count for proxy"""
        result = await self.collection.update_one(
            {"seller_id": seller_id, "proxy_host": proxy_host},
            {"$inc": {"accounts_count": 1}}
        )
        return result.modified_count > 0
    
    async def get_seller_proxies(self, seller_id: int) -> list:
        """Get all proxies for seller"""
        cursor = self.collection.find({"seller_id": seller_id})
        return [SellerProxy(**doc) async for doc in cursor]
    
    async def needs_new_proxy(self, seller_id: int) -> bool:
        """Check if seller needs to add new proxy"""
        available = await self.get_available_proxy(seller_id)
        return available is None
    
    async def get_proxy_dict(self, seller_id: int) -> Optional[dict]:
        """Get Telethon-compatible proxy dict"""
        proxy = await self.get_available_proxy(seller_id)
        if not proxy:
            return None
        
        return {
            "proxy_type": proxy.proxy_type,
            "addr": proxy.proxy_host,
            "port": proxy.proxy_port,
            "username": proxy.proxy_username,
            "password": proxy.proxy_password,
            "rdns": True
        }
