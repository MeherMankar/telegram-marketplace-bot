import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from telethon import TelegramClient

logger = logging.getLogger(__name__)

class PaymentVerificationService:
    def __init__(self, db_connection, admin_bot_client):
        self.db = db_connection
        self.admin_client = admin_bot_client
    
    async def submit_payment_proof(self, user_id: int, amount: float, 
                                 payment_method: str, proof_file_id: str = None, 
                                 proof_message: str = None) -> Dict[str, Any]:
        """Submit payment proof for admin verification"""
        try:
            # Create payment verification request
            verification_request = {
                'user_id': user_id,
                'amount': amount,
                'payment_method': payment_method,
                'proof_file_id': proof_file_id,
                'proof_message': proof_message,
                'status': 'pending',
                'submitted_at': datetime.utcnow(),
                'verified_by': None,
                'verified_at': None
            }
            
            result = await self.db.payment_verifications.insert_one(verification_request)
            verification_id = str(result.inserted_id)
            
            # Send to admin for review
            await self._send_to_admin_for_review(verification_id, verification_request)
            
            return {
                'success': True,
                'verification_id': verification_id,
                'status': 'pending',
                'message': 'Payment proof submitted. Admin will review and add balance within 24 hours.'
            }
            
        except Exception as e:
            logger.error(f"Error submitting payment proof: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _send_to_admin_for_review(self, verification_id: str, request_data: Dict[str, Any]):
        """Send payment proof to admin bot for review"""
        try:
            # Get user info
            user = await self.db.users.find_one({'user_id': request_data['user_id']})
            username = user.get('username', f"User{request_data['user_id']}") if user else 'Unknown'
            
            # Format admin message
            admin_message = f"""
💰 **Payment Verification Request**

👤 **User:** {username} (ID: {request_data['user_id']})
💵 **Amount:** ${request_data['amount']}
💳 **Method:** {request_data['payment_method']}
📅 **Submitted:** {request_data['submitted_at'].strftime('%Y-%m-%d %H:%M:%S')}

📝 **Message:** {request_data.get('proof_message', 'No message')}

**Verification ID:** `{verification_id}`
            """.strip()
            
            # Create admin keyboard
            from ..utils.keyboards import create_payment_verification_keyboard
            keyboard = create_payment_verification_keyboard(verification_id)
            
            # Send message to admin
            if request_data.get('proof_file_id'):
                # Forward the proof image/document
                await self.admin_client.send_file(
                    entity='me',  # Admin chat
                    file=request_data['proof_file_id'],
                    caption=admin_message,
                    buttons=keyboard
                )
            else:
                # Send text message only
                await self.admin_client.send_message(
                    entity='me',
                    message=admin_message,
                    buttons=keyboard
                )
                
        except Exception as e:
            logger.error(f"Error sending to admin: {e}")
    
    async def approve_payment(self, admin_id: int, verification_id: str) -> Dict[str, Any]:
        """Admin approves payment and adds balance"""
        try:
            # Get verification request
            verification = await self.db.payment_verifications.find_one({'_id': verification_id})
            if not verification:
                return {'success': False, 'error': 'Verification request not found'}
            
            if verification['status'] != 'pending':
                return {'success': False, 'error': 'Payment already processed'}
            
            # Update verification status
            await self.db.payment_verifications.update_one(
                {'_id': verification_id},
                {
                    '$set': {
                        'status': 'approved',
                        'verified_by': admin_id,
                        'verified_at': datetime.utcnow()
                    }
                }
            )
            
            # Add balance to user
            await self.db.users.update_one(
                {'user_id': verification['user_id']},
                {
                    '$inc': {'balance': verification['amount']},
                    '$push': {
                        'balance_history': {
                            'amount': verification['amount'],
                            'type': 'deposit',
                            'method': verification['payment_method'],
                            'verification_id': verification_id,
                            'timestamp': datetime.utcnow()
                        }
                    }
                }
            )
            
            # Notify user
            await self._notify_user_payment_approved(verification)
            
            return {
                'success': True,
                'message': f"Payment approved. ${verification['amount']} added to user balance.",
                'user_id': verification['user_id'],
                'amount': verification['amount']
            }
            
        except Exception as e:
            logger.error(f"Error approving payment: {e}")
            return {'success': False, 'error': str(e)}
    
    async def reject_payment(self, admin_id: int, verification_id: str, reason: str = None) -> Dict[str, Any]:
        """Admin rejects payment"""
        try:
            # Get verification request
            verification = await self.db.payment_verifications.find_one({'_id': verification_id})
            if not verification:
                return {'success': False, 'error': 'Verification request not found'}
            
            if verification['status'] != 'pending':
                return {'success': False, 'error': 'Payment already processed'}
            
            # Update verification status
            await self.db.payment_verifications.update_one(
                {'_id': verification_id},
                {
                    '$set': {
                        'status': 'rejected',
                        'verified_by': admin_id,
                        'verified_at': datetime.utcnow(),
                        'rejection_reason': reason
                    }
                }
            )
            
            # Notify user
            await self._notify_user_payment_rejected(verification, reason)
            
            return {
                'success': True,
                'message': f"Payment rejected. User notified.",
                'user_id': verification['user_id']
            }
            
        except Exception as e:
            logger.error(f"Error rejecting payment: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _notify_user_payment_approved(self, verification: Dict[str, Any]):
        """Notify user that payment was approved"""
        try:
            # This would be implemented in the buyer bot
            # For now, we'll store a notification
            await self.db.user_notifications.insert_one({
                'user_id': verification['user_id'],
                'type': 'payment_approved',
                'message': f"✅ Payment approved! ${verification['amount']} added to your balance.",
                'amount': verification['amount'],
                'created_at': datetime.utcnow(),
                'read': False
            })
            
        except Exception as e:
            logger.error(f"Error notifying user: {e}")
    
    async def _notify_user_payment_rejected(self, verification: Dict[str, Any], reason: str = None):
        """Notify user that payment was rejected"""
        try:
            message = f"❌ Payment rejected."
            if reason:
                message += f" Reason: {reason}"
            message += " Please contact support if you believe this is an error."
            
            await self.db.user_notifications.insert_one({
                'user_id': verification['user_id'],
                'type': 'payment_rejected',
                'message': message,
                'amount': verification['amount'],
                'reason': reason,
                'created_at': datetime.utcnow(),
                'read': False
            })
            
        except Exception as e:
            logger.error(f"Error notifying user: {e}")
    
    async def get_pending_verifications(self) -> list:
        """Get all pending payment verifications for admin"""
        try:
            verifications = await self.db.payment_verifications.find({
                'status': 'pending'
            }).sort('submitted_at', 1).to_list(None)
            
            return verifications
            
        except Exception as e:
            logger.error(f"Error getting pending verifications: {e}")
            return []
    
    async def get_user_balance(self, user_id: int) -> Dict[str, Any]:
        """Get user's current balance"""
        try:
            user = await self.db.users.find_one({'user_id': user_id})
            if not user:
                return {'success': False, 'error': 'User not found'}
            
            return {
                'success': True,
                'balance': user.get('balance', 0),
                'balance_history': user.get('balance_history', [])
            }
            
        except Exception as e:
            logger.error(f"Error getting user balance: {e}")
            return {'success': False, 'error': str(e)}