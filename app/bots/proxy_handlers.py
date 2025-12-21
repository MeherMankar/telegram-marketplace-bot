"""Proxy management handlers for AdminBot"""
import logging
import os
from telethon import Button
from app.models import ProxyManager, ProxySettings

logger = logging.getLogger(__name__)

async def handle_proxy_settings(self, event):
    """Show proxy settings menu"""
    try:
        is_admin, user = await self.check_admin_access(event)
        if not is_admin:
            await self.answer_callback(event, "❌ Access denied", alert=True)
            return
        
        proxy_manager = ProxyManager(self.db_connection)
        proxy = await proxy_manager.get_proxy()
        
        if proxy and proxy.enabled:
            status = f"✅ **Proxy Enabled**\n\n"
            status += f"Type: {proxy.proxy_type.upper()}\n"
            status += f"Host: {proxy.proxy_host}\n"
            status += f"Port: {proxy.proxy_port}\n"
            if proxy.proxy_username:
                status += f"Username: {proxy.proxy_username}\n"
        else:
            status = "❌ **Proxy Disabled**\n\nNo proxy configured"
        
        buttons = [
            [Button.inline("➕ Add Proxy", "proxy_add")],
            [Button.inline("🔄 Test Proxy", "proxy_test")] if proxy else [],
            [Button.inline("❌ Disable Proxy", "proxy_disable")] if proxy and proxy.enabled else [],
            [Button.inline("🔙 Back", "security_settings")]
        ]
        buttons = [b for b in buttons if b]
        
        await self.edit_message(event, status, buttons)
        await self.answer_callback(event)
        
    except Exception as e:
        logger.error(f"Proxy settings error: {e}")
        await self.answer_callback(event, "❌ Error loading proxy settings", alert=True)

async def handle_proxy_add(self, event):
    """Start proxy addition flow"""
    try:
        is_admin, user = await self.check_admin_access(event)
        if not is_admin:
            await self.answer_callback(event, "❌ Access denied", alert=True)
            return
        
        message = """
🔧 **Add Proxy Configuration**

Send proxy details in format:
`type://host:port`
or
`type://username:password@host:port`

**Supported types:**
• `socks5` - SOCKS5 proxy (recommended)
• `socks4` - SOCKS4 proxy
• `http` - HTTP proxy
• `mtproto` - MTProto proxy (requires secret)

**Examples:**
`socks5://proxy.example.com:1080`
`socks5://user:pass@proxy.example.com:1080`
`mtproto://proxy.example.com:443?secret=abc123`

Send /cancel to abort.
        """
        
        await self.edit_message(event, message, [[Button.inline("🔙 Cancel", "proxy_settings")]])
        await self.answer_callback(event)
        
        # Set user state
        await self.db_connection.users.update_one(
            {"telegram_user_id": user.telegram_user_id},
            {"$set": {"state": "awaiting_proxy_config"}}
        )
        
    except Exception as e:
        logger.error(f"Proxy add error: {e}")
        await self.answer_callback(event, "❌ Error", alert=True)

