"""Simple OTP Service - Inspired by TeleGuard's approach"""
import asyncio
import logging
import time
from typing import Dict, Optional
from telethon import TelegramClient
from telethon import errors
from telethon.sessions import StringSession
from telethon.crypto import AuthKey

logger = logging.getLogger(__name__)

class SimpleOtpService:
    """Simplified OTP service for phone number verification"""
    
    # Class-level storage to persist between instances
    _pending_sessions = {}  # {user_id: {phone, client, sent_code, timestamp}}
    
    def __init__(self, api_id: int, api_hash: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.pending_sessions = SimpleOtpService._pending_sessions
        
        # Device configurations for realistic sessions
        self.devices = [
            {"model": "Samsung SM-G973F", "system": "Android 10", "version": "9.4.1"},
            {"model": "Google Pixel 6", "system": "Android 13", "version": "9.7.1"},
            {"model": "OnePlus 9 Pro", "system": "Android 12", "version": "9.6.0"},
            {"model": "Xiaomi Mi 11", "system": "Android 11", "version": "9.5.2"},
        ]
    
    def get_random_device(self):
        """Get random device configuration"""
        import random
        return random.choice(self.devices)
    
    async def send_otp(self, phone_number: str, user_id: int) -> dict:
        """Send OTP to phone number"""
        client = None
        try:
            logger.info(f"[OTP_SERVICE] Sending OTP to {phone_number} for user {user_id}")
            
            # Clean up any existing session for this user
            await self._cleanup_user_session(user_id)
            
            # Get random device info
            device = self.get_random_device()
            logger.info(f"[OTP_SERVICE] Using device: {device['model']}")
            
            # Create client with device info
            client = TelegramClient(
                StringSession(),
                self.api_id,
                self.api_hash,
                connection_retries=3,
                retry_delay=2,
                timeout=10,
                device_model=device["model"],
                system_version=device["system"],
                app_version=device["version"]
            )
            
            logger.info(f"[OTP_SERVICE] Connecting to Telegram...")
            await client.connect()
            
            if not client.is_connected():
                raise ConnectionError("Failed to connect to Telegram")
            
            logger.info(f"[OTP_SERVICE] Connected successfully, sending code request to {phone_number}")
            
            # Send code request
            sent_code = await client.send_code_request(phone_number)
            logger.info(f"[OTP_SERVICE] Code sent! Hash: {sent_code.phone_code_hash[:10]}...")
            
            # Store session data
            self.pending_sessions[user_id] = {
                'phone': phone_number,
                'client': client,
                'sent_code': sent_code,
                'timestamp': time.time()
            }
            
            logger.info(f"[OTP_SERVICE] OTP sent successfully to {phone_number}")
            return {
                'success': True,
                'phone': phone_number,
                'code_hash': sent_code.phone_code_hash
            }
            
        except errors.PhoneNumberInvalidError:
            logger.error(f"[OTP_SERVICE] Invalid phone number: {phone_number}")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            return {
                'success': False,
                'error': 'Invalid phone number format. Use international format with country code (e.g., +1234567890)'
            }
        except errors.PhoneNumberBannedError:
            logger.error(f"[OTP_SERVICE] Phone number banned: {phone_number}")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            return {
                'success': False,
                'error': 'This phone number is banned from Telegram'
            }
        except errors.FloodWaitError as e:
            logger.error(f"[OTP_SERVICE] Flood wait error: {e.seconds} seconds")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            return {
                'success': False,
                'error': f'Too many requests. Please wait {e.seconds} seconds and try again'
            }
        except ConnectionError as e:
            logger.error(f"[OTP_SERVICE] Connection error: {str(e)}")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            return {
                'success': False,
                'error': 'Failed to connect to Telegram. Please check your internet connection and try again'
            }
        except Exception as e:
            logger.error(f"[OTP_SERVICE] Failed to send OTP to {phone_number}: {str(e)}")
            import traceback
            logger.error(f"[OTP_SERVICE] Traceback: {traceback.format_exc()}")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            return {
                'success': False,
                'error': f"Failed to send OTP: {str(e)}"
            }
    
    async def verify_otp(self, phone_number: str, otp_code: str, user_id: int, password: str = None) -> dict:
        """Verify OTP code and create session"""
        try:
            if user_id not in self.pending_sessions:
                return {
                    'success': False,
                    'error': 'No pending OTP session found'
                }
            
            session_data = self.pending_sessions[user_id]
            client = session_data['client']
            sent_code = session_data['sent_code']
            phone = session_data['phone']
            
            logger.info(f"Verifying OTP {otp_code} for user {user_id}")
            
            try:
                # Sign in with OTP
                await client.sign_in(phone, otp_code, phone_code_hash=sent_code.phone_code_hash)
                
            except errors.SessionPasswordNeededError:
                if not password:
                    return {
                        'success': False,
                        'requires_password': True,
                        'error': 'Two-factor authentication required'
                    }
                
                # Sign in with 2FA password
                await client.sign_in(password=password)
            
            except errors.PhoneCodeInvalidError:
                await self._cleanup_user_session(user_id)
                return {
                    'success': False,
                    'error': 'Invalid OTP code'
                }
            
            # Get account info
            me = await client.get_me()
            
            # Get session string
            session_string = StringSession.save(client.session)
            
            # Clean up
            await client.disconnect()
            del self.pending_sessions[user_id]
            
            logger.info(f"Successfully created session for {phone}")
            
            return {
                'success': True,
                'session_string': session_string,
                'account_info': {
                    'id': me.id,
                    'username': me.username,
                    'first_name': me.first_name,
                    'last_name': me.last_name,
                    'phone': me.phone,
                    'premium': getattr(me, 'premium', False),
                    'verified': getattr(me, 'verified', False)
                },
                'tfa_password': password if password else None
            }
            
        except Exception as e:
            logger.error(f"OTP verification failed for user {user_id}: {str(e)}")
            
            # Clean up on error
            await self._cleanup_user_session(user_id)
            
            return {
                'success': False,
                'error': f"Verification failed: {str(e)}"
            }
    
    async def _cleanup_user_session(self, user_id: int):
        """Clean up user's pending session"""
        try:
            if user_id in self.pending_sessions:
                session_data = self.pending_sessions[user_id]
                client = session_data.get('client')
                if client:
                    try:
                        await client.disconnect()
                    except:
                        pass
                del self.pending_sessions[user_id]
                logger.info(f"Cleaned up session for user {user_id}")
        except Exception as e:
            logger.error(f"Session cleanup error for user {user_id}: {e}")
    
    async def cleanup_expired_sessions(self):
        """Clean up expired pending sessions"""
        try:
            current_time = time.time()
            expired_users = []
            
            for user_id, session_data in self.pending_sessions.items():
                if current_time - session_data['timestamp'] > 300:  # 5 minutes
                    expired_users.append(user_id)
            
            for user_id in expired_users:
                await self._cleanup_user_session(user_id)
                logger.info(f"Cleaned up expired session for user {user_id}")
                
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")