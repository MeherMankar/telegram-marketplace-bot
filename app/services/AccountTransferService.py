import logging
import os
import tempfile
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from app.utils.encryption import encrypt_data, decrypt_data
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class AccountTransferService:
    """Handle secure account transfers to buyers"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
    
    async def transfer_account(self, listing_id: str, buyer_id: int) -> dict:
        """Transfer account to buyer after successful payment"""
        try:
            # Get listing and account details
            listing = await self.db_connection.listings.find_one({"_id": listing_id})
            if not listing:
                return {"success": False, "error": "Listing not found"}
            
            account = await self.db_connection.accounts.find_one({"_id": listing["account_id"]})
            if not account:
                return {"success": False, "error": "Account not found"}
            
            # Prepare transfer package
            transfer_data = await self._prepare_transfer_package(account)
            
            # Create transfer record
            transfer_record = {
                "listing_id": listing_id,
                "account_id": account["_id"],
                "buyer_id": buyer_id,
                "seller_id": listing["seller_id"],
                "transfer_data": transfer_data,
                "transferred_at": utc_now(),
                "status": "completed"
            }
            
            await self.db_connection.transfers.insert_one(transfer_record)
            
            # Send account details to buyer
            await self._deliver_to_buyer(buyer_id, transfer_data, account)
            
            # Update account status
            await self.db_connection.accounts.update_one(
                {"_id": account["_id"]},
                {
                    "$set": {
                        "status": "transferred",
                        "transferred_to": buyer_id,
                        "transferred_at": utc_now()
                    }
                }
            )
            
            logger.info(f"Account {account['_id']} transferred to buyer {buyer_id}")
            return {"success": True, "message": "Account transferred successfully"}
            
        except Exception as e:
            logger.error(f"Failed to transfer account: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _prepare_transfer_package(self, account: dict) -> dict:
        """Prepare secure transfer package"""
        try:
            # Decrypt session string
            session_string = account.get("session_string")
            if account.get("session_encrypted"):
                session_string = decrypt_data(session_string)
            
            # Get account information
            account_info = await self._get_account_info(session_string)
            
            # Prepare package
            package = {
                "session_string": session_string,
                "account_info": account_info,
                "username": account.get("username"),
                "phone_number": account.get("phone_number"),
                "country": account.get("country"),
                "creation_year": account.get("creation_year"),
                "verification_results": account.get("checks", {}),
                "transfer_instructions": self._get_transfer_instructions()
            }
            
            return package
            
        except Exception as e:
            logger.error(f"Failed to prepare transfer package: {str(e)}")
            return {}
    
    async def _get_account_info(self, session_string: str) -> dict:
        """Get current account information"""
        try:
            client = TelegramClient(StringSession(session_string), 0, "")
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return {"error": "Session not authorized"}
            
            me = await client.get_me()
            
            # Get additional info
            dialogs = await client.get_dialogs(limit=5)
            contacts = await client.get_contacts()
            
            info = {
                "id": me.id,
                "username": me.username,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "phone": me.phone,
                "is_premium": getattr(me, 'premium', False),
                "dialog_count": len(dialogs),
                "contact_count": len(contacts),
                "last_seen": utc_now().isoformat()
            }
            
            await client.disconnect()
            return info
            
        except Exception as e:
            logger.error(f"Failed to get account info: {str(e)}")
            return {"error": str(e)}
    
    def _get_transfer_instructions(self) -> dict:
        """Get transfer instructions for buyer"""
        return {
            "steps": [
                "1. Save the session string in a secure location",
                "2. Use the session string with Telethon or Pyrogram",
                "3. Do not share the session string with anyone",
                "4. Change account password immediately after login",
                "5. Enable 2FA for additional security",
                "6. Update recovery email and phone if needed"
            ],
            "warnings": [
                "⚠️ Session strings provide full account access",
                "⚠️ Do not use the account for spam or illegal activities",
                "⚠️ Account may be banned if misused",
                "⚠️ No refunds after successful transfer"
            ],
            "support": "Contact support if you face any issues"
        }
    
    async def _deliver_to_buyer(self, buyer_id: int, transfer_data: dict, account: dict):
        """Deliver account details to buyer via bot"""
        try:
            # This would be implemented in the buyer bot
            # For now, just log the delivery
            logger.info(f"Account delivery initiated for buyer {buyer_id}")
            
            # Store delivery data for buyer bot to pick up
            delivery_data = {
                "buyer_id": buyer_id,
                "account_id": account["_id"],
                "transfer_data": transfer_data,
                "delivered": False,
                "created_at": utc_now()
            }
            
            await self.db_connection.deliveries.insert_one(delivery_data)
            
        except Exception as e:
            logger.error(f"Failed to deliver to buyer: {str(e)}")
    
    async def get_pending_deliveries(self, buyer_id: int) -> list:
        """Get pending deliveries for a buyer"""
        try:
            deliveries = await self.db_connection.deliveries.find({
                "buyer_id": buyer_id,
                "delivered": False
            }).to_list(length=None)
            
            return deliveries
            
        except Exception as e:
            logger.error(f"Failed to get pending deliveries: {str(e)}")
            return []
    
    async def mark_delivery_completed(self, delivery_id: str) -> dict:
        """Mark delivery as completed"""
        try:
            await self.db_connection.deliveries.update_one(
                {"_id": delivery_id},
                {
                    "$set": {
                        "delivered": True,
                        "delivered_at": utc_now()
                    }
                }
            )
            
            return {"success": True, "message": "Delivery marked as completed"}
            
        except Exception as e:
            logger.error(f"Failed to mark delivery completed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def create_session_file(self, session_string: str, filename: str = None) -> str:
        """Create .session file from session string"""
        try:
            if not filename:
                filename = f"account_{datetime.now().strftime('%Y%m%d_%H%M%S')}.session"
            
            # Create temporary session file
            temp_dir = tempfile.gettempdir()
            file_path = os.path.join(temp_dir, filename)
            
            # Create client and save session
            client = TelegramClient(file_path.replace('.session', ''), 0, "")
            client.session.set_dc(1, '149.154.175.50', 443)  # Default DC
            client.session.auth_key = session_string  # Simplified
            client.session.save()
            
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to create session file: {str(e)}")
            return None
    
    async def get_transfer_history(self, user_id: int, user_type: str = "buyer") -> list:
        """Get transfer history for user"""
        try:
            if user_type == "buyer":
                query = {"buyer_id": user_id}
            else:
                query = {"seller_id": user_id}
            
            transfers = await self.db_connection.transfers.find(query)\
                .sort("transferred_at", -1)\
                .to_list(length=None)
            
            return transfers
            
        except Exception as e:
            logger.error(f"Failed to get transfer history: {str(e)}")
            return []
    
    async def validate_transfer(self, transfer_id: str) -> dict:
        """Validate a completed transfer"""
        try:
            transfer = await self.db_connection.transfers.find_one({"_id": transfer_id})
            if not transfer:
                return {"success": False, "error": "Transfer not found"}
            
            # Check if session is still valid
            session_string = transfer["transfer_data"].get("session_string")
            if session_string:
                client = TelegramClient(StringSession(session_string), 0, "")
                try:
                    await client.connect()
                    is_valid = await client.is_user_authorized()
                    await client.disconnect()
                    
                    return {
                        "success": True,
                        "valid": is_valid,
                        "transfer_id": transfer_id,
                        "transferred_at": transfer["transferred_at"]
                    }
                except:
                    return {
                        "success": True,
                        "valid": False,
                        "error": "Session validation failed"
                    }
            
            return {"success": False, "error": "No session data found"}
            
        except Exception as e:
            logger.error(f"Failed to validate transfer: {str(e)}")
            return {"success": False, "error": str(e)}