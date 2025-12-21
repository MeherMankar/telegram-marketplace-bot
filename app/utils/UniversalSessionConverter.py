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
from app.utils.security_utils import validate_path, safe_join_path

logger = logging.getLogger(__name__)

class UniversalSessionConverter:
    """Enhanced session converter supporting multiple formats"""
    
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
                
        except ValueError as e:
            logger.error(f"Session conversion validation error: {e}")
            return {"success": False, "error": str(e)}
        except OSError as e:
            logger.error(f"Session conversion IO error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Session conversion failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    @classmethod
    def _detect_session_type(cls, source: Union[str, bytes]) -> str:
        """Auto-detect session format"""
        if isinstance(source, bytes):
            return "session_bytes"
        
        if isinstance(source, str):
            if os.path.exists(source):
                if os.path.isdir(source):
                    if os.path.exists(os.path.join(source, "key_datas")):
                        return "tdata"
                elif source.endswith('.session'):
                    return cls._detect_sqlite_session_type(source)
                elif source.endswith('.json'):
                    return "json_session"
            
            try:
                base64.urlsafe_b64decode(source + '==')
                return "telethon_string"
            except (ValueError, TypeError):
                pass
            
            try:
                json.loads(source)
                return "json_session"
            except (ValueError, TypeError):
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
                
                result = "pyrogram_session" if 'user_id' in columns or 'is_bot' in columns else "telethon_session"
            else:
                result = "telethon_session"
            
            return result
        finally:
            try:
                conn.close()
            except (NameError, sqlite3.ProgrammingError):
                pass
    
    @classmethod
    async def _convert_telethon_string(cls, session_string: str) -> Dict[str, Any]:
        """Convert Telethon string session"""
        client = None
        try:
            client = TelegramClient(StringSession(session_string), 0, "")
            await client.connect()
            
            if not await client.is_user_authorized():
                return {"success": False, "error": "Session not authorized"}
            
            me = await client.get_me()
            
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
        except ValueError as e:
            return {"success": False, "error": f"Telethon string validation failed: {str(e)}"}
        except OSError as e:
            return {"success": False, "error": f"Telethon connection failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Telethon conversion failed: {str(e)}"}
        finally:
            if client:
                try:
                    await client.disconnect()
                except (OSError, RuntimeError):
                    pass
    
    @classmethod
    async def _convert_pyrogram_session(cls, session_file: str) -> Dict[str, Any]:
        """Enhanced Pyrogram session conversion"""
        conn = None
        try:
            conn = sqlite3.connect(session_file)
            cursor = conn.cursor()
            
            cursor.execute("SELECT dc_id, auth_key FROM sessions LIMIT 1")
            row = cursor.fetchone()
            
            if not row:
                return {"success": False, "error": "No session data found"}
            
            dc_id, auth_key_data = row
            
            if isinstance(auth_key_data, str):
                auth_key = base64.b64decode(auth_key_data)
            elif isinstance(auth_key_data, bytes):
                auth_key = auth_key_data
            else:
                return {"success": False, "error": "Invalid auth_key format"}
            
            server_address, port = cls.DC_SERVERS.get(dc_id, ('149.154.167.50', 443))
            
            session = StringSession()
            session.set_dc(dc_id, server_address, port)
            session.auth_key = AuthKey(auth_key)
            
            session_string = StringSession.save(session)
            
            return await cls._convert_telethon_string(session_string)
            
        except (ValueError, OSError) as e:
            return {"success": False, "error": f"Pyrogram conversion failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Pyrogram conversion failed: {str(e)}"}
        finally:
            if conn:
                try:
                    conn.close()
                except (sqlite3.ProgrammingError, OSError):
                    pass
    
    @classmethod
    async def _convert_telethon_session(cls, session_file: str) -> Dict[str, Any]:
        """Convert Telethon .session file"""
        conn = None
        try:
            conn = sqlite3.connect(session_file)
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM sessions")
            session_data = cursor.fetchone()
            
            if not session_data:
                return {"success": False, "error": "No session data found"}
            
            dc_id, server_address, port, auth_key = session_data[:4]
            
            session = StringSession()
            session.set_dc(dc_id, str(server_address), port)
            session.auth_key = AuthKey(auth_key)
            
            session_string = StringSession.save(session)
            
            return await cls._convert_telethon_string(session_string)
            
        except (ValueError, OSError) as e:
            return {"success": False, "error": f"Telethon session conversion failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Telethon session conversion failed: {str(e)}"}
        finally:
            if conn:
                try:
                    conn.close()
                except (sqlite3.ProgrammingError, OSError):
                    pass
    
    @classmethod
    def _convert_tdata(cls, tdata_path: str) -> Dict[str, Any]:
        """Enhanced TData conversion with multiple parsing methods"""
        try:
            tdata_dir = Path(tdata_path)
            if not tdata_dir.exists():
                return {"success": False, "error": "TData directory not found"}
            
            key_datas_file = tdata_dir / "key_datas"
            if key_datas_file.exists():
                result = cls._parse_key_datas(key_datas_file)
                if result.get("success"):
                    return result
            
            map_files = list(tdata_dir.glob("map*"))
            if map_files:
                result = cls._parse_map_files(map_files)
                if result.get("success"):
                    return result
            
            return {"success": False, "error": "Could not parse TData structure"}
            
        except (ValueError, OSError) as e:
            return {"success": False, "error": f"TData conversion failed: {str(e)}"}
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
                except (ValueError, RuntimeError, OSError, IOError, struct.error):
                    continue
            
            return {"success": False, "error": "All key_datas parsing strategies failed"}
            
        except (ValueError, OSError, IOError) as e:
            return {"success": False, "error": f"key_datas parsing failed: {str(e)}"}
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
        
        for i in range(offset, len(data) - 256):
            auth_key = data[i:i+256]
            if auth_key != b'\x00' * 256 and len(set(auth_key)) > 10:
                return cls._create_session_from_tdata(dc_id, auth_key)
        
        raise ValueError("Auth key not found")
    
    @classmethod
    def _parse_key_datas_v2(cls, data: bytes) -> Dict[str, Any]:
        """Alternative parsing method - skip more header bytes"""
        offset = 16
        
        if len(data) < offset + 4:
            raise ValueError("Insufficient data")
        
        dc_id = struct.unpack('<I', data[offset:offset+4])[0]
        
        if dc_id not in [1, 2, 3, 4, 5]:
            dc_id = struct.unpack('>I', data[offset:offset+4])[0]
            if dc_id not in [1, 2, 3, 4, 5]:
                raise ValueError(f"Invalid DC ID: {dc_id}")
        
        offset += 4
        for i in range(offset, len(data) - 256, 4):
            auth_key = data[i:i+256]
            if len(set(auth_key)) > 20:
                return cls._create_session_from_tdata(dc_id, auth_key)
        
        raise ValueError("Auth key not found")
    
    @classmethod
    def _parse_key_datas_v3(cls, data: bytes) -> Dict[str, Any]:
        """Pattern-based parsing method"""
        for offset in range(0, min(100, len(data) - 260), 4):
            try:
                dc_id = struct.unpack('<I', data[offset:offset+4])[0]
                if 1 <= dc_id <= 5:
                    search_start = max(0, offset - 50)
                    search_end = min(len(data) - 256, offset + 100)
                    
                    for i in range(search_start, search_end, 4):
                        auth_key = data[i:i+256]
                        if len(set(auth_key)) > 15:
                            return cls._create_session_from_tdata(dc_id, auth_key)
            except (struct.error, ValueError):
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
            
            if 'session_string' in session_data:
                return await cls._convert_telethon_string(session_data['session_string'])
            elif 'auth_key' in session_data and 'dc_id' in session_data:
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
                
        except (ValueError, OSError, json.JSONDecodeError) as e:
            return {"success": False, "error": f"JSON session conversion failed: {str(e)}"}
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
            
        except (ValueError, OSError) as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @classmethod
    async def _convert_session_bytes(cls, session_data: bytes) -> Dict[str, Any]:
        """Convert session bytes to session string"""
        temp_path = None
        try:
            temp_path = f"temp_session_{os.getpid()}.session"
            with open(temp_path, 'wb') as f:
                f.write(session_data)
            
            result = await cls.convert_session(temp_path, "auto")
            return result
        except (ValueError, OSError, IOError) as e:
            return {"success": False, "error": f"Session bytes conversion failed: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Session bytes conversion failed: {str(e)}"}
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except (OSError, IOError):
                    pass
