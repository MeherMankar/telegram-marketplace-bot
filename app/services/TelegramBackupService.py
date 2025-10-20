import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeFilename

logger = logging.getLogger(__name__)

class TelegramBackupService:
    def __init__(self, api_id: int, api_hash: str, backup_channel_id: int):
        self.api_id = api_id
        self.api_hash = api_hash
        self.backup_channel_id = backup_channel_id
        self.client = None
    
    async def initialize(self):
        """Initialize Telegram client for backup"""
        try:
            self.client = TelegramClient('backup_bot', self.api_id, self.api_hash)
            await self.client.start()
            logger.info("Telegram backup service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram backup service: {e}")
    
    async def backup_session_to_channel(self, session_file_path: str, 
                                      account_info: Dict[str, Any]) -> Dict[str, Any]:
        """Backup session file to Telegram channel"""
        try:
            if not self.client:
                await self.initialize()
            
            if not os.path.exists(session_file_path):
                return {'success': False, 'error': 'Session file not found'}
            
            # Create backup filename with metadata
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            phone = account_info.get('phone', 'unknown')
            country = account_info.get('country', 'XX')
            filename = f"session_{phone}_{country}_{timestamp}.session"
            
            # Create caption with account details
            caption = f"""
📱 **Session Backup**
Phone: {phone}
Country: {country}
Username: {account_info.get('username', 'N/A')}
Creation Year: {account_info.get('creation_year', 'N/A')}
Backup Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
User ID: {account_info.get('user_id', 'N/A')}
            """.strip()
            
            # Send file to channel
            message = await self.client.send_file(
                self.backup_channel_id,
                session_file_path,
                caption=caption,
                attributes=[DocumentAttributeFilename(filename)]
            )
            
            return {
                'success': True,
                'message_id': message.id,
                'filename': filename,
                'backup_time': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error backing up session to channel: {e}")
            return {'success': False, 'error': str(e)}
    
    async def backup_account_data_to_channel(self, account_data: Dict[str, Any]) -> Dict[str, Any]:
        """Backup account data as text to channel"""
        try:
            if not self.client:
                await self.initialize()
            
            # Format account data
            data_text = f"""
🔐 **Account Data Backup**

📱 Phone: {account_data.get('phone', 'N/A')}
👤 Username: {account_data.get('username', 'N/A')}
🌍 Country: {account_data.get('country', 'N/A')}
📅 Creation Year: {account_data.get('creation_year', 'N/A')}
✅ Verification Status: {account_data.get('verification_status', 'N/A')}
💰 Price: ${account_data.get('price', 'N/A')}
📊 Quality Score: {account_data.get('quality_score', 'N/A')}
🔒 Session Data: {account_data.get('session_data', 'N/A')[:100]}...

⏰ Backup Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👤 User ID: {account_data.get('user_id', 'N/A')}
            """.strip()
            
            message = await self.client.send_message(
                self.backup_channel_id,
                data_text
            )
            
            return {
                'success': True,
                'message_id': message.id,
                'backup_time': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error backing up account data to channel: {e}")
            return {'success': False, 'error': str(e)}
    
    async def bulk_backup_sessions_to_channel(self, session_files: list) -> Dict[str, Any]:
        """Backup multiple session files to channel"""
        try:
            results = {
                'total': len(session_files),
                'successful': 0,
                'failed': 0,
                'errors': []
            }
            
            for session_info in session_files:
                result = await self.backup_session_to_channel(
                    session_info['file_path'],
                    session_info['account_info']
                )
                
                if result['success']:
                    results['successful'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(result.get('error', 'Unknown error'))
                
                # Small delay to avoid rate limits
                await asyncio.sleep(1)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in bulk backup to channel: {e}")
            return {'success': False, 'error': str(e)}
    
    async def send_backup_summary_to_channel(self, backup_stats: Dict[str, Any]) -> Dict[str, Any]:
        """Send backup summary to channel"""
        try:
            if not self.client:
                await self.initialize()
            
            summary_text = f"""
📊 **Daily Backup Summary**

📅 Date: {datetime.now().strftime('%Y-%m-%d')}
📁 Total Sessions Backed Up: {backup_stats.get('total_sessions', 0)}
✅ Successful Backups: {backup_stats.get('successful', 0)}
❌ Failed Backups: {backup_stats.get('failed', 0)}
💾 Total Size: {backup_stats.get('total_size_mb', 0):.2f} MB
⏰ Backup Time: {datetime.now().strftime('%H:%M:%S')}

🔐 All session files are stored unencrypted for easy access.
            """.strip()
            
            message = await self.client.send_message(
                self.backup_channel_id,
                summary_text
            )
            
            return {
                'success': True,
                'message_id': message.id
            }
            
        except Exception as e:
            logger.error(f"Error sending backup summary to channel: {e}")
            return {'success': False, 'error': str(e)}
    
    async def close(self):
        """Close Telegram client"""
        if self.client:
            await self.client.disconnect()