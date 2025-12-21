"""Account Login Service - Login and store accounts for marketplace"""
import logging
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PasswordHashInvalidError
from app.utils.UniversalSessionConverter import UniversalSessionConverter
from app.utils.encryption import encrypt_data
from app.models import AccountStatus
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class AccountLoginService:
    """Service to login accounts and store them for selling"""
    
    def __init__(self, db_connection, api_id: int, api_hash: str):
        self.db_connection = db_connection
        self.api_id = api_id
        self.api_hash = api_hash
    
    async def login_and_store_account(self, session_source, seller_id: int, source_type: str = "auto") -> dict:
        """Login to account and store in database for selling"""
        try:
            # Convert session using enhanced converter
            conversion_result = await UniversalSessionConverter.convert_session(session_source, source_type)
            
            if not conversion_result.get("success"):
                return {"success": False, "error": conversion_result.get("error", "Session conversion failed")}
            
            session_string = conversion_result["session_string"]
            
            # Login and get account info
            client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
            
            try:
                await client.connect()
                
                if not await client.is_user_authorized():
                    await client.disconnect()
                    return {"success": False, "error": "Session not authorized"}
                
                # Get account details
                me = await client.get_me()
                
                # Get additional account info
                full_user = await client.get_entity(me.id)
                
                await client.disconnect()
                
                # Encrypt session for storage
                encrypted_session = encrypt_data(session_string)
                
                # Store account in database
                account_data = {
                    "seller_id": seller_id,
                    "telegram_account_id": me.id,
                    "username": me.username,
                    "first_name": me.first_name,
                    "last_name": me.last_name,
                    "phone_number": me.phone,
                    "session_string": encrypted_session,
                    "status": AccountStatus.PENDING,
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                    "obtained_via": conversion_result.get("format", "unknown"),
                    "account_info": {
                        "id": me.id,
                        "username": me.username,
                        "first_name": me.first_name,
                        "last_name": me.last_name,
                        "phone": me.phone,
                        "premium": getattr(me, 'premium', False),
                        "verified": getattr(me, 'verified', False),
                        "restricted": getattr(me, 'restricted', False),
                        "scam": getattr(me, 'scam', False),
                        "fake": getattr(me, 'fake', False)
                    }
                }
                
                # Check if account already exists
                existing = await self.db_connection.accounts.find_one({
                    "telegram_account_id": me.id
                })
                
                if existing:
                    return {"success": False, "error": "Account already exists in marketplace"}
                
                # Insert account
                result = await self.db_connection.accounts.insert_one(account_data)
                
                return {
                    "success": True,
                    "account_id": str(result.inserted_id),
                    "account_info": {
                        "id": me.id,
                        "username": me.username,
                        "first_name": me.first_name,
                        "last_name": me.last_name,
                        "phone": me.phone,
                        "premium": getattr(me, 'premium', False)
                    }
                }
                
            except Exception as e:
                try:
                    await client.disconnect()
                except:
                    pass
                return {"success": False, "error": f"Login failed: {str(e)}"}
                
        except Exception as e:
            logger.error(f"Account login service error: {e}")
            return {"success": False, "error": str(e)}
    
    async def login_with_phone_otp(self, phone: str, seller_id: int) -> dict:
        """Login using phone and OTP"""
        try:
            client = TelegramClient(StringSession(), self.api_id, self.api_hash)
            await client.connect()
            
            # Send code
            sent_code = await client.send_code_request(phone)
            
            return {
                "success": True,
                "phone_code_hash": sent_code.phone_code_hash,
                "client_session": StringSession.save(client.session),
                "message": "OTP sent successfully"
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def verify_otp_and_store(self, phone: str, code: str, phone_code_hash: str, 
                                   client_session: str, seller_id: int, password: str = None) -> dict:
        """Verify OTP and store account"""
        try:
            client = TelegramClient(StringSession(client_session), self.api_id, self.api_hash)
            await client.connect()
            
            try:
                # Sign in with code
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                
            except SessionPasswordNeededError:
                if not password:
                    await client.disconnect()
                    return {"success": False, "requires_password": True, "error": "2FA password required"}
                
                # Sign in with password
                await client.sign_in(password=password)
            
            except PhoneCodeInvalidError:
                await client.disconnect()
                return {"success": False, "error": "Invalid OTP code"}
            
            except PasswordHashInvalidError:
                await client.disconnect()
                return {"success": False, "error": "Invalid 2FA password"}
            
            # Get account info
            me = await client.get_me()
            session_string = StringSession.save(client.session)
            
            await client.disconnect()
            
            # Store account using the session
            return await self.login_and_store_account(session_string, seller_id, "telethon_string")
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def transfer_account_to_buyer(self, account_id: str, buyer_id: int) -> dict:
        """Transfer account ownership to buyer"""
        try:
            from bson import ObjectId
            
            # Get account
            account = await self.db_connection.accounts.find_one({"_id": ObjectId(account_id)})
            if not account:
                return {"success": False, "error": "Account not found"}
            
            # Decrypt session for transfer
            from app.utils.encryption import decrypt_data
            session_string = decrypt_data(account["session_string"])
            
            # Update account status
            await self.db_connection.accounts.update_one(
                {"_id": ObjectId(account_id)},
                {
                    "$set": {
                        "status": AccountStatus.SOLD,
                        "buyer_id": buyer_id,
                        "sold_at": utc_now(),
                        "updated_at": utc_now()
                    }
                }
            )
            
            return {
                "success": True,
                "session_string": session_string,
                "account_info": account.get("account_info", {}),
                "tfa_password": account.get("tfa_password")
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}