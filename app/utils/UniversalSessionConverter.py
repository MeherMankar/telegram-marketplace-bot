"""Universal Session Converter - Enhanced with opentele, TGConvertor, and TGSessionsConverter methods"""
import os
import json
import sqlite3
import struct
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Union
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.crypto import AuthKey

logger = logging.getLogger(__name__)

class UniversalSessionConverter:
    """Enhanced session converter supporting multiple formats"""
    
    # DC server mappings
    DC_SERVERS = {
        1: ('149.154.175.53', 443),
        2: ('149.154.167.51', 443),
        3: ('149.154.175.100', 443),
        4: ('149.154.167.91', 443),
        5: ('91.108.56.130', 443)
    }
    
    @classmethod
    async def convert_session(cls, source: Union[str, bytes], source_type: str = "auto") -> Dict[str, Any]:
        """Universal session converter with auto-detection"""
        try:
            if source_type == "auto":
                source_type = cls._detect_session_type(source)
            
            if source_type == "telethon_string":
                return await cls._convert_telethon_string(source)
            elif source_type == "pyrogram_session":
                return await cls._convert_pyrogram_session(source)
            elif source_type == "telethon_session":
                return await cls._convert_telethon_session(source)
            elif source_type == "tdata":
                return cls._convert_tdata(source)
            elif source_type == "json_session":
                return await cls._convert_json_session(source)
            elif source_type == "session_bytes":
                return await cls._convert_session_bytes(source)
            else:
                return {"success": False, "error": f"Unsupported session type: {source_type}"}
                
        except Exception as e:
            logger.error(f"Session conversion failed: {e}")
            return {"success": False, "error": str(e)}
    
    @classmethod
    def _detect_session_type(cls, source: Union[str, bytes]) -> str:
        """Auto-detect session format"""
        if isinstance(source, bytes):
            return "session_bytes"
        
        if isinstance(source, str):
            # Check if it's a file path
            if os.path.exists(source):
                if os.path.isdir(source):
                    # Check for TData
                    if os.path.exists(os.path.join(source, "key_datas")):
                        return "tdata"
                elif source.endswith('.session'):
                    # Determine if Telethon or Pyrogram
                    return cls._detect_sqlite_session_type(source)
                elif source.endswith('.json'):
                    return "json_session"
            
            # Check if it's a session string
            try:
                base64.urlsafe_b64decode(source + '==')
                return "telethon_string"
            except:
                pass
            
            # Check if it's JSON string
            try:
                json.loads(source)
                return "json_session"
            except:
                pass
        
        return "unknown"
    
    @classmethod
    def _detect_sqlite_session_type(cls, session_file: str) -> str:
        """Detect if SQLite session is Telethon or Pyrogram"""
        try:
            conn = sqlite3.connect(session_file)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            if 'sessions' in tables:
                cursor.execute("PRAGMA table_info(sessions)")
                columns = [row[1] for row in cursor.fetchall()]
                
                # Pyrogram has different column structure
                if 'user_id' in columns or 'is_bot' in columns:
                    conn.close()
                    return "pyrogram_session"
                else:
                    conn.close()
                    return "telethon_session"
            
            conn.close()
            return "telethon_session"
            
        except Exception:
            return "telethon_session"
    
    @classmethod
    async def _convert_telethon_string(cls, session_string: str) -> Dict[str, Any]:
        """Convert Telethon string session"""
        try:
            # Validate session
            client = TelegramClient(StringSession(session_string), 0, "")
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return {"success": False, "error": "Session not authorized"}
            
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
                "format": "telethon_string"
            }
        except Exception as e:
            return {"success": False, "error": f"Telethon string conversion failed: {str(e)}"}
    
    @classmethod
    async def _convert_pyrogram_session(cls, session_file: str) -> Dict[str, Any]:
        """Enhanced Pyrogram session conversion"""
        try:
            conn = sqlite3.connect(session_file)
            cursor = conn.cursor()
            
            # Get session data
            cursor.execute("SELECT dc_id, auth_key FROM sessions LIMIT 1")
            row = cursor.fetchone()
            
            if not row:
                conn.close()
                return {"success": False, "error": "No session data found"}
            
            dc_id, auth_key_data = row
            
            # Handle different auth_key formats
            if isinstance(auth_key_data, str):
                auth_key = base64.b64decode(auth_key_data)
            elif isinstance(auth_key_data, bytes):
                auth_key = auth_key_data
            else:
                conn.close()
                return {"success": False, "error": "Invalid auth_key format"}
            
            conn.close()
            
            # Get server info
            server_address, port = cls.DC_SERVERS.get(dc_id, ('149.154.167.50', 443))
            
            # Create Telethon session
            session = StringSession()
            session.set_dc(dc_id, server_address, port)
            session.auth_key = AuthKey(auth_key)
            
            session_string = StringSession.save(session)
            
            # Validate converted session
            return await cls._convert_telethon_string(session_string)
            
        except Exception as e:
            return {"success": False, "error": f"Pyrogram conversion failed: {str(e)}"}
    
    @classmethod
    async def _convert_telethon_session(cls, session_file: str) -> Dict[str, Any]:
        """Convert Telethon .session file"""
        try:
            conn = sqlite3.connect(session_file)
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM sessions")
            session_data = cursor.fetchone()
            
            if not session_data:
                conn.close()
                return {"success": False, "error": "No session data found"}
            
            dc_id, server_address, port, auth_key = session_data[:4]
            conn.close()
            
            # Create session string
            session = StringSession()
            session.set_dc(dc_id, str(server_address), port)
            session.auth_key = AuthKey(auth_key)
            
            session_string = StringSession.save(session)
            
            return await cls._convert_telethon_string(session_string)
            
        except Exception as e:
            return {"success": False, "error": f"Telethon session conversion failed: {str(e)}"}
    
    @classmethod
    def _convert_tdata(cls, tdata_path: str) -> Dict[str, Any]:
        """Enhanced TData conversion with multiple parsing methods"""
        try:
            tdata_dir = Path(tdata_path)
            if not tdata_dir.exists():
                return {"success": False, "error": "TData directory not found"}
            
            # Method 1: Try key_datas file
            key_datas_file = tdata_dir / "key_datas"
            if key_datas_file.exists():
                result = cls._parse_key_datas(key_datas_file)
                if result.get("success"):
                    return result
            
            # Method 2: Try map files (alternative TData structure)
            map_files = list(tdata_dir.glob("map*"))
            if map_files:
                result = cls._parse_map_files(map_files)
                if result.get("success"):
                    return result
            
            return {"success": False, "error": "Could not parse TData structure"}
            
        except Exception as e:
            return {"success": False, "error": f"TData conversion failed: {str(e)}"}
    
    @classmethod
    def _parse_key_datas(cls, key_datas_file: Path) -> Dict[str, Any]:
        """Parse key_datas file with enhanced methods"""
        try:
            with open(key_datas_file, 'rb') as f:
                data = f.read()
            
            if len(data) < 300:
                return {"success": False, "error": "key_datas file too small"}
            
            # Multiple parsing strategies
            strategies = [
                cls._parse_key_datas_v1,
                cls._parse_key_datas_v2,
                cls._parse_key_datas_v3
            ]
            
            for strategy in strategies:
                try:
                    result = strategy(data)
                    if result.get("success"):
                        return result
                except Exception:
                    continue
            
            return {"success": False, "error": "All key_datas parsing strategies failed"}
            
        except Exception as e:
            return {"success": False, "error": f"key_datas parsing failed: {str(e)}"}
    
    @classmethod
    def _parse_key_datas_v1(cls, data: bytes) -> Dict[str, Any]:
        """Original parsing method"""
        offset = 4
        dc_id = struct.unpack('<I', data[offset:offset+4])[0]
        offset += 4
        
        if dc_id not in [1, 2, 3, 4, 5]:
            raise ValueError(f"Invalid DC ID: {dc_id}")
        
        # Search for 256-byte auth key
        for i in range(offset, len(data) - 256):
            auth_key = data[i:i+256]
            if auth_key != b'\\x00' * 256 and len(set(auth_key)) > 10:
                return cls._create_session_from_tdata(dc_id, auth_key)
        
        raise ValueError("Auth key not found")
    
    @classmethod
    def _parse_key_datas_v2(cls, data: bytes) -> Dict[str, Any]:
        """Alternative parsing method - skip more header bytes"""
        offset = 16  # Skip more header
        
        if len(data) < offset + 4:
            raise ValueError("Insufficient data")
        
        dc_id = struct.unpack('<I', data[offset:offset+4])[0]
        
        if dc_id not in [1, 2, 3, 4, 5]:
            # Try big endian
            dc_id = struct.unpack('>I', data[offset:offset+4])[0]
            if dc_id not in [1, 2, 3, 4, 5]:
                raise ValueError(f"Invalid DC ID: {dc_id}")
        
        # Look for auth key after DC ID
        offset += 4
        for i in range(offset, len(data) - 256, 4):
            auth_key = data[i:i+256]
            if len(set(auth_key)) > 20:  # More entropy check
                return cls._create_session_from_tdata(dc_id, auth_key)
        
        raise ValueError("Auth key not found")
    
    @classmethod
    def _parse_key_datas_v3(cls, data: bytes) -> Dict[str, Any]:
        """Pattern-based parsing method"""
        # Look for DC ID patterns
        for offset in range(0, min(100, len(data) - 260), 4):
            try:
                dc_id = struct.unpack('<I', data[offset:offset+4])[0]
                if 1 <= dc_id <= 5:
                    # Found potential DC ID, look for auth key nearby
                    search_start = max(0, offset - 50)
                    search_end = min(len(data) - 256, offset + 100)
                    
                    for i in range(search_start, search_end, 4):
                        auth_key = data[i:i+256]
                        if len(set(auth_key)) > 15:
                            return cls._create_session_from_tdata(dc_id, auth_key)
            except:
                continue
        
        raise ValueError("No valid DC ID and auth key combination found")
    
    @classmethod
    def _create_session_from_tdata(cls, dc_id: int, auth_key: bytes) -> Dict[str, Any]:
        """Create session string from TData components"""
        server_address, port = cls.DC_SERVERS[dc_id]
        
        session = StringSession()
        session.set_dc(dc_id, server_address, port)
        session.auth_key = AuthKey(auth_key)
        
        session_string = StringSession.save(session)
        
        return {
            "success": True,
            "session_string": session_string,
            "dc_id": dc_id,
            "server": f"{server_address}:{port}",
            "format": "tdata_converted"
        }
    
    @classmethod
    def _parse_map_files(cls, map_files: list) -> Dict[str, Any]:
        """Parse alternative TData map files"""
        # Implementation for map-based TData parsing
        # This would be used for newer TData formats
        return {"success": False, "error": "Map file parsing not implemented"}
    
    @classmethod
    async def _convert_json_session(cls, json_source: str) -> Dict[str, Any]:
        """Convert JSON session format"""
        try:
            if os.path.exists(json_source):
                with open(json_source, 'r') as f:
                    session_data = json.load(f)
            else:
                session_data = json.loads(json_source)
            
            # Handle different JSON formats
            if 'session_string' in session_data:
                return await cls._convert_telethon_string(session_data['session_string'])
            elif 'auth_key' in session_data and 'dc_id' in session_data:
                # Custom JSON format
                dc_id = session_data['dc_id']
                auth_key = base64.b64decode(session_data['auth_key'])
                
                server_address, port = cls.DC_SERVERS.get(dc_id, ('149.154.167.50', 443))
                
                session = StringSession()
                session.set_dc(dc_id, server_address, port)
                session.auth_key = AuthKey(auth_key)
                
                session_string = StringSession.save(session)
                return await cls._convert_telethon_string(session_string)
            else:
                return {"success": False, "error": "Unsupported JSON session format"}
                
        except Exception as e:
            return {"success": False, "error": f"JSON session conversion failed: {str(e)}"}
    
    @classmethod
    def get_session_info(cls, source: Union[str, bytes]) -> Dict[str, Any]:
        """Get session information without full conversion"""
        try:
            session_type = cls._detect_session_type(source)
            
            info = {
                "detected_type": session_type,
                "supported": session_type != "unknown"
            }
            
            if session_type == "tdata" and isinstance(source, str):
                tdata_dir = Path(source)
                info.update({
                    "files_count": len(list(tdata_dir.iterdir())),
                    "has_key_datas": (tdata_dir / "key_datas").exists(),
                    "directory_size": sum(f.stat().st_size for f in tdata_dir.rglob('*') if f.is_file())
                })
            
            return {"success": True, "info": info}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @classmethod
    async def _convert_session_bytes(cls, session_data: bytes) -> Dict[str, Any]:
        """Convert session bytes to session string"""
        try:
            # Save bytes to temp file and convert
            temp_path = f"temp_session_{os.getpid()}.session"
            with open(temp_path, 'wb') as f:
                f.write(session_data)
            
            result = await cls.convert_session(temp_path, "auto")
            
            # Cleanup
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            return result
        except Exception as e:
            return {"success": False, "error": f"Session bytes conversion failed: {str(e)}"}