import os
import json
import sqlite3
import struct
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
import logging
from app.utils.UniversalSessionConverter import UniversalSessionConverter

logger = logging.getLogger(__name__)

class SessionImporter:
    """Import sessions from various formats using enhanced converter"""
    
    @staticmethod
    async def import_session(file_path: str = None, session_string: str = None, session_data: bytes = None) -> dict:
        """Import session from file, string, or bytes using universal converter"""
        try:
            if session_string:
                return await UniversalSessionConverter.convert_session(session_string, "telethon_string")
            elif file_path:
                return await UniversalSessionConverter.convert_session(file_path, "auto")
            elif session_data:
                return await UniversalSessionConverter.convert_session(session_data, "session_bytes")
            else:
                raise ValueError("No session data provided")
        except Exception as e:
            logger.error(f"Session import failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _import_string_session(session_string: str) -> dict:
        """Import from Telethon string session - legacy method"""
        return await UniversalSessionConverter.convert_session(session_string, "telethon_string")
    
    @staticmethod
    async def _import_file_session(file_path: str) -> dict:
        """Import from file using universal converter"""
        return await UniversalSessionConverter.convert_session(file_path, "auto")
    
    @staticmethod
    async def _import_bytes_session(session_data: bytes) -> dict:
        """Import from session bytes using universal converter"""
        return await UniversalSessionConverter.convert_session(session_data, "session_bytes")
    
    @staticmethod
    def _extract_session_string(session_file: str) -> str:
        """Legacy method - use UniversalSessionConverter instead"""
        logger.warning("Using legacy _extract_session_string method")
        try:
            conn = sqlite3.connect(session_file)
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM sessions")
            session_data = cursor.fetchone()
            
            if not session_data:
                conn.close()
                return None
            
            dc_id, server_address, port, auth_key = session_data[0], session_data[1], session_data[2], session_data[3]
            
            if not isinstance(server_address, str):
                server_address = str(server_address)
            if not isinstance(auth_key, bytes):
                auth_key = bytes(auth_key) if hasattr(auth_key, '__iter__') else b''
            
            packed = struct.pack('>B', 1)
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
        """Import from Telegram Desktop tdata folder using enhanced converter"""
        return await UniversalSessionConverter.convert_session(tdata_path, "tdata")
    
    @staticmethod
    async def import_pyrogram_session(session_file: str) -> dict:
        """Import from Pyrogram session using enhanced converter"""
        return await UniversalSessionConverter.convert_session(session_file, "pyrogram_session")
    
    @staticmethod
    def get_session_info(source) -> dict:
        """Get session information without full conversion"""
        return UniversalSessionConverter.get_session_info(source)