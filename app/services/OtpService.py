import asyncio
import random
import time
import os
from typing import Dict, Any
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError, PasswordHashInvalidError, AuthRestartError, FloodWaitError
import logging

logger = logging.getLogger(__name__)

class OtpService:
    def __init__(self, api_id, api_hash):
        self.api_id = api_id
        self.api_hash = api_hash
        self.pending_auth = {}
        self.active_clients = {}
        self.devices = [
            {"model": "Samsung SM-G973F", "system": "Android 10", "version": "8.4.1"},
            {"model": "Google Pixel 6", "system": "Android 13", "version": "8.7.1"},
            {"model": "OnePlus 9 Pro", "system": "Android 12", "version": "8.6.0"},
        ]
    
    def get_random_device(self):
        return random.choice(self.devices)

    async def start_phone_auth(self, user_id: int, phone: str) -> Dict[str, Any]:
        try:
            phone = str(phone)
            phone_digits = ''.join(ch for ch in phone if ch.isdigit())
            
            session_name = f"auth_{user_id}_{phone_digits}"
            session_path = f"sessions/{session_name}.session"
            
            os.makedirs("sessions", exist_ok=True)
            
            device = self.get_random_device()
            client = TelegramClient(
                session_path, 
                self.api_id, 
                self.api_hash,
                device_model=device["model"],
                system_version=device["system"],
                app_version=device["version"],
                lang_code="en",
                system_lang_code="en",
                flood_sleep_threshold=0,
                auto_reconnect=True,
                connection_retries=5,
                retry_delay=1
            )
            
            logger.info(f"[OTP] Connecting client for user {user_id}")
            await client.connect()
            
            # Wait a bit for connection to stabilize
            await asyncio.sleep(1)
            
            if not client.is_connected():
                logger.error(f"[OTP] Client failed to connect for user {user_id}")
                await client.disconnect()
                return {'success': False, 'error': 'Failed to connect to Telegram servers'}
            
            # Ensure we're not already authorized (clean session)
            try:
                if await client.is_user_authorized():
                    logger.info(f"[OTP] Client already authorized, logging out for fresh auth")
                    await client.log_out()
                    await client.disconnect()
                    # Remove session file and reconnect
                    if os.path.exists(session_path):
                        os.remove(session_path)
                    await client.connect()
                    await asyncio.sleep(1)
            except Exception as auth_check_error:
                logger.warning(f"[OTP] Error checking authorization status: {auth_check_error}")
                # Continue anyway, might be a fresh session
            
            logger.info(f"[OTP] Sending code request to {phone} for user {user_id}")
            # Add a small delay before sending code request
            await asyncio.sleep(0.5)
            sent_code = await client.send_code_request(phone)
            logger.info(f"[OTP] Code sent successfully to {phone} for user {user_id}")
            
            # Store client and auth data
            self.active_clients[user_id] = client
            self.pending_auth[user_id] = {
                'phone': phone,
                'phone_code_hash': sent_code.phone_code_hash,
                'session_path': session_path,
                'session_name': session_name,
                'step': 'code',
                'request_time': time.time()
            }
            
            logger.info(f"[OTP] Auth data stored for user {user_id}, client connected: {client.is_connected()}")
            
            return {
                'success': True,
                'step': 'code',
                'message': f'Code sent to {phone}. Please enter the verification code.'
            }
                
        except FloodWaitError as e:
            logger.error(f"[OTP] Flood wait error for user {user_id}: {e.seconds} seconds")
            await self._cleanup_client(user_id)
            return {'success': False, 'error': f'Too many requests. Please wait {e.seconds} seconds and try again.'}
        except AuthRestartError:
            logger.error(f"[OTP] Telegram auth restart required for user {user_id}")
            await self._cleanup_client(user_id)
            return {'success': False, 'error': 'Telegram is having internal issues. Please try again in a few minutes.'}
        except Exception as e:
            logger.error(f"[OTP] Phone auth error for user {user_id}: {e}")
            await self._cleanup_client(user_id)
            return {'success': False, 'error': str(e)}

    async def verify_code(self, user_id: int, code: str) -> Dict[str, Any]:
        if user_id not in self.pending_auth:
            logger.error(f"[OTP] No pending authentication for user {user_id}")
            return {'success': False, 'error': 'No pending authentication'}
        
        try:
            auth_data = self.pending_auth[user_id]
            
            if user_id not in self.active_clients:
                logger.error(f"[OTP] Client session lost for user {user_id}")
                return {'success': False, 'error': 'Client session lost. Please restart authentication.'}
            
            client = self.active_clients[user_id]
            
            if not client.is_connected():
                logger.error(f"[OTP] Client disconnected for user {user_id}, reconnecting...")
                try:
                    await client.connect()
                    await asyncio.sleep(1)
                    if not client.is_connected():
                        logger.error(f"[OTP] Failed to reconnect client for user {user_id}")
                        await self._cleanup_client(user_id)
                        return {'success': False, 'error': 'Connection lost. Please restart authentication.'}
                except Exception as reconnect_error:
                    logger.error(f"[OTP] Error reconnecting client for user {user_id}: {reconnect_error}")
                    await self._cleanup_client(user_id)
                    return {'success': False, 'error': 'Failed to reconnect. Please restart authentication.'}
            
            try:
                logger.info(f"[OTP] Signing in with code for user {user_id}")
                await client.sign_in(
                    phone=auth_data['phone'],
                    code=code,
                    phone_code_hash=auth_data['phone_code_hash']
                )
                
                logger.info(f"[OTP] Successfully signed in, getting account info for user {user_id}")
                me = await client.get_me()
                session_string = client.session.save()
                
                # Clean up after successful auth
                await self._cleanup_client(user_id)
                
                logger.info(f"[OTP] Account verification complete for user {user_id}: {me.first_name} ({me.id})")
                return {
                    'success': True,
                    'step': 'complete',
                    'session_string': session_string,
                    'account_info': {
                        'id': me.id,
                        'username': me.username,
                        'first_name': me.first_name,
                        'last_name': me.last_name,
                        'phone': me.phone
                    }
                }
            except Exception as e:
                raise e
                
        except SessionPasswordNeededError:
            logger.info(f"[OTP] 2FA required for user {user_id}")
            auth_data['step'] = '2fa'
            return {'success': True, 'step': '2fa', 'message': 'Enter 2FA password', 'requires_password': True}
        except PhoneCodeInvalidError:
            logger.warning(f"[OTP] Invalid code for user {user_id}")
            return {'success': False, 'error': 'Invalid code'}
        except PhoneCodeExpiredError:
            logger.warning(f"[OTP] Code expired for user {user_id}")
            await self._cleanup_client(user_id)
            return {'success': False, 'error': 'The confirmation code has expired', 'expired': True}
        except FloodWaitError as e:
            logger.error(f"[OTP] Flood wait during code verification for user {user_id}: {e.seconds} seconds")
            return {'success': False, 'error': f'Too many attempts. Please wait {e.seconds} seconds and try again.'}
        except Exception as e:
            logger.error(f"[OTP] Code verify error for user {user_id}: {e}")
            return {'success': False, 'error': str(e)}

    async def verify_2fa(self, user_id: int, password: str) -> Dict[str, Any]:
        if user_id not in self.pending_auth or user_id not in self.active_clients:
            return {'success': False, 'error': 'No pending authentication or client session lost.'}
        
        try:
            client = self.active_clients[user_id]
            
            # Ensure client is connected
            if not client.is_connected():
                try:
                    await client.connect()
                    await asyncio.sleep(1)
                    if not client.is_connected():
                        return {'success': False, 'error': 'Connection lost. Please restart authentication.'}
                except Exception as reconnect_error:
                    logger.error(f"[OTP] Error reconnecting for 2FA for user {user_id}: {reconnect_error}")
                    return {'success': False, 'error': 'Failed to reconnect. Please restart authentication.'}
            
            await client.sign_in(password=password)
            
            me = await client.get_me()
            session_string = client.session.save()
            
            # Clean up after successful 2FA
            await self._cleanup_client(user_id)
            
            return {
                'success': True,
                'step': 'complete',
                'session_string': session_string,
                'account_info': {
                    'id': me.id,
                    'username': me.username,
                    'first_name': me.first_name,
                    'last_name': me.last_name,
                    'phone': me.phone
                }
            }
                
        except PasswordHashInvalidError:
            return {'success': False, 'error': 'Invalid password'}
        except FloodWaitError as e:
            logger.error(f"[OTP] Flood wait during 2FA verification for user {user_id}: {e.seconds} seconds")
            return {'success': False, 'error': f'Too many attempts. Please wait {e.seconds} seconds and try again.'}
        except Exception as e:
            logger.error(f"2FA verify error: {e}")
            return {'success': False, 'error': str(e)}

    async def _cleanup_client(self, user_id: int):
        logger.info(f"[OTP] Cleaning up client for user {user_id}")
        if user_id in self.active_clients:
            try:
                client = self.active_clients[user_id]
                if hasattr(client, 'is_connected') and client.is_connected():
                    await client.disconnect()
                logger.info(f"[OTP] Client disconnected for user {user_id}")
            except Exception as e:
                logger.error(f"[OTP] Error disconnecting client for user {user_id}: {e}")
            finally:
                self.active_clients.pop(user_id, None)
        
        # Clean up session file if exists
        if user_id in self.pending_auth:
            auth_data = self.pending_auth[user_id]
            session_path = auth_data.get('session_path')
            if session_path and os.path.exists(session_path):
                try:
                    os.remove(session_path)
                    logger.info(f"[OTP] Removed session file for user {user_id}")
                except Exception as e:
                    logger.error(f"[OTP] Error removing session file for user {user_id}: {e}")
            self.pending_auth.pop(user_id, None)
        else:
            # Still remove from pending_auth even if no session file
            self.pending_auth.pop(user_id, None)

    async def verify_account_ownership(self, phone_number: str, user_id: int) -> Dict[str, Any]:
        try:
            logger.info(f"[OTP] Starting ownership verification for {phone_number}, user {user_id}")
            
            # Clean up any existing session for this user first
            if user_id in self.active_clients or user_id in self.pending_auth:
                logger.info(f"[OTP] Cleaning up existing session for user {user_id}")
                await self._cleanup_client(user_id)
                await asyncio.sleep(1)  # Wait a bit before starting new auth
            
            result = await self.start_phone_auth(user_id, phone_number)
            if result.get('success'):
                result['message'] = 'OTP sent for ownership verification. Please enter the code to confirm you own this account.'
                logger.info(f"[OTP] Ownership verification OTP sent successfully to {phone_number}")
            else:
                logger.error(f"[OTP] Failed to send ownership verification OTP to {phone_number}: {result.get('error')}")
            return result
        except Exception as e:
            logger.error(f"[OTP] Ownership verification failed for {phone_number}: {str(e)}")
            return {'success': False, 'error': f'Verification failed: {str(e)}'}

    async def verify_otp_and_create_session(self, user_id: int, otp_code: str, password: str = None) -> Dict[str, Any]:
        logger.info(f"[OTP] Verifying OTP for user {user_id}, has_password: {bool(password)}")
        try:
            if password:
                return await self.verify_2fa(user_id, password)
            else:
                return await self.verify_code(user_id, otp_code)
        except Exception as e:
            logger.error(f"[OTP] Error in verify_otp_and_create_session for user {user_id}: {e}")
            await self._cleanup_client(user_id)
            return {'success': False, 'error': str(e)}