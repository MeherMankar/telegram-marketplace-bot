"""TData to Session Converter - Based on nicollasm/tdata2session_converter"""
import os
import struct
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from app.utils.security_utils import validate_path, safe_join_path

logger = logging.getLogger(__name__)

class TDataConverter:
    """Convert Telegram Desktop TData to session string"""
    
    @staticmethod
    def convert_tdata_to_session(tdata_path: str) -> Dict[str, Any]:
        """Convert TData folder to Telethon session string"""
        try:
            tdata_dir = Path(tdata_path)
            if not tdata_dir.exists() or not tdata_dir.is_dir():
                return {"success": False, "error": "TData directory not found"}
            
            key_datas_file = tdata_dir / "key_datas"
            if not key_datas_file.exists():
                return {"success": False, "error": "key_datas file not found"}
            
            with open(key_datas_file, 'rb') as f:
                key_data = f.read()
            
            if len(key_data) < 4:
                return {"success": False, "error": "Invalid key_datas file"}
            
            try:
                offset = 4
                
                if len(key_data) < offset + 4:
                    return {"success": False, "error": "Incomplete key_datas file"}
                
                dc_id = struct.unpack('<I', key_data[offset:offset+4])[0]
                offset += 4
                
                if dc_id not in [1, 2, 3, 4, 5]:
                    return {"success": False, "error": f"Invalid DC ID: {dc_id}"}
                
                auth_key = None
                
                for i in range(offset, len(key_data) - 256):
                    potential_key = key_data[i:i+256]
                    if potential_key != b'\x00' * 256 and len(set(potential_key)) > 10:
                        auth_key = potential_key
                        break
                
                if not auth_key:
                    return {"success": False, "error": "Auth key not found in key_datas"}
                
                dc_servers = {
                    1: ('149.154.175.53', 443),
                    2: ('149.154.167.51', 443), 
                    3: ('149.154.175.100', 443),
                    4: ('149.154.167.91', 443),
                    5: ('91.108.56.130', 443)
                }
                
                server_address, port = dc_servers[dc_id]
                
                from telethon.sessions import StringSession
                from telethon.crypto import AuthKey
                
                temp_session = StringSession()
                temp_session.set_dc(dc_id, server_address, port)
                temp_session.auth_key = AuthKey(auth_key)
                
                session_string = StringSession.save(temp_session)
                
                return {
                    "success": True,
                    "session_string": session_string,
                    "dc_id": dc_id,
                    "server": f"{server_address}:{port}",
                    "format": "tdata_converted"
                }
                
            except (struct.error, ValueError) as e:
                logger.error(f"TData parsing error: {e}")
                return {"success": False, "error": f"Failed to parse TData: {str(e)}"}
            
        except (OSError, IOError) as e:
            logger.error(f"TData IO error: {e}")
            return {"success": False, "error": f"TData conversion failed: {str(e)}"}
        except Exception as e:
            logger.error(f"TData conversion error: {e}", exc_info=True)
            return {"success": False, "error": f"TData conversion failed: {str(e)}"}
    
    @staticmethod
    def extract_tdata_info(tdata_path: str) -> Dict[str, Any]:
        """Extract basic info from TData without full conversion"""
        try:
            tdata_dir = Path(tdata_path)
            if not tdata_dir.exists():
                return {"success": False, "error": "TData directory not found"}
            
            info = {
                "has_key_datas": (tdata_dir / "key_datas").exists(),
                "has_settings": (tdata_dir / "settings").exists(),
                "has_usertag": (tdata_dir / "usertag").exists(),
                "files_count": len(list(tdata_dir.iterdir())),
                "directory_size": sum(f.stat().st_size for f in tdata_dir.rglob('*') if f.is_file())
            }
            
            if info["has_key_datas"]:
                try:
                    with open(tdata_dir / "key_datas", 'rb') as f:
                        key_data = f.read()
                    
                    if len(key_data) >= 8:
                        dc_id = struct.unpack('<I', key_data[4:8])[0]
                        if 1 <= dc_id <= 5:
                            info["dc_id"] = dc_id
                        
                except (struct.error, ValueError, OSError, IOError):
                    pass
            
            return {"success": True, "info": info}
            
        except (OSError, IOError) as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def validate_tdata_structure(tdata_path: str) -> bool:
        """Validate if directory has valid TData structure"""
        try:
            tdata_dir = Path(tdata_path)
            if not tdata_dir.exists() or not tdata_dir.is_dir():
                return False
            
            required_files = ["key_datas"]
            for file_name in required_files:
                if not (tdata_dir / file_name).exists():
                    return False
            
            key_datas_file = tdata_dir / "key_datas"
            if key_datas_file.stat().st_size < 100:
                return False
            
            return True
            
        except (OSError, IOError, ValueError):
            return False
