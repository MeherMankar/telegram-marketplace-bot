import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import random
import string

logger = logging.getLogger(__name__)

class MarketingService:
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def create_campaign(self, admin_id: int, name: str, campaign_type: str,
                            target_audience: str, discount_percent: float = 0,
                            start_date: datetime = None, end_date: datetime = None) -> Dict[str, Any]:
        """Create a new marketing campaign"""
        try:
            campaign = {
                'name': name,
                'type': campaign_type,  # 'discount', 'promotion', 'referral'
                'target_audience': target_audience,  # 'all', 'sellers', 'buyers', 'new_users'
                'discount_percent': discount_percent,
                'start_date': start_date or datetime.utcnow(),
                'end_date': end_date or (datetime.utcnow() + timedelta(days=7)),
                'created_by': admin_id,
                'created_at': datetime.utcnow(),
                'status': 'active',
                'metrics': {
                    'views': 0,
                    'clicks': 0,
                    'conversions': 0,
                    'revenue_generated': 0
                }
            }
            
            result = await self.db.marketing_campaigns.insert_one(campaign)
            campaign_id = str(result.inserted_id)
            
            return {
                'success': True,
                'campaign_id': campaign_id,
                'status': 'active'
            }
            
        except Exception as e:
            logger.error(f"Error creating campaign: {e}")
            return {'success': False, 'error': str(e)}
    
    async def create_discount_code(self, admin_id: int, code: str = None, 
                                 discount_percent: float = 10, max_uses: int = 100,
                                 valid_until: datetime = None) -> Dict[str, Any]:
        """Create a discount code"""
        try:
            if not code:
                code = self._generate_discount_code()
            
            # Check if code already exists
            existing = await self.db.discount_codes.find_one({'code': code})
            if existing:
                return {'success': False, 'error': 'Discount code already exists'}
            
            discount_code = {
                'code': code.upper(),
                'discount_percent': discount_percent,
                'max_uses': max_uses,
                'current_uses': 0,
                'valid_until': valid_until or (datetime.utcnow() + timedelta(days=30)),
                'created_by': admin_id,
                'created_at': datetime.utcnow(),
                'is_active': True,
                'usage_history': []
            }
            
            await self.db.discount_codes.insert_one(discount_code)
            
            return {
                'success': True,
                'code': code.upper(),
                'discount_percent': discount_percent,
                'valid_until': discount_code['valid_until'].isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating discount code: {e}")
            return {'success': False, 'error': str(e)}
    
    async def apply_discount_code(self, user_id: int, code: str, 
                                purchase_amount: float) -> Dict[str, Any]:
        """Apply a discount code to a purchase"""
        try:
            discount_code = await self.db.discount_codes.find_one({
                'code': code.upper(),
                'is_active': True,
                'valid_until': {'$gte': datetime.utcnow()}
            })
            
            if not discount_code:
                return {'success': False, 'error': 'Invalid or expired discount code'}
            
            if discount_code['current_uses'] >= discount_code['max_uses']:
                return {'success': False, 'error': 'Discount code usage limit reached'}
            
            # Check if user already used this code
            if any(usage['user_id'] == user_id for usage in discount_code['usage_history']):
                return {'success': False, 'error': 'You have already used this discount code'}
            
            # Calculate discount
            discount_amount = purchase_amount * (discount_code['discount_percent'] / 100)
            final_amount = purchase_amount - discount_amount
            
            # Update usage
            await self.db.discount_codes.update_one(
                {'_id': discount_code['_id']},
                {
                    '$inc': {'current_uses': 1},
                    '$push': {
                        'usage_history': {
                            'user_id': user_id,
                            'used_at': datetime.utcnow(),
                            'original_amount': purchase_amount,
                            'discount_amount': discount_amount
                        }
                    }
                }
            )
            
            return {
                'success': True,
                'original_amount': purchase_amount,
                'discount_amount': round(discount_amount, 2),
                'final_amount': round(final_amount, 2),
                'discount_percent': discount_code['discount_percent']
            }
            
        except Exception as e:
            logger.error(f"Error applying discount code: {e}")
            return {'success': False, 'error': str(e)}
    
    async def send_promotional_message(self, campaign_id: str, user_ids: List[int], 
                                     message: str) -> Dict[str, Any]:
        """Send promotional messages to users"""
        try:
            sent_count = 0
            failed_count = 0
            
            for user_id in user_ids:
                try:
                    # Store message for delivery via bot
                    await self.db.promotional_messages.insert_one({
                        'campaign_id': campaign_id,
                        'user_id': user_id,
                        'message': message,
                        'status': 'pending',
                        'created_at': datetime.utcnow()
                    })
                    sent_count += 1
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Failed to queue message for user {user_id}: {e}")
            
            # Update campaign metrics
            await self.db.marketing_campaigns.update_one(
                {'_id': campaign_id},
                {'$inc': {'metrics.views': sent_count}}
            )
            
            return {
                'success': True,
                'sent_count': sent_count,
                'failed_count': failed_count,
                'total_targeted': len(user_ids)
            }
            
        except Exception as e:
            logger.error(f"Error sending promotional messages: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_campaign_analytics(self, campaign_id: str) -> Dict[str, Any]:
        """Get analytics for a specific campaign"""
        try:
            campaign = await self.db.marketing_campaigns.find_one({'_id': campaign_id})
            if not campaign:
                return {'success': False, 'error': 'Campaign not found'}
            
            # Get detailed metrics
            messages_sent = await self.db.promotional_messages.count_documents({
                'campaign_id': campaign_id
            })
            
            messages_delivered = await self.db.promotional_messages.count_documents({
                'campaign_id': campaign_id,
                'status': 'delivered'
            })
            
            # Calculate ROI if it's a discount campaign
            roi = 0
            if campaign['metrics']['revenue_generated'] > 0:
                campaign_cost = messages_sent * 0.01  # Assume $0.01 per message
                roi = ((campaign['metrics']['revenue_generated'] - campaign_cost) / campaign_cost) * 100
            
            return {
                'success': True,
                'campaign_name': campaign['name'],
                'campaign_type': campaign['type'],
                'status': campaign['status'],
                'start_date': campaign['start_date'].isoformat(),
                'end_date': campaign['end_date'].isoformat(),
                'metrics': {
                    'messages_sent': messages_sent,
                    'messages_delivered': messages_delivered,
                    'delivery_rate': (messages_delivered / messages_sent * 100) if messages_sent > 0 else 0,
                    'clicks': campaign['metrics']['clicks'],
                    'conversions': campaign['metrics']['conversions'],
                    'conversion_rate': (campaign['metrics']['conversions'] / messages_sent * 100) if messages_sent > 0 else 0,
                    'revenue_generated': campaign['metrics']['revenue_generated'],
                    'roi_percent': round(roi, 2)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting campaign analytics: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_user_segments(self) -> Dict[str, Any]:
        """Get user segments for targeted marketing"""
        try:
            # Active sellers (uploaded in last 30 days)
            active_sellers = await self.db.accounts.distinct('user_id', {
                'upload_date': {'$gte': datetime.utcnow() - timedelta(days=30)}
            })
            
            # Active buyers (purchased in last 30 days)
            active_buyers = await self.db.transactions.distinct('buyer_id', {
                'created_at': {'$gte': datetime.utcnow() - timedelta(days=30)}
            })
            
            # New users (registered in last 7 days)
            new_users = await self.db.users.find({
                'created_at': {'$gte': datetime.utcnow() - timedelta(days=7)}
            }).to_list(None)
            
            # Inactive users (no activity in 30 days)
            all_users = await self.db.users.find({}).to_list(None)
            inactive_users = []
            
            for user in all_users:
                user_id = user['user_id']
                
                # Check recent activity
                recent_upload = await self.db.accounts.find_one({
                    'user_id': user_id,
                    'upload_date': {'$gte': datetime.utcnow() - timedelta(days=30)}
                })
                
                recent_purchase = await self.db.transactions.find_one({
                    'buyer_id': user_id,
                    'created_at': {'$gte': datetime.utcnow() - timedelta(days=30)}
                })
                
                if not recent_upload and not recent_purchase:
                    inactive_users.append(user_id)
            
            # High-value customers (spent > $100)
            high_value_customers = await self.db.transactions.aggregate([
                {
                    '$group': {
                        '_id': '$buyer_id',
                        'total_spent': {'$sum': '$amount'}
                    }
                },
                {
                    '$match': {'total_spent': {'$gte': 100}}
                }
            ]).to_list(None)
            
            return {
                'active_sellers': {
                    'count': len(active_sellers),
                    'user_ids': active_sellers
                },
                'active_buyers': {
                    'count': len(active_buyers),
                    'user_ids': active_buyers
                },
                'new_users': {
                    'count': len(new_users),
                    'user_ids': [user['user_id'] for user in new_users]
                },
                'inactive_users': {
                    'count': len(inactive_users),
                    'user_ids': inactive_users
                },
                'high_value_customers': {
                    'count': len(high_value_customers),
                    'user_ids': [customer['_id'] for customer in high_value_customers]
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting user segments: {e}")
            return {}
    
    async def schedule_campaign(self, campaign_id: str, send_time: datetime) -> Dict[str, Any]:
        """Schedule a campaign for future execution"""
        try:
            await self.db.marketing_campaigns.update_one(
                {'_id': campaign_id},
                {
                    '$set': {
                        'scheduled_time': send_time,
                        'status': 'scheduled'
                    }
                }
            )
            
            return {
                'success': True,
                'scheduled_time': send_time.isoformat(),
                'status': 'scheduled'
            }
            
        except Exception as e:
            logger.error(f"Error scheduling campaign: {e}")
            return {'success': False, 'error': str(e)}
    
    def _generate_discount_code(self, length: int = 8) -> str:
        """Generate a random discount code"""
        characters = string.ascii_uppercase + string.digits
        return ''.join(random.choice(characters) for _ in range(length))
    
    async def get_pending_promotional_messages(self, user_id: int) -> List[Dict[str, Any]]:
        """Get pending promotional messages for a user"""
        try:
            messages = await self.db.promotional_messages.find({
                'user_id': user_id,
                'status': 'pending'
            }).to_list(None)
            
            # Mark as delivered
            if messages:
                message_ids = [msg['_id'] for msg in messages]
                await self.db.promotional_messages.update_many(
                    {'_id': {'$in': message_ids}},
                    {'$set': {'status': 'delivered', 'delivered_at': datetime.utcnow()}}
                )
            
            return [
                {
                    'message': msg['message'],
                    'campaign_id': msg['campaign_id'],
                    'created_at': msg['created_at'].isoformat()
                }
                for msg in messages
            ]
            
        except Exception as e:
            logger.error(f"Error getting promotional messages: {e}")
            return []