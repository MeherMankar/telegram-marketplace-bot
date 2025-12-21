"""
Code Interceptor Service - Intercepts Telegram login codes for sold accounts
Integrated from AuthBot functionality
"""
import asyncio
import logging
import re
from typing import Dict, Optional, List
from telethon import TelegramClient, events
from telethon.errors import SessionRevokedError, UnauthorizedError, AuthKeyUnregisteredError
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)


class CodeInterceptorService:
    """Service to intercept and forward Telegram login codes for sold accounts"""
    
    def __init__(self, api_id: int, api_hash: str, db_connection):
        self.api_id = api_id
        self.api_hash = api_hash
        self.db_connection = db_connection
        self.account_clients: Dict[str, TelegramClient] = {}
        self.pending_codes: Dict[str, List[int]] = {}  # {account_id: [buyer_user_ids]}
        self.account_id_to_db_id: Dict[int, str] = {}  # {telegram_account_id: db_account_id}
    
    async def start_intercepting_account(self, account_id: str, session_string: str, buyer_user_id: int):
        """Start intercepting codes for a sold account"""
        try:
            from app.utils.encryption import decrypt_data
            
            # Decrypt session
            decrypted_session = decrypt_data(session_string)
            
            # Create client
            client = TelegramClient(
                StringSession(decrypted_session),
                self.api_id,
                self.api_hash
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.warning(f"Account {account_id} session not authorized")
                return False
            
            me = await client.get_me()
            telegram_account_id = me.id
            
            # Store mapping
            self.account_id_to_db_id[telegram_account_id] = account_id
            self.account_clients[account_id] = client
            
            # Add buyer to pending codes list
            if account_id not in self.pending_codes:
                self.pending_codes[account_id] = []
            if buyer_user_id not in self.pending_codes[account_id]:
                self.pending_codes[account_id].append(buyer_user_id)
            
            # Register message handler
            @client.on(events.NewMessage())
            async def code_handler(event):
                try:
                    # Skip own messages
                    if event.sender_id == telegram_account_id:
                        return
                    
                    text = event.message.text or ""
                    text_lower = text.lower()
                    
                    # Check if message contains login code
                    if any(keyword in text_lower for keyword in [
                        "код для входа", "code is", "login code", "ваш код",
                        "verification code", "telegram code"
                    ]):
                        # Extract 5-digit code
                        codes = re.findall(r'\b\d{5}\b', text)
                        
                        if codes and account_id in self.pending_codes:
                            code_value = codes[0]
                            logger.info(f"Intercepted code {code_value} for account {account_id}")
                            
                            # Send code to all waiting buyers
                            for user_id in self.pending_codes[account_id]:
                                await self.send_code_to_buyer(user_id, code_value)
                            
                            # Clear pending list
                            self.pending_codes[account_id] = []
                            
                            logger.info(f"Code {code_value} sent to buyers for account {account_id}")
                
                except Exception as e:
                    logger.error(f"Error in code handler for account {account_id}: {e}")
            
            logger.info(f"✅ Started intercepting codes for account {account_id} (Telegram ID: {telegram_account_id})")
            return True
            
        except (SessionRevokedError, UnauthorizedError, AuthKeyUnregisteredError) as e:
            logger.warning(f"Session invalid for account {account_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error starting code interception for account {account_id}: {e}")
            return False
    
    async def send_code_to_buyer(self, buyer_user_id: int, code_value: str):
        """Send intercepted code to buyer via buyer bot"""
        try:
            # Import here to avoid circular dependency
            from app.main import buyer_bot
            
            if buyer_bot and buyer_bot.client:
                message = f"""🔐 **Login Code Received**

Your Telegram login code: **{code_value}**

⚠️ **Security Warning:**
• Never share this code with anyone
• This code is for logging into YOUR purchased account
• Telegram will NEVER ask for this code

If you didn't request this code, ignore this message."""
                
                await buyer_bot.client.send_message(buyer_user_id, message)
                logger.info(f"Code sent to buyer {buyer_user_id}")
        except Exception as e:
            logger.error(f"Error sending code to buyer {buyer_user_id}: {e}")
    
    async def stop_intercepting_account(self, account_id: str):
        """Stop intercepting codes for an account"""
        try:
            if account_id in self.account_clients:
                client = self.account_clients[account_id]
                await client.disconnect()
                del self.account_clients[account_id]
                
                # Clean up mappings
                telegram_id = None
                for tid, aid in self.account_id_to_db_id.items():
                    if aid == account_id:
                        telegram_id = tid
                        break
                
                if telegram_id:
                    del self.account_id_to_db_id[telegram_id]
                
                if account_id in self.pending_codes:
                    del self.pending_codes[account_id]
                
                logger.info(f"Stopped intercepting codes for account {account_id}")
                return True
        except Exception as e:
            logger.error(f"Error stopping code interception for account {account_id}: {e}")
            return False
    
    async def add_buyer_to_pending(self, account_id: str, buyer_user_id: int):
        """Add buyer to pending codes list"""
        if account_id not in self.pending_codes:
            self.pending_codes[account_id] = []
        if buyer_user_id not in self.pending_codes[account_id]:
            self.pending_codes[account_id].append(buyer_user_id)
            logger.info(f"Added buyer {buyer_user_id} to pending codes for account {account_id}")
    
    async def cleanup_expired_sessions(self):
        """Clean up disconnected or invalid sessions"""
        try:
            accounts_to_remove = []
            
            for account_id, client in self.account_clients.items():
                try:
                    if not client.is_connected():
                        accounts_to_remove.append(account_id)
                except:
                    accounts_to_remove.append(account_id)
            
            for account_id in accounts_to_remove:
                await self.stop_intercepting_account(account_id)
            
            if accounts_to_remove:
                logger.info(f"Cleaned up {len(accounts_to_remove)} expired sessions")
        
        except Exception as e:
            logger.error(f"Error cleaning up sessions: {e}")
    
    async def get_active_interceptions(self) -> List[str]:
        """Get list of accounts currently being intercepted"""
        return list(self.account_clients.keys())
    
    async def shutdown(self):
        """Shutdown all interception clients"""
        logger.info("Shutting down code interceptor service...")
        
        for account_id in list(self.account_clients.keys()):
            await self.stop_intercepting_account(account_id)
        
        logger.info("Code interceptor service shutdown complete")