async def handle_proxy_config_input(self, event, user):
    """Handle proxy configuration input"""
    try:
        text = event.text.strip()
        
        if text == "/cancel":
            await self.db_connection.users.update_one(
                {"telegram_user_id": user.telegram_user_id},
                {"$set": {"state": None}}
            )
            await self.send_message(event.chat_id, "❌ Cancelled", 
                                   [[Button.inline("🔙 Back", "proxy_settings")]])
            return
        
        # Parse proxy URL
        import re
        from urllib.parse import urlparse, parse_qs
        
        # Handle mtproto format
        if text.startswith("mtproto://"):
            parsed = urlparse(text)
            secret = parse_qs(parsed.query).get('secret', [None])[0]
            
            if not secret:
                await self.send_message(event.chat_id, "❌ MTProto proxy requires secret parameter")
                return
            
            proxy = ProxySettings(
                proxy_type="mtproto",
                proxy_host=parsed.hostname,
                proxy_port=parsed.port or 443,
                proxy_secret=secret,
                enabled=True
            )
        else:
            # Parse standard proxy format
            match = re.match(r'(socks5|socks4|http)://(?:([^:]+):([^@]+)@)?([^:]+):(\d+)', text)
            
            if not match:
                await self.send_message(event.chat_id, "❌ Invalid proxy format. Please try again.")
                return
            
            proxy_type, username, password, host, port = match.groups()
            
            proxy = ProxySettings(
                proxy_type=proxy_type,
                proxy_host=host,
                proxy_port=int(port),
                proxy_username=username,
                proxy_password=password,
                enabled=True
            )
        
        # Save proxy
        proxy_manager = ProxyManager(self.db_connection)
        await proxy_manager.set_proxy(proxy)
        
        # Clear state
        await self.db_connection.users.update_one(
            {"telegram_user_id": user.telegram_user_id},
            {"$set": {"state": None}}
        )
        
        await self.send_message(
            event.chat_id,
            f"✅ **Proxy configured successfully!**\n\n"
            f"Type: {proxy.proxy_type.upper()}\n"
            f"Host: {proxy.proxy_host}:{proxy.proxy_port}\n\n"
            f"⚠️ **Restart bots** to apply proxy settings.",
            [[Button.inline("🔙 Back", "proxy_settings")]]
        )
        
    except Exception as e:
        logger.error(f"Proxy config input error: {e}")
        await self.send_message(event.chat_id, f"❌ Error: {str(e)}")

async def handle_proxy_test(self, event):
    """Test proxy connection"""
    try:
        is_admin, user = await self.check_admin_access(event)
        if not is_admin:
            await self.answer_callback(event, "❌ Access denied", alert=True)
            return
        
        await self.answer_callback(event, "🔄 Testing proxy...")
        
        proxy_manager = ProxyManager(self.db_connection)
        proxy_dict = await proxy_manager.get_proxy_dict()
        
        if not proxy_dict:
            await self.edit_message(event, "❌ No proxy configured", 
                                   [[Button.inline("🔙 Back", "proxy_settings")]])
            return
        
        # Test connection
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        test_client = TelegramClient(
            StringSession(),
            int(os.getenv('API_ID')),
            os.getenv('API_HASH'),
            proxy=proxy_dict
        )
        
        try:
            await test_client.connect()
            await test_client.disconnect()
            
            await self.edit_message(
                event,
                f"✅ **Proxy test successful!**\n\n"
                f"Connection established through:\n"
                f"{proxy_dict['proxy_type']}://{proxy_dict['addr']}:{proxy_dict['port']}",
                [[Button.inline("🔙 Back", "proxy_settings")]]
            )
        except Exception as e:
            await self.edit_message(
                event,
                f"❌ **Proxy test failed!**\n\n"
                f"Error: {str(e)}\n\n"
                f"Please check your proxy configuration.",
                [[Button.inline("🔙 Back", "proxy_settings")]]
            )
        
    except Exception as e:
        logger.error(f"Proxy test error: {e}")
        await self.answer_callback(event, "❌ Test failed", alert=True)

async def handle_proxy_disable(self, event):
    """Disable proxy"""
    try:
        is_admin, user = await self.check_admin_access(event)
        if not is_admin:
            await self.answer_callback(event, "❌ Access denied", alert=True)
            return
        
        proxy_manager = ProxyManager(self.db_connection)
        await proxy_manager.disable_proxy()
        
        await self.edit_message(
            event,
            "✅ **Proxy disabled**\n\n⚠️ Restart bots to apply changes.",
            [[Button.inline("🔙 Back", "proxy_settings")]]
        )
        await self.answer_callback(event)
        
    except Exception as e:
        logger.error(f"Proxy disable error: {e}")
        await self.answer_callback(event, "❌ Error", alert=True)
