import asyncio
import logging
import os
import shutil
import zipfile
from datetime import datetime, timedelta
from typing import Dict, Any
import boto3
from botocore.exceptions import ClientError
from .TelegramBackupService import TelegramBackupService

logger = logging.getLogger(__name__)

class BackupService:
    def __init__(self, db_connection, api_id: int = None, api_hash: str = None):
        self.db = db_connection
        self.backup_dir = 'backups'
        self.s3_client = None
        self.telegram_backup = None
        self._init_s3()
        self._init_telegram_backup(api_id, api_hash)
    
    def _init_s3(self):
        """Initialize S3 client for cloud backups"""
        try:
            aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
            aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
            aws_region = os.getenv('AWS_REGION', 'us-east-1')
            
            if aws_access_key and aws_secret_key:
                self.s3_client = boto3.client(
                    's3',
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                    region_name=aws_region
                )
                logger.info("S3 client initialized for cloud backups")
        except Exception as e:
            logger.warning(f"Could not initialize S3 client: {e}")
    
    def _init_telegram_backup(self, api_id: int, api_hash: str):
        """Initialize Telegram backup service"""
        try:
            backup_channel_id = os.getenv('BACKUP_CHANNEL_ID')
            if backup_channel_id and api_id and api_hash:
                self.telegram_backup = TelegramBackupService(
                    api_id, api_hash, int(backup_channel_id)
                )
                logger.info("Telegram backup service initialized")
        except Exception as e:
            logger.warning(f"Could not initialize Telegram backup: {e}")
    
    async def create_database_backup(self) -> Dict[str, Any]:
        """Create a backup of the database"""
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"{self.backup_dir}/db_backup_{timestamp}.json"
            
            # Export collections
            collections = ['users', 'accounts', 'listings', 'transactions', 'admin_actions']
            backup_data = {}
            
            for collection_name in collections:
                collection = getattr(self.db, collection_name)
                documents = await collection.find({}).to_list(None)
                
                # Convert ObjectId to string for JSON serialization
                for doc in documents:
                    if '_id' in doc:
                        doc['_id'] = str(doc['_id'])
                
                backup_data[collection_name] = documents
            
            # Save to file
            import json
            with open(backup_file, 'w') as f:
                json.dump(backup_data, f, default=str, indent=2)
            
            # Compress backup
            zip_file = f"{backup_file}.zip"
            with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(backup_file, os.path.basename(backup_file))
            
            # Remove uncompressed file
            os.remove(backup_file)
            
            # Upload to S3 if configured
            s3_url = None
            if self.s3_client:
                s3_url = await self._upload_to_s3(zip_file)
            
            file_size = os.path.getsize(zip_file)
            
            return {
                'success': True,
                'backup_file': zip_file,
                's3_url': s3_url,
                'file_size': file_size,
                'timestamp': timestamp,
                'collections_backed_up': len(collections)
            }
            
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def backup_session_files(self) -> Dict[str, Any]:
        """Backup session files to cloud storage and Telegram channel"""
        try:
            session_dir = 'storage/sessions'
            if not os.path.exists(session_dir):
                return {'success': True, 'message': 'No session files to backup'}
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"{self.backup_dir}/sessions_backup_{timestamp}.zip"
            
            # Create zip archive of session files
            session_files = []
            total_size = 0
            
            with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(session_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arc_name = os.path.relpath(file_path, session_dir)
                        zf.write(file_path, arc_name)
                        
                        # Collect for Telegram backup
                        if file.endswith('.session'):
                            file_size = os.path.getsize(file_path)
                            total_size += file_size
                            
                            # Get account info from database
                            account_info = await self._get_account_info_by_session(file)
                            session_files.append({
                                'file_path': file_path,
                                'account_info': account_info
                            })
            
            # Upload to S3 if configured
            s3_url = None
            if self.s3_client:
                s3_url = await self._upload_to_s3(backup_file)
            
            # Backup to Telegram channel if configured
            telegram_result = None
            if self.telegram_backup and session_files:
                telegram_result = await self.telegram_backup.bulk_backup_sessions_to_channel(session_files)
                
                # Send summary to channel
                backup_stats = {
                    'total_sessions': len(session_files),
                    'successful': telegram_result.get('successful', 0),
                    'failed': telegram_result.get('failed', 0),
                    'total_size_mb': total_size / (1024 * 1024)
                }
                await self.telegram_backup.send_backup_summary_to_channel(backup_stats)
            
            file_size = os.path.getsize(backup_file)
            
            return {
                'success': True,
                'backup_file': backup_file,
                's3_url': s3_url,
                'telegram_backup': telegram_result,
                'file_size': file_size,
                'timestamp': timestamp,
                'sessions_backed_up': len(session_files)
            }
            
        except Exception as e:
            logger.error(f"Session files backup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _upload_to_s3(self, file_path: str) -> str:
        """Upload backup file to S3"""
        try:
            bucket_name = os.getenv('S3_BACKUP_BUCKET')
            if not bucket_name:
                return None
            
            file_name = os.path.basename(file_path)
            s3_key = f"backups/{file_name}"
            
            self.s3_client.upload_file(file_path, bucket_name, s3_key)
            
            s3_url = f"s3://{bucket_name}/{s3_key}"
            logger.info(f"Backup uploaded to S3: {s3_url}")
            
            return s3_url
            
        except ClientError as e:
            logger.error(f"S3 upload failed: {e}")
            return None
    
    async def restore_database_backup(self, backup_file: str) -> Dict[str, Any]:
        """Restore database from backup file"""
        try:
            if not os.path.exists(backup_file):
                return {'success': False, 'error': 'Backup file not found'}
            
            # Extract if it's a zip file
            if backup_file.endswith('.zip'):
                with zipfile.ZipFile(backup_file, 'r') as zf:
                    zf.extractall(self.backup_dir)
                    json_file = backup_file.replace('.zip', '')
            else:
                json_file = backup_file
            
            # Load backup data
            import json
            with open(json_file, 'r') as f:
                backup_data = json.load(f)
            
            # Restore collections
            restored_collections = 0
            for collection_name, documents in backup_data.items():
                if documents:
                    collection = getattr(self.db, collection_name)
                    
                    # Clear existing data (optional - be careful!)
                    # await collection.delete_many({})
                    
                    # Insert backup data
                    await collection.insert_many(documents)
                    restored_collections += 1
            
            return {
                'success': True,
                'restored_collections': restored_collections,
                'total_documents': sum(len(docs) for docs in backup_data.values())
            }
            
        except Exception as e:
            logger.error(f"Database restore failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def cleanup_old_backups(self, days_to_keep: int = 7) -> Dict[str, Any]:
        """Remove backup files older than specified days"""
        try:
            if not os.path.exists(self.backup_dir):
                return {'success': True, 'removed_files': 0}
            
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            removed_files = 0
            
            for filename in os.listdir(self.backup_dir):
                file_path = os.path.join(self.backup_dir, filename)
                
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    if file_time < cutoff_date:
                        os.remove(file_path)
                        removed_files += 1
                        logger.info(f"Removed old backup: {filename}")
            
            return {
                'success': True,
                'removed_files': removed_files,
                'cutoff_date': cutoff_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def schedule_automatic_backups(self):
        """Schedule automatic daily backups"""
        while True:
            try:
                # Wait until 2 AM for daily backup
                now = datetime.now()
                next_backup = now.replace(hour=2, minute=0, second=0, microsecond=0)
                
                if next_backup <= now:
                    next_backup += timedelta(days=1)
                
                wait_seconds = (next_backup - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                # Perform backups
                logger.info("Starting scheduled backup...")
                
                db_result = await self.create_database_backup()
                session_result = await self.backup_session_files()
                cleanup_result = await self.cleanup_old_backups()
                
                logger.info(f"Scheduled backup completed: DB={db_result['success']}, Sessions={session_result['success']}, Cleanup={cleanup_result['success']}")
                
            except Exception as e:
                logger.error(f"Scheduled backup error: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour before retry
    
    async def backup_single_session_to_telegram(self, session_file_path: str, 
                                               account_data: Dict[str, Any]) -> Dict[str, Any]:
        """Backup single session file to Telegram channel"""
        try:
            if not self.telegram_backup:
                return {'success': False, 'error': 'Telegram backup not configured'}
            
            # Backup session file
            session_result = await self.telegram_backup.backup_session_to_channel(
                session_file_path, account_data
            )
            
            # Backup account data as text
            data_result = await self.telegram_backup.backup_account_data_to_channel(account_data)
            
            return {
                'success': True,
                'session_backup': session_result,
                'data_backup': data_result
            }
            
        except Exception as e:
            logger.error(f"Single session Telegram backup failed: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _get_account_info_by_session(self, session_filename: str) -> Dict[str, Any]:
        """Get account info from database by session filename"""
        try:
            # Extract phone from filename if possible
            phone = session_filename.replace('.session', '')
            
            account = await self.db.accounts.find_one({'phone': phone})
            if account:
                return {
                    'phone': account.get('phone', 'unknown'),
                    'username': account.get('username'),
                    'country': account.get('country'),
                    'creation_year': account.get('creation_year'),
                    'user_id': account.get('user_id'),
                    'verification_status': account.get('verification_status'),
                    'price': account.get('price'),
                    'quality_score': account.get('quality_score')
                }
            
            return {
                'phone': phone,
                'username': None,
                'country': 'unknown',
                'creation_year': None,
                'user_id': None
            }
            
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {'phone': 'unknown'}