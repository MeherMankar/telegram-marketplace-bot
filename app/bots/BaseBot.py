import asyncio
import logging
import os
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from app.database.connection import db
from app.models import User
from app.services import AdminService
from datetime import datetime

logger = logging.getLogger(__name__)

class BaseBot:
    def __init__(self, api_id: int, api_hash: str, bot_token: str, db_connection, bot_name: str = None):
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_token = bot_token
        self.db_connection = db_connection
        self.bot_name = bot_name or self.__class__.__name__
        self.client = None
        self.admin_service = None
    
    async def start(self):
        """Start the bot"""
        if not self.bot_token:
            logger.warning(f"{self.bot_name} token not provided, skipping")
            return
        
        # Add delay for time sync
        await asyncio.sleep(1)
        
        self.client = TelegramClient(f'{self.bot_name}_bot', self.api_id, self.api_hash,
                                   system_version="4.16.30-vxCUSTOM",
                                   device_model="Desktop",
                                   app_version="1.0")
        
        await self.client.start(bot_token=self.bot_token)
        
        # Register event handlers AFTER client is started
        self.register_handlers()
        
        logger.info(f"{self.bot_name} bot started and handlers registered")
    
    async def run_until_disconnected(self):
        """Keep the bot running"""
        if self.client:
            await self.client.run_until_disconnected()
    
    def register_handlers(self):
        """Register event handlers - to be implemented by subclasses"""
        pass
    
    async def get_or_create_user(self, event) -> User:
        """Get or create user from event using upsert to avoid duplicate key errors"""
        try:
            logger.info(f"[{self.bot_name}] Getting/creating user for sender_id: {event.sender_id}")
            
            logger.info(f"[{self.bot_name}] User data: {event.sender.first_name} (@{event.sender.username})")
            
            # First, clean up any records with null user_id to prevent duplicate key errors
            try:
                await self.db_connection.users.delete_many({"user_id": None})
            except:
                pass
            
            # Use upsert to safely create or update user
            result = await self.db_connection.users.update_one(
                {"telegram_user_id": event.sender_id},
                {
                    "$set": {
                        "username": event.sender.username,
                        "first_name": event.sender.first_name,
                        "last_name": event.sender.last_name,
                        "language_code": getattr(event.sender, 'lang_code', None)
                    },
                    "$setOnInsert": {
                        "telegram_user_id": event.sender_id,
                        "is_admin": False,
                        "balance": 0.0,
                        "upload_count_today": 0,
                        "created_at": datetime.utcnow(),
                        "tos_accepted": None,
                        "last_upload_date": None
                    },
                    "$unset": {"user_id": 1}
                },
                upsert=True
            )
            
            # Get the user record
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": event.sender_id})
            
            if not user_doc:
                # Fallback: try to find by old user_id field
                user_doc = await self.db_connection.users.find_one({"user_id": event.sender_id})
                if user_doc:
                    # Migrate the record
                    await self.db_connection.users.update_one(
                        {"_id": user_doc["_id"]},
                        {
                            "$set": {"telegram_user_id": event.sender_id},
                            "$unset": {"user_id": 1}
                        }
                    )
                    user_doc["telegram_user_id"] = event.sender_id
            
            if not user_doc:
                raise Exception(f"Failed to create or find user {event.sender_id}")
            
            # Ensure all required fields exist with defaults
            user_dict = {
                "_id": user_doc.get("_id"),
                "telegram_user_id": user_doc.get("telegram_user_id"),
                "username": user_doc.get("username"),
                "first_name": user_doc.get("first_name"),
                "last_name": user_doc.get("last_name"),
                "language_code": user_doc.get("language_code"),
                "is_admin": user_doc.get("is_admin", False),
                "balance": user_doc.get("balance", 0.0),
                "tos_accepted": user_doc.get("tos_accepted"),
                "created_at": user_doc.get("created_at", datetime.utcnow()),
                "upload_count_today": user_doc.get("upload_count_today", 0),
                "last_upload_date": user_doc.get("last_upload_date")
            }
            
            user = User(**user_dict)
            logger.info(f"[{self.bot_name}] User ready: {user.telegram_user_id} - {user.first_name}")
            return user
                
        except Exception as e:
            if "duplicate key error" in str(e) and "user_id" in str(e):
                # Handle duplicate key error by cleaning up and retrying
                try:
                    # Clean up null user_id records
                    await self.db_connection.users.delete_many({"user_id": None})
                    
                    # Try to find existing user
                    user_doc = await self.db_connection.users.find_one({"telegram_user_id": event.sender_id})
                    if user_doc:
                        user_dict = {
                            "_id": user_doc.get("_id"),
                            "telegram_user_id": user_doc.get("telegram_user_id"),
                            "username": user_doc.get("username"),
                            "first_name": user_doc.get("first_name"),
                            "last_name": user_doc.get("last_name"),
                            "language_code": user_doc.get("language_code"),
                            "is_admin": user_doc.get("is_admin", False),
                            "balance": user_doc.get("balance", 0.0),
                            "tos_accepted": user_doc.get("tos_accepted"),
                            "created_at": user_doc.get("created_at", datetime.utcnow()),
                            "upload_count_today": user_doc.get("upload_count_today", 0),
                            "last_upload_date": user_doc.get("last_upload_date")
                        }
                        return User(**user_dict)
                    
                    # If no user found, create new one directly
                    new_user_doc = {
                        "telegram_user_id": event.sender_id,
                        "username": event.sender.username,
                        "first_name": event.sender.first_name,
                        "last_name": event.sender.last_name,
                        "language_code": getattr(event.sender, 'lang_code', None),
                        "is_admin": False,
                        "balance": 0.0,
                        "upload_count_today": 0,
                        "created_at": datetime.utcnow(),
                        "tos_accepted": None,
                        "last_upload_date": None
                    }
                    
                    result = await self.db_connection.users.insert_one(new_user_doc)
                    new_user_doc["_id"] = result.inserted_id
                    return User(**new_user_doc)
                    
                except Exception as retry_error:
                    logger.error(f"[{self.bot_name}] Retry failed: {str(retry_error)}")
            
            logger.error(f"[{self.bot_name}] Failed to get/create user for {event.sender_id}: {str(e)}")
            import traceback
            logger.error(f"[{self.bot_name}] Traceback: {traceback.format_exc()}")
            raise
    
    async def send_message(self, chat_id: int, message: str, buttons=None):
        """Send message with optional buttons"""
        try:
            logger.info(f"[{self.bot_name}] Sending message to {chat_id}: {message[:50]}...")
            if buttons:
                logger.info(f"[{self.bot_name}] Message includes {len(buttons)} button rows")
            return await self.client.send_message(chat_id, message, buttons=buttons)
        except Exception as e:
            logger.error(f"[{self.bot_name}] Failed to send message to {chat_id}: {str(e)}")
            return None
    
    async def edit_message(self, event, message: str, buttons=None):
        """Edit message with optional buttons"""
        try:
            logger.info(f"[{self.bot_name}] Editing message for {event.sender_id}: {message[:50]}...")
            if buttons:
                logger.info(f"[{self.bot_name}] Edit includes {len(buttons)} button rows")
            await event.edit(message, buttons=buttons)
        except Exception as e:
            logger.error(f"[{self.bot_name}] Failed to edit message for {event.sender_id}: {str(e)}")
    
    async def answer_callback(self, event, message: str = None, alert: bool = False):
        """Answer callback query"""
        try:
            callback_data = event.data.decode('utf-8') if event.data else 'unknown'
            logger.info(f"[{self.bot_name}] Answering callback '{callback_data}' for user {event.sender_id}")
            if message:
                logger.info(f"[{self.bot_name}] Callback answer: {message}")
            await event.answer(message, alert=alert)
        except Exception as e:
            logger.debug(f"[{self.bot_name}] Failed to answer callback for {event.sender_id}: {str(e)}")