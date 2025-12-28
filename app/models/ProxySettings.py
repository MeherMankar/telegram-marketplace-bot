from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Tuple
from datetime import datetime
import logging
import re
import html
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

class ProxySettings(BaseModel):
    """Proxy configuration model"""
    proxy_type: Literal["socks5", "socks4", "http", "mtproto"] = "socks5"
    proxy_host: str
    proxy_port: int
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    proxy_secret: Optional[str] = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ProxyManager:
    """Manage proxy settings in database"""
    def __init__(self, db_connection):
        self.db = db_connection
        self.collection = self.db.proxy_settings
        self.proxies_collection = self.db.proxies
    
    async def parse_telegram_proxy_link(self, link: str) -> Optional[Dict]:
        """Parse Telegram proxy link (t.me/proxy, t.me/socks, tg://)"""
        try:
            link = html.unescape(link.strip())
            link = re.sub(r'^https?://', '', link)
            
            if 't.me/proxy' in link or 't.me/socks' in link:
                if '?' not in link:
                    return None
                params = {}
                for param in link.split('?')[1].split('&'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        params[key] = value
                
                proxy_type = 'socks5' if 'socks' in link else 'mtproto'
                if proxy_type == 'mtproto':
                    return {'type': 'mtproto', 'server': params.get('server'), 'port': int(params.get('port', 443)), 'secret': params.get('secret')}
                return {'type': 'socks5', 'server': params.get('server'), 'port': int(params.get('port', 1080)), 'username': params.get('user'), 'password': params.get('pass')}
            
            elif link.startswith('tg://'):
                parsed = urlparse(link)
                params = parse_qs(parsed.query)
                proxy_type = 'socks5' if 'socks' in link else 'mtproto'
                
                if proxy_type == 'mtproto':
                    return {'type': 'mtproto', 'server': params.get('server', [''])[0], 'port': int(params.get('port', [443])[0]), 'secret': params.get('secret', [''])[0]}
                return {'type': 'socks5', 'server': params.get('server', [''])[0], 'port': int(params.get('port', [1080])[0]), 'username': params.get('user', [''])[0], 'password': params.get('pass', [''])[0]}
            
            elif '://' in link:
                parsed = urlparse(link)
                return {'type': parsed.scheme, 'server': parsed.hostname, 'port': parsed.port or 1080, 'username': parsed.username, 'password': parsed.password}
            
            return None
        except Exception as e:
            logger.error(f"Parse proxy error: {e}")
            return None
    
    async def add_user_proxy(self, user_id: int, proxy_data: Dict, name: str = None) -> Tuple[bool, str]:
        """Add proxy for user"""
        try:
            if not proxy_data.get('server') or not proxy_data.get('port'):
                return False, "Invalid proxy data"
            
            doc = {
                'user_id': user_id,
                'name': name or f"{proxy_data['server']}:{proxy_data['port']}",
                'type': proxy_data.get('type', 'socks5'),
                'server': proxy_data['server'],
                'port': proxy_data['port'],
                'username': proxy_data.get('username'),
                'password': proxy_data.get('password'),
                'secret': proxy_data.get('secret'),
                'status': 'active',
                'created_at': datetime.utcnow()
            }
            
            result = await self.proxies_collection.insert_one(doc)
            return True, str(result.inserted_id)
        except Exception as e:
            logger.error(f"Add proxy error: {e}")
            return False, str(e)
    
    async def get_user_proxies(self, user_id: int):
        """Get all proxies for user"""
        return await self.proxies_collection.find({'user_id': user_id}).to_list(length=None)
    
    async def delete_user_proxy(self, user_id: int, proxy_id: str) -> bool:
        """Delete user proxy"""
        from bson import ObjectId
        result = await self.proxies_collection.delete_one({'_id': ObjectId(proxy_id), 'user_id': user_id})
        return result.deleted_count > 0
    
    async def build_telethon_proxy(self, proxy: Dict) -> Optional[Dict]:
        """Build Telethon proxy dict"""
        if not proxy:
            return None
        
        if proxy['type'] == 'mtproto':
            return {'proxy_type': 'mtproto', 'addr': proxy['server'], 'port': proxy['port'], 'secret': proxy.get('secret', '')}
        
        return {'proxy_type': proxy['type'], 'addr': proxy['server'], 'port': proxy['port'], 'username': proxy.get('username'), 'password': proxy.get('password'), 'rdns': True}
    
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
            return {"proxy_type": "mtproto", "addr": proxy.proxy_host, "port": proxy.proxy_port, "secret": proxy.proxy_secret}
        
        return {"proxy_type": proxy.proxy_type, "addr": proxy.proxy_host, "port": proxy.proxy_port, "username": proxy.proxy_username, "password": proxy.proxy_password, "rdns": True}
