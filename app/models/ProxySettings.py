from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

class ProxySettings(BaseModel):
    """Proxy configuration model"""
    proxy_type: Literal["socks5", "socks4", "http", "mtproto"] = "socks5"
    proxy_host: str
    proxy_port: int
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    proxy_secret: Optional[str] = None  # For MTProto
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ProxyManager:
    """Manage proxy settings in database"""
    def __init__(self, db_connection):
        self.db = db_connection
        self.collection = self.db.proxy_settings
    
    async def get_proxy(self) -> Optional[ProxySettings]:
        """Get active proxy configuration"""
        doc = await self.collection.find_one({"enabled": True})
        return ProxySettings(**doc) if doc else None
    
    async def set_proxy(self, proxy: ProxySettings) -> bool:
        """Set proxy configuration"""
        await self.collection.delete_many({})
        await self.collection.insert_one(proxy.dict())
        return True
    
    async def disable_proxy(self) -> bool:
        """Disable proxy"""
        await self.collection.update_many({}, {"$set": {"enabled": False}})
        return True
    
    async def get_proxy_dict(self) -> Optional[dict]:
        """Get proxy as Telethon-compatible dict"""
        proxy = await self.get_proxy()
        if not proxy or not proxy.enabled:
            return None
        
        if proxy.proxy_type == "mtproto":
            return {
                "proxy_type": "mtproto",
                "addr": proxy.proxy_host,
                "port": proxy.proxy_port,
                "secret": proxy.proxy_secret
            }
        
        return {
            "proxy_type": proxy.proxy_type,
            "addr": proxy.proxy_host,
            "port": proxy.proxy_port,
            "username": proxy.proxy_username,
            "password": proxy.proxy_password,
            "rdns": True
        }
