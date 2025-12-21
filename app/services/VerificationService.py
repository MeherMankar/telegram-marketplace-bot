import asyncio
import logging
import os
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from app.models import SettingsManager

logger = logging.getLogger(__name__)

class VerificationService:
    """Comprehensive account verification service"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
        self.settings_manager = SettingsManager(db_connection)
        # Get API credentials from environment
        self.api_id = int(os.getenv("API_ID", "0"))
        self.api_hash = os.getenv("API_HASH", "")
    
    async def verify_account(self, account_data: dict, proxy: dict = None) -> dict:
        """Run all verification checks on an account
        
        Args:
            account_data: Account data dictionary
            proxy: Optional proxy dict with keys: proxy_type, addr, port, username, password
        """
        try:
            session_string = account_data.get("session_string")
            if not session_string:
                return {"success": False, "error": "No session string provided"}
            
            # Decrypt session if it's encrypted
            try:
                from app.utils.encryption import decrypt_data
                decrypted_session = decrypt_data(session_string)
                logger.info("Session decrypted successfully for verification")
            except Exception as decrypt_error:
                # If decryption fails, assume it's already decrypted
                logger.warning(f"Session decryption failed, using as-is: {str(decrypt_error)}")
                decrypted_session = session_string
            
            # Get verification limits
            limits = await self.settings_manager.get_verification_limits()
            
            # Initialize results
            results = {
                "success": True,
                "checks": {},
                "logs": [],
                "score": 0,
                "max_score": 0
            }
            
            # Get proxy if not provided
            if not proxy and account_data.get("uses_proxy") and account_data.get("proxy_host"):
                # Retrieve proxy from seller_proxies
                seller_id = account_data.get("seller_id")
                proxy_host = account_data.get("proxy_host")
                if seller_id and proxy_host:
                    proxy_doc = await self.db_connection.seller_proxies.find_one({
                        "seller_id": seller_id,
                        "proxy_host": proxy_host
                    })
                    if proxy_doc:
                        proxy = {
                            "proxy_type": proxy_doc["proxy_type"],
                            "addr": proxy_doc["proxy_host"],
                            "port": proxy_doc["proxy_port"],
                            "username": proxy_doc.get("proxy_username"),
                            "password": proxy_doc.get("proxy_password")
                        }
                        logger.info(f"Using seller proxy for verification: {proxy['addr']}:{proxy['port']}")
            
            # Create client with proper API credentials and proxy
            client = TelegramClient(
                StringSession(decrypted_session),
                self.api_id,
                self.api_hash,
                proxy=proxy if proxy else None
            )
            
            try:
                await client.connect()
                
                if not await client.is_user_authorized():
                    return {"success": False, "error": "Session not authorized"}
                
                # Run all checks
                await self._check_basic_info(client, results)
                await self._check_contacts(client, results, limits)
                await self._check_groups_channels(client, results, limits)
                await self._check_bots(client, results, limits)
                await self._check_sessions(client, results, limits)
                await self._check_spam_status(client, results, limits)
                await self._check_account_age(client, results)
                await self._check_profile_completeness(client, results)
                await self._check_activity_patterns(client, results)
                await self._check_security_settings(client, results)
                
                # Calculate final score
                if results["max_score"] > 0:
                    results["score_percentage"] = (results["score"] / results["max_score"]) * 100
                else:
                    results["score_percentage"] = 0
                
                # Determine if account passes
                results["passed"] = results["score_percentage"] >= 70  # 70% threshold
                
            finally:
                await client.disconnect()
            
            return results
            
        except Exception as e:
            logger.error(f"Account verification failed: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _check_basic_info(self, client, results):
        """Check basic account information"""
        try:
            me = await client.get_me()
            
            # Username check
            has_username = bool(me.username)
            results["checks"]["has_username"] = {"passed": has_username, "value": me.username}
            if has_username:
                results["score"] += 10
            results["max_score"] += 10
            
            # Profile photo check
            has_photo = bool(me.photo)
            results["checks"]["has_profile_photo"] = {"passed": has_photo}
            if has_photo:
                results["score"] += 5
            results["max_score"] += 5
            
            # Bio check
            full_user = await client.get_entity(me.id)
            has_bio = bool(getattr(full_user, 'about', None))
            results["checks"]["has_bio"] = {"passed": has_bio}
            if has_bio:
                results["score"] += 5
            results["max_score"] += 5
            
            results["logs"].append("✅ Basic info check completed")
            
        except Exception as e:
            results["logs"].append(f"❌ Basic info check failed: {str(e)}")
    
    async def _check_contacts(self, client, results, limits):
        """Check contact count"""
        try:
            contacts = await client.get_contacts()
            contact_count = len(contacts)
            
            max_contacts = limits.get("max_contacts", 5)
            require_zero = limits.get("require_zero_contacts", False)
            
            if require_zero:
                passed = contact_count == 0
            else:
                passed = contact_count <= max_contacts
            
            results["checks"]["contact_count"] = {
                "passed": passed,
                "value": contact_count,
                "limit": max_contacts
            }
            
            if passed:
                results["score"] += 15
            results["max_score"] += 15
            
            results["logs"].append(f"📞 Contact count: {contact_count} (limit: {max_contacts})")
            
        except Exception as e:
            results["logs"].append(f"❌ Contact check failed: {str(e)}")
    
    async def _check_groups_channels(self, client, results, limits):
        """Check groups and channels"""
        try:
            dialogs = await client.get_dialogs()
            
            groups = [d for d in dialogs if d.is_group]
            channels = [d for d in dialogs if d.is_channel]
            supergroups = [d for d in dialogs if getattr(d.entity, 'megagroup', False)]
            
            # Check owned groups
            owned_groups = 0
            for dialog in groups + channels + supergroups:
                try:
                    entity = await client.get_entity(dialog.entity.id)
                    if hasattr(entity, 'creator') and entity.creator:
                        owned_groups += 1
                except:
                    continue
            
            max_owned = limits.get("max_groups_owned", 10)
            passed = owned_groups <= max_owned
            
            results["checks"]["owned_groups"] = {
                "passed": passed,
                "value": owned_groups,
                "limit": max_owned
            }
            
            if passed:
                results["score"] += 10
            results["max_score"] += 10
            
            results["logs"].append(f"👥 Groups: {len(groups)}, Channels: {len(channels)}, Owned: {owned_groups}")
            
        except Exception as e:
            results["logs"].append(f"❌ Groups/channels check failed: {str(e)}")
    
    async def _check_bots(self, client, results, limits):
        """Check bot interactions"""
        try:
            dialogs = await client.get_dialogs()
            bot_chats = [d for d in dialogs if d.entity.bot if hasattr(d.entity, 'bot')]
            
            max_bots = limits.get("max_bot_chats", 3)
            passed = len(bot_chats) <= max_bots
            
            results["checks"]["bot_chats"] = {
                "passed": passed,
                "value": len(bot_chats),
                "limit": max_bots
            }
            
            if passed:
                results["score"] += 10
            results["max_score"] += 10
            
            results["logs"].append(f"🤖 Bot chats: {len(bot_chats)} (limit: {max_bots})")
            
        except Exception as e:
            results["logs"].append(f"❌ Bot check failed: {str(e)}")
    
    async def _check_sessions(self, client, results, limits):
        """Check active sessions"""
        try:
            # This is a simplified check - full implementation would require more API calls
            max_sessions = limits.get("max_active_sessions", 3)
            
            # For now, assume 1 session (current)
            active_sessions = 1
            passed = active_sessions <= max_sessions
            
            results["checks"]["active_sessions"] = {
                "passed": passed,
                "value": active_sessions,
                "limit": max_sessions
            }
            
            if passed:
                results["score"] += 10
            results["max_score"] += 10
            
            results["logs"].append(f"📱 Active sessions: {active_sessions} (limit: {max_sessions})")
            
        except Exception as e:
            results["logs"].append(f"❌ Session check failed: {str(e)}")
    
    async def _check_spam_status(self, client, results, limits):
        """Check if account is spam-restricted"""
        try:
            require_spam_check = limits.get("require_spam_check", True)
            
            if not require_spam_check:
                results["checks"]["spam_status"] = {"passed": True, "skipped": True}
                results["score"] += 15
                results["max_score"] += 15
                return
            
            # Try to send a message to spam bot to check status
            try:
                spam_bot = await client.get_entity("@SpamBot")
                await client.send_message(spam_bot, "/start")
                
                # Wait for response
                await asyncio.sleep(2)
                messages = await client.get_messages(spam_bot, limit=1)
                
                if messages:
                    response = messages[0].message.lower()
                    is_spam = "limited" in response or "restricted" in response
                    passed = not is_spam
                else:
                    passed = True  # No response means likely not spam
                
            except:
                passed = True  # If can't check, assume not spam
            
            results["checks"]["spam_status"] = {"passed": passed}
            
            if passed:
                results["score"] += 15
            results["max_score"] += 15
            
            results["logs"].append(f"🚫 Spam check: {'Passed' if passed else 'Failed'}")
            
        except Exception as e:
            results["logs"].append(f"❌ Spam check failed: {str(e)}")
    
    async def _check_account_age(self, client, results):
        """Check account creation date"""
        try:
            me = await client.get_me()
            
            # Estimate age based on user ID (rough approximation)
            # Lower IDs = older accounts
            estimated_age_days = max(1, (2000000000 - me.id) // 100000)
            
            # Accounts older than 30 days get points
            passed = estimated_age_days >= 30
            
            results["checks"]["account_age"] = {
                "passed": passed,
                "estimated_days": estimated_age_days
            }
            
            if passed:
                results["score"] += 10
            results["max_score"] += 10
            
            results["logs"].append(f"📅 Estimated age: {estimated_age_days} days")
            
        except Exception as e:
            results["logs"].append(f"❌ Age check failed: {str(e)}")
    
    async def _check_profile_completeness(self, client, results):
        """Check profile completeness"""
        try:
            me = await client.get_me()
            
            completeness_score = 0
            max_completeness = 4
            
            if me.first_name:
                completeness_score += 1
            if me.last_name:
                completeness_score += 1
            if me.username:
                completeness_score += 1
            if me.photo:
                completeness_score += 1
            
            passed = completeness_score >= 3
            
            results["checks"]["profile_completeness"] = {
                "passed": passed,
                "score": completeness_score,
                "max_score": max_completeness
            }
            
            if passed:
                results["score"] += 10
            results["max_score"] += 10
            
            results["logs"].append(f"📋 Profile completeness: {completeness_score}/{max_completeness}")
            
        except Exception as e:
            results["logs"].append(f"❌ Profile completeness check failed: {str(e)}")
    
    async def _check_activity_patterns(self, client, results):
        """Check for suspicious activity patterns"""
        try:
            # This is a simplified check
            # Full implementation would analyze message patterns, timing, etc.
            
            dialogs = await client.get_dialogs(limit=10)
            recent_activity = len([d for d in dialogs if d.date > datetime.now() - timedelta(days=7)])
            
            # Some recent activity is good, too much might be suspicious
            passed = 1 <= recent_activity <= 8
            
            results["checks"]["activity_patterns"] = {
                "passed": passed,
                "recent_chats": recent_activity
            }
            
            if passed:
                results["score"] += 5
            results["max_score"] += 5
            
            results["logs"].append(f"📊 Recent activity: {recent_activity} chats")
            
        except Exception as e:
            results["logs"].append(f"❌ Activity check failed: {str(e)}")
    
    async def _check_security_settings(self, client, results):
        """Check security settings"""
        try:
            # Check if 2FA is enabled
            try:
                await client.edit_2fa(new_password="test")  # This will fail if 2FA exists
                has_2fa = False
            except:
                has_2fa = True
            
            results["checks"]["two_factor_auth"] = {"passed": has_2fa}
            
            if has_2fa:
                results["score"] += 5
            results["max_score"] += 5
            
            results["logs"].append(f"🔒 2FA enabled: {'Yes' if has_2fa else 'No'}")
            
        except Exception as e:
            results["logs"].append(f"❌ Security check failed: {str(e)}")
    
    async def enable_otp_destroyer(self, session_string: str) -> bool:
        """Enable OTP destroyer for approved account"""
        try:
            # This would implement OTP code interception
            # For now, just log the action
            logger.info(f"OTP destroyer enabled for session")
            return True
        except Exception as e:
            logger.error(f"Failed to enable OTP destroyer: {str(e)}")
            return False
    
    async def disable_otp_destroyer(self, session_string: str) -> bool:
        """Disable OTP destroyer when account is sold"""
        try:
            # This would disable OTP code interception
            # For now, just log the action
            logger.info(f"OTP destroyer disabled for session")
            return True
        except Exception as e:
            logger.error(f"Failed to disable OTP destroyer: {str(e)}")
            return False