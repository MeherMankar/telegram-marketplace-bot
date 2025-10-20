import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

class SocialService:
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def add_user_rating(self, rater_id: int, rated_user_id: int, 
                            transaction_id: str, rating: int, review: str = "") -> Dict[str, Any]:
        """Add a rating and review for a user"""
        try:
            if rating < 1 or rating > 5:
                return {'success': False, 'error': 'Rating must be between 1 and 5'}
            
            # Check if transaction exists and involves both users
            transaction = await self.db.transactions.find_one({
                '_id': transaction_id,
                '$or': [
                    {'buyer_id': rater_id, 'seller_id': rated_user_id},
                    {'buyer_id': rated_user_id, 'seller_id': rater_id}
                ],
                'status': 'completed'
            })
            
            if not transaction:
                return {'success': False, 'error': 'Invalid transaction or not completed'}
            
            # Check if rating already exists
            existing_rating = await self.db.user_ratings.find_one({
                'rater_id': rater_id,
                'rated_user_id': rated_user_id,
                'transaction_id': transaction_id
            })
            
            if existing_rating:
                return {'success': False, 'error': 'You have already rated this user for this transaction'}
            
            # Add rating
            rating_data = {
                'rater_id': rater_id,
                'rated_user_id': rated_user_id,
                'transaction_id': transaction_id,
                'rating': rating,
                'review': review,
                'created_at': datetime.utcnow(),
                'is_verified': True  # Since it's based on actual transaction
            }
            
            await self.db.user_ratings.insert_one(rating_data)
            
            # Update user's average rating
            await self._update_user_rating_stats(rated_user_id)
            
            return {
                'success': True,
                'rating': rating,
                'review': review,
                'created_at': rating_data['created_at'].isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error adding user rating: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_user_ratings(self, user_id: int, limit: int = 20) -> Dict[str, Any]:
        """Get ratings and reviews for a user"""
        try:
            # Get ratings
            ratings = await self.db.user_ratings.find({
                'rated_user_id': user_id
            }).sort('created_at', -1).limit(limit).to_list(None)
            
            # Get rating statistics
            rating_stats = await self.db.user_ratings.aggregate([
                {'$match': {'rated_user_id': user_id}},
                {
                    '$group': {
                        '_id': None,
                        'total_ratings': {'$sum': 1},
                        'average_rating': {'$avg': '$rating'},
                        'rating_distribution': {
                            '$push': '$rating'
                        }
                    }
                }
            ]).to_list(None)
            
            # Calculate rating distribution
            distribution = defaultdict(int)
            if rating_stats:
                for rating in rating_stats[0]['rating_distribution']:
                    distribution[rating] += 1
            
            # Format ratings for display
            formatted_ratings = []
            for rating in ratings:
                # Get rater info (anonymized)
                rater = await self.db.users.find_one({'user_id': rating['rater_id']})
                rater_name = rater.get('username', f'User{rating["rater_id"]}') if rater else 'Anonymous'
                
                formatted_ratings.append({
                    'rating': rating['rating'],
                    'review': rating['review'],
                    'rater_name': rater_name[:3] + '***',  # Partially anonymize
                    'created_at': rating['created_at'].isoformat(),
                    'is_verified': rating.get('is_verified', False)
                })
            
            stats = rating_stats[0] if rating_stats else {
                'total_ratings': 0,
                'average_rating': 0
            }
            
            return {
                'user_id': user_id,
                'total_ratings': stats['total_ratings'],
                'average_rating': round(stats['average_rating'], 2) if stats['average_rating'] else 0,
                'rating_distribution': dict(distribution),
                'ratings': formatted_ratings
            }
            
        except Exception as e:
            logger.error(f"Error getting user ratings: {e}")
            return {'user_id': user_id, 'total_ratings': 0, 'average_rating': 0, 'ratings': []}
    
    async def calculate_seller_reputation(self, user_id: int) -> Dict[str, Any]:
        """Calculate comprehensive seller reputation score"""
        try:
            # Get seller statistics
            total_accounts = await self.db.accounts.count_documents({'user_id': user_id})
            approved_accounts = await self.db.accounts.count_documents({
                'user_id': user_id,
                'verification_status': 'approved'
            })
            
            # Get sales statistics
            completed_sales = await self.db.transactions.count_documents({
                'seller_id': user_id,
                'status': 'completed'
            })
            
            total_revenue = await self.db.transactions.aggregate([
                {'$match': {'seller_id': user_id, 'status': 'completed'}},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ]).to_list(None)
            
            revenue = total_revenue[0]['total'] if total_revenue else 0
            
            # Get ratings
            ratings_data = await self.get_user_ratings(user_id)
            
            # Calculate reputation score (0-100)
            reputation_score = 0
            
            # Approval rate (30 points max)
            if total_accounts > 0:
                approval_rate = approved_accounts / total_accounts
                reputation_score += approval_rate * 30
            
            # Sales volume (25 points max)
            if completed_sales > 0:
                sales_score = min(completed_sales / 10, 1) * 25  # Max at 10 sales
                reputation_score += sales_score
            
            # Average rating (25 points max)
            if ratings_data['average_rating'] > 0:
                rating_score = (ratings_data['average_rating'] / 5) * 25
                reputation_score += rating_score
            
            # Account age and activity (20 points max)
            user = await self.db.users.find_one({'user_id': user_id})
            if user and user.get('created_at'):
                days_active = (datetime.utcnow() - user['created_at']).days
                activity_score = min(days_active / 30, 1) * 20  # Max at 30 days
                reputation_score += activity_score
            
            # Determine reputation level
            if reputation_score >= 80:
                reputation_level = "Excellent"
                trust_badge = "🏆 Trusted Seller"
            elif reputation_score >= 60:
                reputation_level = "Good"
                trust_badge = "⭐ Verified Seller"
            elif reputation_score >= 40:
                reputation_level = "Average"
                trust_badge = "✅ Active Seller"
            elif reputation_score >= 20:
                reputation_level = "Below Average"
                trust_badge = "🔰 New Seller"
            else:
                reputation_level = "Poor"
                trust_badge = "⚠️ Unverified"
            
            return {
                'user_id': user_id,
                'reputation_score': round(reputation_score, 1),
                'reputation_level': reputation_level,
                'trust_badge': trust_badge,
                'statistics': {
                    'total_accounts_uploaded': total_accounts,
                    'accounts_approved': approved_accounts,
                    'approval_rate': round((approved_accounts / total_accounts * 100) if total_accounts > 0 else 0, 1),
                    'completed_sales': completed_sales,
                    'total_revenue': round(revenue, 2),
                    'average_rating': ratings_data['average_rating'],
                    'total_ratings': ratings_data['total_ratings']
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating seller reputation: {e}")
            return {'user_id': user_id, 'reputation_score': 0, 'reputation_level': 'Unknown'}
    
    async def add_community_feedback(self, user_id: int, feedback_type: str, 
                                   target_id: str, content: str) -> Dict[str, Any]:
        """Add community feedback (report, suggestion, etc.)"""
        try:
            feedback_types = ['report_user', 'report_listing', 'suggestion', 'compliment']
            
            if feedback_type not in feedback_types:
                return {'success': False, 'error': 'Invalid feedback type'}
            
            feedback = {
                'user_id': user_id,
                'feedback_type': feedback_type,
                'target_id': target_id,
                'content': content,
                'status': 'pending',
                'created_at': datetime.utcnow(),
                'reviewed_by': None,
                'reviewed_at': None
            }
            
            result = await self.db.community_feedback.insert_one(feedback)
            feedback_id = str(result.inserted_id)
            
            # Auto-process certain types
            if feedback_type == 'suggestion':
                await self.db.community_feedback.update_one(
                    {'_id': result.inserted_id},
                    {'$set': {'status': 'received'}}
                )
            
            return {
                'success': True,
                'feedback_id': feedback_id,
                'status': 'received' if feedback_type == 'suggestion' else 'pending'
            }
            
        except Exception as e:
            logger.error(f"Error adding community feedback: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_trust_badges(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all trust badges for a user"""
        try:
            badges = []
            
            # Get user data
            user = await self.db.users.find_one({'user_id': user_id})
            if not user:
                return badges
            
            # Account age badge
            if user.get('created_at'):
                days_active = (datetime.utcnow() - user['created_at']).days
                if days_active >= 365:
                    badges.append({
                        'name': 'Veteran Member',
                        'icon': '🎖️',
                        'description': 'Member for over 1 year',
                        'earned_at': user['created_at'].isoformat()
                    })
                elif days_active >= 90:
                    badges.append({
                        'name': 'Established Member',
                        'icon': '📅',
                        'description': 'Member for over 3 months',
                        'earned_at': user['created_at'].isoformat()
                    })
            
            # Verification badges
            user_verification = await self.db.user_verification.find_one({'user_id': user_id})
            if user_verification:
                if user_verification.get('phone_verified'):
                    badges.append({
                        'name': 'Phone Verified',
                        'icon': '📱',
                        'description': 'Phone number verified',
                        'earned_at': user_verification.get('phone_verified_at', datetime.utcnow()).isoformat()
                    })
                
                if user_verification.get('2fa_enabled'):
                    badges.append({
                        'name': 'Security Enhanced',
                        'icon': '🔐',
                        'description': '2FA enabled for extra security',
                        'earned_at': user_verification.get('2fa_enabled_at', datetime.utcnow()).isoformat()
                    })
            
            # Sales badges
            completed_sales = await self.db.transactions.count_documents({
                'seller_id': user_id,
                'status': 'completed'
            })
            
            if completed_sales >= 100:
                badges.append({
                    'name': 'Super Seller',
                    'icon': '🏆',
                    'description': '100+ successful sales',
                    'earned_at': datetime.utcnow().isoformat()
                })
            elif completed_sales >= 50:
                badges.append({
                    'name': 'Top Seller',
                    'icon': '⭐',
                    'description': '50+ successful sales',
                    'earned_at': datetime.utcnow().isoformat()
                })
            elif completed_sales >= 10:
                badges.append({
                    'name': 'Active Seller',
                    'icon': '✅',
                    'description': '10+ successful sales',
                    'earned_at': datetime.utcnow().isoformat()
                })
            
            # Rating badges
            ratings_data = await self.get_user_ratings(user_id)
            if ratings_data['total_ratings'] >= 10 and ratings_data['average_rating'] >= 4.5:
                badges.append({
                    'name': 'Highly Rated',
                    'icon': '🌟',
                    'description': '4.5+ stars with 10+ ratings',
                    'earned_at': datetime.utcnow().isoformat()
                })
            
            # Purchase badges
            completed_purchases = await self.db.transactions.count_documents({
                'buyer_id': user_id,
                'status': 'completed'
            })
            
            if completed_purchases >= 50:
                badges.append({
                    'name': 'VIP Buyer',
                    'icon': '💎',
                    'description': '50+ purchases made',
                    'earned_at': datetime.utcnow().isoformat()
                })
            elif completed_purchases >= 10:
                badges.append({
                    'name': 'Regular Buyer',
                    'icon': '🛒',
                    'description': '10+ purchases made',
                    'earned_at': datetime.utcnow().isoformat()
                })
            
            return badges
            
        except Exception as e:
            logger.error(f"Error getting trust badges: {e}")
            return []
    
    async def get_community_stats(self) -> Dict[str, Any]:
        """Get overall community statistics"""
        try:
            # User statistics
            total_users = await self.db.users.count_documents({})
            active_sellers = await self.db.accounts.distinct('user_id', {
                'upload_date': {'$gte': datetime.utcnow() - timedelta(days=30)}
            })
            active_buyers = await self.db.transactions.distinct('buyer_id', {
                'created_at': {'$gte': datetime.utcnow() - timedelta(days=30)}
            })
            
            # Rating statistics
            total_ratings = await self.db.user_ratings.count_documents({})
            avg_community_rating = await self.db.user_ratings.aggregate([
                {'$group': {'_id': None, 'avg_rating': {'$avg': '$rating'}}}
            ]).to_list(None)
            
            community_rating = avg_community_rating[0]['avg_rating'] if avg_community_rating else 0
            
            # Top rated users
            top_rated = await self.db.user_ratings.aggregate([
                {
                    '$group': {
                        '_id': '$rated_user_id',
                        'avg_rating': {'$avg': '$rating'},
                        'total_ratings': {'$sum': 1}
                    }
                },
                {'$match': {'total_ratings': {'$gte': 5}}},
                {'$sort': {'avg_rating': -1}},
                {'$limit': 10}
            ]).to_list(None)
            
            # Format top rated users
            top_users = []
            for user_data in top_rated:
                user = await self.db.users.find_one({'user_id': user_data['_id']})
                if user:
                    top_users.append({
                        'user_id': user_data['_id'],
                        'username': user.get('username', f'User{user_data["_id"]}'),
                        'average_rating': round(user_data['avg_rating'], 2),
                        'total_ratings': user_data['total_ratings']
                    })
            
            # Recent community activity
            recent_ratings = await self.db.user_ratings.count_documents({
                'created_at': {'$gte': datetime.utcnow() - timedelta(days=7)}
            })
            
            recent_feedback = await self.db.community_feedback.count_documents({
                'created_at': {'$gte': datetime.utcnow() - timedelta(days=7)}
            })
            
            return {
                'community_overview': {
                    'total_users': total_users,
                    'active_sellers_30d': len(active_sellers),
                    'active_buyers_30d': len(active_buyers),
                    'total_ratings': total_ratings,
                    'average_community_rating': round(community_rating, 2)
                },
                'top_rated_users': top_users,
                'recent_activity': {
                    'new_ratings_7d': recent_ratings,
                    'community_feedback_7d': recent_feedback
                },
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting community stats: {e}")
            return {}
    
    async def _update_user_rating_stats(self, user_id: int):
        """Update cached rating statistics for a user"""
        try:
            stats = await self.db.user_ratings.aggregate([
                {'$match': {'rated_user_id': user_id}},
                {
                    '$group': {
                        '_id': None,
                        'total_ratings': {'$sum': 1},
                        'average_rating': {'$avg': '$rating'}
                    }
                }
            ]).to_list(None)
            
            if stats:
                await self.db.user_rating_stats.update_one(
                    {'user_id': user_id},
                    {
                        '$set': {
                            'total_ratings': stats[0]['total_ratings'],
                            'average_rating': stats[0]['average_rating'],
                            'updated_at': datetime.utcnow()
                        }
                    },
                    upsert=True
                )
                
        except Exception as e:
            logger.error(f"Error updating user rating stats: {e}")