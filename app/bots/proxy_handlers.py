"""Proxy management handlers for AdminBot"""
import logging
from telethon import Button
from app.models import ProxyManager, ProxySettings

logger = logging.getLogger(__name__)

async def handle_proxy_menu(self, event):
    """Show proxy management menu"""
    try:
        is_admin, user = await self.check_admin_access(event)
        if not is_admin:
            await self.answer_callback(event, "❌ Access denied", alert=True)
            return
        
        proxy_manager = ProxyManager(self.db_connection)
        proxies = await proxy_manager.get_user_proxies(user.telegram_user_id)
        
        text = f"🌐 **Proxy Management**\n\n📊 Total Proxies: {len(proxies)}\n\n**Supported:**\n✅ SOCKS5/HTTP (Recommended)\n⚠️ MTProto (May fail on cloud)"
        
        buttons = [
            [Button.inline("➕ Add Proxy", "proxy_add")],
            [Button.inline("📋 View Proxies", "proxy_list")],
            [Button.inline("⚙️ Global Settings", "proxy_settings")],
            [Button.inline("🔙 Back", "security_settings")]
        ]
        
        await self.edit_message(event, text, buttons)
        await self.answer_callback(event)
    except Exception as e:
        logger.error(f"Proxy menu error: {e}")
        await self.answer_callback(event, "❌ Error", alert=True)

async def handle_proxy_list(self, event):
    """Show user's proxies"""
    try:
        is_admin, user = await self.check_admin_access(event)
        if not is_admin:
            await self.answer_callback(event, "❌ Access denied", alert=True)
            return
        
        proxy_manager = ProxyManager(self.db_connection)
        proxies = await proxy_manager.get_user_proxies(user.telegram_user_id)
        
        if not proxies:
            text = "📋 **Your Proxies**\n\n❌ No proxies added"
            buttons = [[Button.inline("➕ Add Proxy", "proxy_add")], [Button.inline("🔙 Back", "proxy_menu")]]
        else:
            text = f"📋 **Your Proxies** ({len(proxies)})\n\n"
            buttons = []
            for p in proxies[:10]:
                text += f"• {p['name']}\n  {p['type']}://{p['server']}:{p['port']}\n\n"
                buttons.append([Button.inline(f"🗑️ Delete {p['name']}", f"proxy_delete:{p['_id']}")])
            buttons.append([Button.inline("➕ Add More", "proxy_add")])
            buttons.append([Button.inline("🔙 Back", "proxy_menu")])
        
        await self.edit_message(event, text, buttons)
        await self.answer_callback(event)
    except Exception as e:
        logger.error(f"Proxy list error: {e}")
        await self.answer_callback(event, "❌ Error", alert=True)

async def handle_proxy_delete(self, event, proxy_id):
    """Delete a proxy"""
    try:
        is_admin, user = await self.check_admin_access(event)
        if not is_admin:
            await self.answer_callback(event, "❌ Access denied", alert=True)
            return
        
        proxy_manager = ProxyManager(self.db_connection)
        success = await proxy_manager.delete_user_proxy(user.telegram_user_id, proxy_id)
        
        if success:
            await self.answer_callback(event, "✅ Proxy deleted", alert=True)
        else:
            await self.answer_callback(event, "❌ Failed to delete", alert=True)
        
        await handle_proxy_list(self, event)
    except Exception as e:
        logger.error(f"Proxy delete error: {e}")
        await self.answer_callback(event, "❌ Error", alert=True)

async def handle_proxy_settings(self, event):
    """Show global proxy settings menu"""
    try:
        is_admin, user = await self.check_admin_access(event)
        if not is_admin:
            await self.answer_callback(event, "❌ Access denied", alert=True)
            return
        
        proxy_manager = ProxyManager(self.db_connection)
        proxy = await proxy_manager.get_proxy()
        
        if proxy and proxy.enabled:
            status = f"✅ **Global Proxy Enabled**\n\nType: {proxy.proxy_type.upper()}\nHost: {proxy.proxy_host}\nPort: {proxy.proxy_port}\n"
            if proxy.proxy_username:
                status += f"Username: {proxy.proxy_username}\n"
        else:
            status = "❌ **Global Proxy Disabled**\n\nNo global proxy configured"
        
        buttons = [
            [Button.inline("🔄 Test Proxy", "proxy_test")] if proxy else [],
            [Button.inline("❌ Disable Proxy", "proxy_disable")] if proxy and proxy.enabled else [],
            [Button.inline("🔙 Back", "proxy_menu")]
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
➕ **Add Proxy**

**Telegram Links:**
• `t.me/socks?server=1.2.3.4&port=1080&user=admin&pass=123` ✅
• `t.me/proxy?server=1.2.3.4&port=443&secret=abc123` ⚠️
• `tg://socks?server=1.2.3.4&port=1080` ✅

**Manual Format:**
• `socks5://user:pass@1.2.3.4:1080` ✅ Recommended
• `http://user:pass@1.2.3.4:8080` ✅ Recommended
• `mtproto://1.2.3.4:443:secret` ⚠️ May not work

Send /cancel to abort.
        """
        
        await self.edit_message(event, message, [[Button.inline("🔙 Cancel", "proxy_menu")]])
        await self.answer_callback(event)
        
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
            await self.send_message(event.chat_id, "❌ Cancelled", [[Button.inline("🔙 Back", "proxy_menu")]])
            return
        
        proxy_manager = ProxyManager(self.db_connection)
        proxy_data = await proxy_manager.parse_telegram_proxy_link(text)
        
        if not proxy_data:
            await self.send_message(event.chat_id, "❌ Invalid proxy format. Try again or /cancel")
            return
        
        success, result = await proxy_manager.add_user_proxy(user.telegram_user_id, proxy_data)
        
        await self.db_connection.users.update_one(
            {"telegram_user_id": user.telegram_user_id},
            {"$set": {"state": None}}
        )
        
        if success:
            await self.send_message(
                event.chat_id,
                f"✅ **Proxy Added!**\n\nType: {proxy_data['type']}\nServer: {proxy_data['server']}:{proxy_data['port']}",
                [[Button.inline("📋 View Proxies", "proxy_list")]]
            )
        else:
            await self.send_message(event.chat_id, f"❌ Error: {result}")
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
            await self.edit_message(event, "❌ No proxy configured", [[Button.inline("🔙 Back", "proxy_settings")]])
            return
        
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        import os
        
        test_client = TelegramClient(StringSession(), int(os.getenv('API_ID')), os.getenv('API_HASH'), proxy=proxy_dict)
        
        try:
            await test_client.connect()
            await test_client.disconnect()
            
            await self.edit_message(
                event,
                f"✅ **Proxy test successful!**\n\nConnection established through:\n{proxy_dict['proxy_type']}://{proxy_dict['addr']}:{proxy_dict['port']}",
                [[Button.inline("🔙 Back", "proxy_settings")]]
            )
        except Exception as e:
            await self.edit_message(
                event,
                f"❌ **Proxy test failed!**\n\nError: {str(e)}\n\nPlease check your proxy configuration.",
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
        
        await self.edit_message(event, "✅ **Proxy disabled**\n\n⚠️ Restart bots to apply changes.", [[Button.inline("🔙 Back", "proxy_settings")]])
        await self.answer_callback(event)
    except Exception as e:
        logger.error(f"Proxy disable error: {e}")
        await self.answer_callback(event, "❌ Error", alert=True)
