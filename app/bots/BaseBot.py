import asyncio
import logging
from telethon import TelegramClient, events, Button
from app.database.connection import db
from app.models import User
from app.utils.datetime_utils import utc_now

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
        
        await asyncio.sleep(1)
        
        # Get proxy configuration
        from app.models import ProxyManager
        proxy_manager = ProxyManager(self.db_connection)
        proxy = await proxy_manager.get_proxy_dict()
        
        session_name = f'sessions/{self.bot_name.lower()}_bot'
        self.client = TelegramClient(session_name, self.api_id, self.api_hash,
                                   proxy=proxy,
                                   system_version="4.16.30-vxCUSTOM",
                                   device_model="Desktop",
                                   app_version="1.0")
        
        await self.client.start(bot_token=self.bot_token)
        
        self.register_handlers()
        
        logger.info(f"{self.bot_name} bot started and handlers registered")
        if proxy:
            logger.info(f"{self.bot_name} using proxy: {proxy.get('proxy_type')}://{proxy.get('addr')}:{proxy.get('port')}")
    
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
            
            try:
                await self.db_connection.users.delete_many({"user_id": None})
            except (ValueError, OSError) as e:
                pass
            
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
                        "created_at": utc_now(),
                        "tos_accepted": None,
                        "last_upload_date": None
                    },
                    "$unset": {"user_id": 1}
                },
                upsert=True
            )
            
            user_doc = await self.db_connection.users.find_one({"telegram_user_id": event.sender_id})
            
            if not user_doc:
                user_doc = await self.db_connection.users.find_one({"user_id": event.sender_id})
                if user_doc:
                    await self.db_connection.users.update_one(
                        {"_id": user_doc["_id"]},
                        {
                            "$set": {"telegram_user_id": event.sender_id},
                            "$unset": {"user_id": 1}
                        }
                    )
                    user_doc["telegram_user_id"] = event.sender_id
            
            if not user_doc:
                raise ValueError(f"Failed to create or find user {event.sender_id}")
            
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
                "created_at": user_doc.get("created_at", utc_now()),
                "upload_count_today": user_doc.get("upload_count_today", 0),
                "last_upload_date": user_doc.get("last_upload_date")
            }
            
            user = User(**user_dict)
            logger.info(f"[{self.bot_name}] User ready: {user.telegram_user_id} - {user.first_name}")
            return user
                
        except ValueError as e:
            logger.error(f"[{self.bot_name}] Validation error: {str(e)}")
            raise
        except OSError as e:
            logger.error(f"[{self.bot_name}] Database error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"[{self.bot_name}] Failed to get/create user for {event.sender_id}: {str(e)}", exc_info=True)
            
            try:
                existing = await self.db_connection.users.find_one({"telegram_user_id": event.sender_id})
                if existing:
                    return User(**{
                        "_id": existing.get("_id"),
                        "telegram_user_id": existing.get("telegram_user_id"),
                        "username": existing.get("username"),
                        "first_name": existing.get("first_name", 'User'),
                        "last_name": existing.get("last_name"),
                        "language_code": existing.get("language_code"),
                        "is_admin": existing.get("is_admin", False),
                        "balance": existing.get("balance", 0.0),
                        "tos_accepted": existing.get("tos_accepted"),
                        "created_at": existing.get("created_at", utc_now()),
                        "upload_count_today": existing.get("upload_count_today", 0),
                        "last_upload_date": existing.get("last_upload_date")
                    })
                
                simple_user = {
                    "telegram_user_id": event.sender_id,
                    "username": getattr(event.sender, 'username', None),
                    "first_name": getattr(event.sender, 'first_name', 'User'),
                    "last_name": getattr(event.sender, 'last_name', None),
                    "language_code": getattr(event.sender, 'lang_code', None),
                    "is_admin": False,
                    "balance": 0.0,
                    "upload_count_today": 0,
                    "created_at": utc_now(),
                    "tos_accepted": None,
                    "last_upload_date": None
                }
                
                result = await self.db_connection.users.insert_one(simple_user)
                simple_user["_id"] = result.inserted_id
                return User(**simple_user)
                
            except (ValueError, OSError) as fallback_error:
                logger.error(f"[{self.bot_name}] Fallback failed: {str(fallback_error)}")
                raise ValueError(f"Failed to create or find user {event.sender_id}")
    
    async def send_message(self, chat_id: int, message: str, buttons=None):
        """Send message with optional buttons"""
        try:
            logger.info(f"[{self.bot_name}] Sending message to {chat_id}: {message[:50]}...")
            if buttons:
                logger.info(f"[{self.bot_name}] Message includes {len(buttons)} button rows")
            return await self.client.send_message(chat_id, message, buttons=buttons)
        except (ValueError, OSError) as e:
            logger.error(f"[{self.bot_name}] Failed to send message to {chat_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"[{self.bot_name}] Unexpected error sending message: {str(e)}", exc_info=True)
            return None
    
    async def edit_message(self, event, message: str, buttons=None):
        """Edit message with optional buttons"""
        try:
            logger.info(f"[{self.bot_name}] Editing message for {event.sender_id}: {message[:50]}...")
            if buttons:
                logger.info(f"[{self.bot_name}] Edit includes {len(buttons)} button rows")
            await event.edit(message, buttons=buttons)
        except ValueError as e:
            if "Content of the message was not modified" not in str(e):
                logger.error(f"[{self.bot_name}] Validation error editing message: {str(e)}")
        except OSError as e:
            logger.error(f"[{self.bot_name}] Network error editing message: {str(e)}")
        except Exception as e:
            logger.error(f"[{self.bot_name}] Failed to edit message for {event.sender_id}: {str(e)}", exc_info=True)
    
    async def answer_callback(self, event, message: str = None, alert: bool = False):
        """Answer callback query"""
        try:
            callback_data = event.data.decode('utf-8') if event.data else 'unknown'
            logger.info(f"[{self.bot_name}] Answering callback '{callback_data}' for user {event.sender_id}")
            if message:
                logger.info(f"[{self.bot_name}] Callback answer: {message}")
            await event.answer(message, alert=alert)
        except (ValueError, OSError) as e:
            logger.debug(f"[{self.bot_name}] Failed to answer callback: {str(e)}")
        except Exception as e:
            logger.debug(f"[{self.bot_name}] Unexpected error answering callback: {str(e)}")
