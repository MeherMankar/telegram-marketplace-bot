import os
import json
import sqlite3
import struct
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
import logging

logger = logging.getLogger(__name__)

class SessionImporter:
    """Import sessions from various formats"""
    
    @staticmethod
    async def import_session(file_path: str = None, session_string: str = None, session_data: bytes = None) -> dict:
        """Import session from file, string, or bytes"""
        try:
            if session_string:
                return await SessionImporter._import_string_session(session_string)
            elif file_path:
                return await SessionImporter._import_file_session(file_path)
            elif session_data:
                return await SessionImporter._import_bytes_session(session_data)
            else:
                raise ValueError("No session data provided")
        except Exception as e:
            logger.error(f"Session import failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _import_string_session(session_string: str) -> dict:
        """Import from Telethon string session"""
        try:
            # Test the session
            client = TelegramClient(StringSession(session_string), 0, "")
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return {"success": False, "error": "Session not authorized"}
            
            # Get account info
            me = await client.get_me()
            await client.disconnect()
            
            return {
                "success": True,
                "session_string": session_string,
                "telegram_account_id": me.id,
                "username": me.username,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "phone_number": me.phone,
                "format": "string_session"
            }
        except Exception as e:
            return {"success": False, "error": f"String session import failed: {str(e)}"}
    
    @staticmethod
    async def _import_file_session(file_path: str) -> dict:
        """Import from .session file"""
        try:
            if not os.path.exists(file_path):
                return {"success": False, "error": "Session file not found"}
            
            # Extract session string from .session file
            session_string = SessionImporter._extract_session_string(file_path)
            if not session_string:
                return {"success": False, "error": "Could not extract session string"}
            
            return await SessionImporter._import_string_session(session_string)
        except Exception as e:
            return {"success": False, "error": f"File session import failed: {str(e)}"}
    
    @staticmethod
    async def _import_bytes_session(session_data: bytes) -> dict:
        """Import from session bytes"""
        try:
            # Save bytes to temp file and import
            temp_path = f"temp_session_{os.getpid()}.session"
            with open(temp_path, 'wb') as f:
                f.write(session_data)
            
            result = await SessionImporter._import_file_session(temp_path)
            
            # Cleanup
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            return result
        except Exception as e:
            return {"success": False, "error": f"Bytes session import failed: {str(e)}"}
    
    @staticmethod
    def _extract_session_string(session_file: str) -> str:
        """Extract session string from .session file"""
        try:
            conn = sqlite3.connect(session_file)
            cursor = conn.cursor()
            
            # Get session data
            cursor.execute("SELECT * FROM sessions")
            session_data = cursor.fetchone()
            
            if not session_data:
                conn.close()
                return None
            
            # Convert to string session format
            dc_id, server_address, port, auth_key = session_data[0], session_data[1], session_data[2], session_data[3]
            
            # Pack session data
            packed = struct.pack('>B', 1)  # Version
            packed += struct.pack('>B', dc_id)
            packed += struct.pack('>H', len(server_address))
            packed += server_address.encode()
            packed += struct.pack('>H', port)
            packed += auth_key
            
            import base64
            session_string = base64.urlsafe_b64encode(packed).decode().rstrip('=')
            
            conn.close()
            return session_string
        except Exception as e:
            logger.error(f"Session string extraction failed: {str(e)}")
            return None
    
    @staticmethod
    async def import_tdata(tdata_path: str) -> dict:
        """Import from Telegram Desktop tdata folder"""
        try:
            if not os.path.exists(tdata_path):
                return {"success": False, "error": "tdata folder not found"}
            
            # Look for key_datas file
            key_data_file = os.path.join(tdata_path, "key_datas")
            if not os.path.exists(key_data_file):
                return {"success": False, "error": "key_datas file not found in tdata"}
            
            # This is a simplified implementation
            # Full tdata parsing requires more complex logic
            return {"success": False, "error": "tdata import not fully implemented"}
        except Exception as e:
            return {"success": False, "error": f"tdata import failed: {str(e)}"}
    
    @staticmethod
    async def import_pyrogram_session(session_file: str) -> dict:
        """Import from Pyrogram session"""
        try:
            if not os.path.exists(session_file):
                return {"success": False, "error": "Pyrogram session file not found"}
            
            # Pyrogram uses SQLite with different schema
            conn = sqlite3.connect(session_file)
            cursor = conn.cursor()
            
            # Get session info
            cursor.execute("SELECT * FROM sessions")
            session_data = cursor.fetchone()
            
            if not session_data:
                conn.close()
                return {"success": False, "error": "No session data found"}
            
            # Convert Pyrogram session to Telethon format
            # This requires format conversion logic
            conn.close()
            return {"success": False, "error": "Pyrogram conversion not fully implemented"}
        except Exception as e:
            return {"success": False, "error": f"Pyrogram import failed: {str(e)}"}