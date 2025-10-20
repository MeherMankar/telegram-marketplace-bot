import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
import pandas as pd
from collections import defaultdict

logger = logging.getLogger(__name__)

class AnalyticsService:
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def get_revenue_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get revenue analytics for specified period"""
        try:
            start_date = datetime.utcnow() - timedelta(days=days)
            
            # Get completed transactions
            transactions = await self.db.transactions.find({
                'status': 'completed',
                'created_at': {'$gte': start_date}
            }).to_list(None)
            
            if not transactions:
                return self._empty_revenue_analytics()
            
            # Calculate metrics
            total_revenue = sum(t['amount'] for t in transactions)
            total_transactions = len(transactions)
            avg_transaction = total_revenue / total_transactions if total_transactions > 0 else 0
            
            # Daily revenue breakdown
            daily_revenue = defaultdict(float)
            for transaction in transactions:
                date_key = transaction['created_at'].strftime('%Y-%m-%d')
                daily_revenue[date_key] += transaction['amount']
            
            # Revenue by country
            country_revenue = defaultdict(float)
            for transaction in transactions:
                account = await self.db.accounts.find_one({'_id': transaction['account_id']})
                if account:
                    country_revenue[account.get('country', 'Unknown')] += transaction['amount']
            
            # Growth calculation
            mid_point = start_date + timedelta(days=days//2)
            first_half_revenue = sum(t['amount'] for t in transactions if t['created_at'] < mid_point)
            second_half_revenue = sum(t['amount'] for t in transactions if t['created_at'] >= mid_point)
            
            growth_rate = 0
            if first_half_revenue > 0:
                growth_rate = ((second_half_revenue - first_half_revenue) / first_half_revenue) * 100
            
            return {
                'period_days': days,
                'total_revenue': round(total_revenue, 2),
                'total_transactions': total_transactions,
                'average_transaction': round(avg_transaction, 2),
                'growth_rate': round(growth_rate, 2),
                'daily_revenue': dict(daily_revenue),
                'country_revenue': dict(country_revenue),
                'top_selling_countries': sorted(country_revenue.items(), key=lambda x: x[1], reverse=True)[:5]
            }
            
        except Exception as e:
            logger.error(f"Revenue analytics error: {e}")
            return self._empty_revenue_analytics()
    
    async def get_user_behavior_analytics(self) -> Dict[str, Any]:
        """Analyze user behavior patterns"""
        try:
            # User registration trends
            users = await self.db.users.find({}).to_list(None)
            
            # Registration by date
            registration_dates = defaultdict(int)
            user_types = defaultdict(int)
            
            for user in users:
                if user.get('created_at'):
                    date_key = user['created_at'].strftime('%Y-%m-%d')
                    registration_dates[date_key] += 1
                
                user_types[user.get('user_type', 'unknown')] += 1
            
            # Activity metrics
            active_sellers = await self.db.accounts.distinct('user_id', {
                'upload_date': {'$gte': datetime.utcnow() - timedelta(days=30)}
            })
            
            active_buyers = await self.db.transactions.distinct('buyer_id', {
                'created_at': {'$gte': datetime.utcnow() - timedelta(days=30)}
            })
            
            # Upload patterns
            upload_stats = await self.db.accounts.aggregate([
                {
                    '$group': {
                        '_id': '$user_id',
                        'total_uploads': {'$sum': 1},
                        'approved_uploads': {
                            '$sum': {'$cond': [{'$eq': ['$verification_status', 'approved']}, 1, 0]}
                        }
                    }
                }
            ]).to_list(None)
            
            avg_uploads_per_user = sum(stat['total_uploads'] for stat in upload_stats) / len(upload_stats) if upload_stats else 0
            avg_approval_rate = sum(stat['approved_uploads'] / stat['total_uploads'] for stat in upload_stats if stat['total_uploads'] > 0) / len(upload_stats) if upload_stats else 0
            
            return {
                'total_users': len(users),
                'user_types': dict(user_types),
                'active_sellers_30d': len(active_sellers),
                'active_buyers_30d': len(active_buyers),
                'registration_trend': dict(registration_dates),
                'avg_uploads_per_user': round(avg_uploads_per_user, 2),
                'avg_approval_rate': round(avg_approval_rate * 100, 2)
            }
            
        except Exception as e:
            logger.error(f"User behavior analytics error: {e}")
            return {}
    
    async def get_market_trends(self) -> Dict[str, Any]:
        """Analyze market trends and patterns"""
        try:
            # Price trends by country and year
            listings = await self.db.listings.find({'status': 'sold'}).to_list(None)
            
            price_trends = defaultdict(lambda: defaultdict(list))
            for listing in listings:
                country = listing.get('country', 'Unknown')
                year = listing.get('creation_year', 2024)
                price_trends[country][year].append(listing['price'])
            
            # Calculate average prices
            avg_prices = {}
            for country, years in price_trends.items():
                avg_prices[country] = {}
                for year, prices in years.items():
                    avg_prices[country][year] = sum(prices) / len(prices)
            
            # Most popular countries
            country_demand = defaultdict(int)
            for listing in listings:
                country_demand[listing.get('country', 'Unknown')] += 1
            
            # Account age preferences
            age_demand = defaultdict(int)
            current_year = datetime.now().year
            for listing in listings:
                age = current_year - listing.get('creation_year', current_year)
                age_range = f"{age}-{age+1} years" if age < 5 else "5+ years"
                age_demand[age_range] += 1
            
            # Seasonal trends (if enough data)
            monthly_sales = defaultdict(int)
            for listing in listings:
                if listing.get('sold_date'):
                    month = listing['sold_date'].strftime('%Y-%m')
                    monthly_sales[month] += 1
            
            return {
                'average_prices_by_country_year': avg_prices,
                'most_popular_countries': sorted(country_demand.items(), key=lambda x: x[1], reverse=True)[:10],
                'age_preferences': dict(age_demand),
                'monthly_sales_trend': dict(monthly_sales),
                'total_market_size': len(listings)
            }
            
        except Exception as e:
            logger.error(f"Market trends error: {e}")
            return {}
    
    async def get_performance_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive performance dashboard data"""
        try:
            # Get data for different time periods
            revenue_30d = await self.get_revenue_analytics(30)
            revenue_7d = await self.get_revenue_analytics(7)
            user_behavior = await self.get_user_behavior_analytics()
            market_trends = await self.get_market_trends()
            
            # System health metrics
            total_accounts = await self.db.accounts.count_documents({})
            pending_approvals = await self.db.accounts.count_documents({'verification_status': 'pending'})
            active_listings = await self.db.listings.count_documents({'status': 'active'})
            
            # Recent activity
            recent_transactions = await self.db.transactions.find({
                'created_at': {'$gte': datetime.utcnow() - timedelta(hours=24)}
            }).sort('created_at', -1).limit(10).to_list(None)
            
            return {
                'revenue_metrics': {
                    '30_days': revenue_30d,
                    '7_days': revenue_7d
                },
                'user_metrics': user_behavior,
                'market_data': market_trends,
                'system_health': {
                    'total_accounts': total_accounts,
                    'pending_approvals': pending_approvals,
                    'active_listings': active_listings,
                    'approval_queue_size': pending_approvals
                },
                'recent_activity': [
                    {
                        'transaction_id': str(t['_id']),
                        'amount': t['amount'],
                        'country': t.get('country', 'Unknown'),
                        'timestamp': t['created_at'].isoformat()
                    }
                    for t in recent_transactions
                ],
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Performance dashboard error: {e}")
            return {}
    
    async def forecast_revenue(self, days_ahead: int = 30) -> Dict[str, Any]:
        """Simple revenue forecasting based on historical data"""
        try:
            # Get historical data (last 90 days)
            historical_data = await self.get_revenue_analytics(90)
            daily_revenue = historical_data.get('daily_revenue', {})
            
            if len(daily_revenue) < 7:
                return {'error': 'Insufficient historical data for forecasting'}
            
            # Simple moving average forecast
            recent_values = list(daily_revenue.values())[-14:]  # Last 14 days
            avg_daily_revenue = sum(recent_values) / len(recent_values)
            
            # Apply growth trend
            growth_rate = historical_data.get('growth_rate', 0) / 100
            daily_growth = growth_rate / 30  # Convert monthly to daily
            
            forecast = {}
            current_date = datetime.utcnow()
            
            for i in range(days_ahead):
                future_date = current_date + timedelta(days=i+1)
                date_key = future_date.strftime('%Y-%m-%d')
                
                # Apply compound growth
                forecasted_revenue = avg_daily_revenue * (1 + daily_growth) ** (i + 1)
                forecast[date_key] = round(forecasted_revenue, 2)
            
            total_forecast = sum(forecast.values())
            
            return {
                'forecast_period_days': days_ahead,
                'daily_forecast': forecast,
                'total_forecasted_revenue': round(total_forecast, 2),
                'avg_daily_forecast': round(total_forecast / days_ahead, 2),
                'confidence_level': 'Low' if len(recent_values) < 14 else 'Medium',
                'based_on_days': len(recent_values)
            }
            
        except Exception as e:
            logger.error(f"Revenue forecasting error: {e}")
            return {'error': str(e)}
    
    def _empty_revenue_analytics(self) -> Dict[str, Any]:
        """Return empty revenue analytics structure"""
        return {
            'period_days': 0,
            'total_revenue': 0,
            'total_transactions': 0,
            'average_transaction': 0,
            'growth_rate': 0,
            'daily_revenue': {},
            'country_revenue': {},
            'top_selling_countries': []
        }