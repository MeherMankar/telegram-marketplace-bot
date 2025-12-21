import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

class AdminPricingService:
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def set_country_buy_price(self, admin_id: int, country: str, buy_price: float) -> Dict[str, Any]:
        """Admin sets buy price for country"""
        try:
            await self.db.country_pricing.update_one(
                {'country': country},
                {
                    '$set': {
                        'country': country,
                        'buy_price': buy_price,
                        'buy_price_set_by': admin_id,
                        'buy_price_updated_at': utc_now()
                    }
                },
                upsert=True
            )
            
            return {
                'success': True,
                'message': f"Buy price set: {country} = ₹{buy_price}",
                'country': country,
                'buy_price': buy_price
            }
            
        except Exception as e:
            logger.error(f"Error setting buy price: {e}")
            return {'success': False, 'error': str(e)}
    
    async def set_country_sell_price(self, admin_id: int, country: str, sell_price: float) -> Dict[str, Any]:
        """Admin sets sell price for country"""
        try:
            await self.db.country_pricing.update_one(
                {'country': country},
                {
                    '$set': {
                        'sell_price': sell_price,
                        'sell_price_set_by': admin_id,
                        'sell_price_updated_at': utc_now()
                    }
                },
                upsert=True
            )
            
            return {
                'success': True,
                'message': f"Sell price set: {country} = ₹{sell_price}",
                'country': country,
                'sell_price': sell_price
            }
            
        except Exception as e:
            logger.error(f"Error setting sell price: {e}")
            return {'success': False, 'error': str(e)}
    
    async def set_country_both_prices(self, admin_id: int, country: str, 
                                    buy_price: float, sell_price: float) -> Dict[str, Any]:
        """Admin sets both buy and sell prices for country"""
        try:
            if sell_price <= buy_price:
                return {'success': False, 'error': 'Sell price must be higher than buy price'}
            
            await self.db.country_pricing.update_one(
                {'country': country},
                {
                    '$set': {
                        'country': country,
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'profit_margin': sell_price - buy_price,
                        'profit_percentage': ((sell_price - buy_price) / buy_price) * 100,
                        'updated_by': admin_id,
                        'updated_at': utc_now()
                    }
                },
                upsert=True
            )
            
            return {
                'success': True,
                'message': f"Prices set: {country} - Buy: ₹{buy_price}, Sell: ₹{sell_price}",
                'country': country,
                'buy_price': buy_price,
                'sell_price': sell_price,
                'profit': sell_price - buy_price
            }
            
        except Exception as e:
            logger.error(f"Error setting prices: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_country_buy_price(self, country: str) -> float:
        """Get admin-set buy price for country"""
        try:
            pricing = await self.db.country_pricing.find_one({'country': country})
            return pricing.get('buy_price', 0) if pricing else 0
            
        except Exception as e:
            logger.error(f"Error getting buy price: {e}")
            return 0
    
    async def get_country_sell_price(self, country: str) -> float:
        """Get admin-set sell price for country"""
        try:
            pricing = await self.db.country_pricing.find_one({'country': country})
            return pricing.get('sell_price', 0) if pricing else 0
            
        except Exception as e:
            logger.error(f"Error getting sell price: {e}")
            return 0
    
    async def get_all_country_pricing(self) -> List[Dict[str, Any]]:
        """Get all country pricing settings"""
        try:
            pricing_list = await self.db.country_pricing.find({}).to_list(None)
            return pricing_list
            
        except Exception as e:
            logger.error(f"Error getting country pricing: {e}")
            return []
    
    async def remove_country_pricing(self, admin_id: int, country: str) -> Dict[str, Any]:
        """Remove pricing for specific country"""
        try:
            result = await self.db.country_pricing.delete_one({'country': country})
            
            if result.deleted_count > 0:
                return {
                    'success': True,
                    'message': f"Pricing removed for {country}"
                }
            else:
                return {'success': False, 'error': 'Country pricing not found'}
                
        except Exception as e:
            logger.error(f"Error removing pricing: {e}")
            return {'success': False, 'error': str(e)}
    
    async def bulk_set_country_pricing(self, admin_id: int, country_pricing_data: List[Dict]) -> Dict[str, Any]:
        """Bulk set pricing for multiple countries"""
        try:
            successful = 0
            failed = 0
            
            for data in country_pricing_data:
                try:
                    await self.set_country_both_prices(
                        admin_id,
                        data['country'],
                        data['buy_price'],
                        data['sell_price']
                    )
                    successful += 1
                except:
                    failed += 1
            
            return {
                'success': True,
                'message': f"Bulk country pricing: {successful} successful, {failed} failed",
                'successful': successful,
                'failed': failed
            }
            
        except Exception as e:
            logger.error(f"Error in bulk country pricing: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_pricing_stats(self) -> Dict[str, Any]:
        """Get pricing statistics and profit analysis"""
        try:
            country_pricing = await self.get_all_country_pricing()
            
            if not country_pricing:
                return {'total_countries': 0, 'avg_profit': 0}
            
            # Calculate stats
            countries_with_both_prices = [c for c in country_pricing if c.get('profit_margin')]
            
            if not countries_with_both_prices:
                return {'total_countries': len(country_pricing), 'countries_with_both_prices': 0}
            
            total_profit = sum(c.get('profit_margin', 0) for c in countries_with_both_prices)
            avg_profit = total_profit / len(countries_with_both_prices)
            
            # Get highest and lowest profit margins
            profits = [c.get('profit_margin', 0) for c in countries_with_both_prices]
            highest_profit = max(profits) if profits else 0
            lowest_profit = min(profits) if profits else 0
            
            return {
                'total_countries': len(country_pricing),
                'countries_with_both_prices': len(countries_with_both_prices),
                'avg_profit_margin': round(avg_profit, 2),
                'highest_profit': highest_profit,
                'lowest_profit': lowest_profit
            }
            
        except Exception as e:
            logger.error(f"Error getting pricing stats: {e}")
            return {}
    
    async def suggest_country_pricing(self, country: str) -> Dict[str, Any]:
        """Suggest optimal buy/sell prices for country"""
        try:
            # Get recent sales data for this country
            recent_sales = await self.db.transactions.find({
                'account_country': country,
                'status': 'completed',
                'created_at': {'$gte': utc_now().replace(day=1)}  # This month
            }).to_list(None)
            
            # Base pricing by country
            base_prices = {
                'US': 45, 'IN': 30, 'GB': 40, 'CA': 35, 'AU': 35, 'DE': 35
            }
            base_buy = base_prices.get(country, 25)
            
            if recent_sales:
                # Market-based pricing
                avg_market_price = sum(sale['amount'] for sale in recent_sales) / len(recent_sales)
                suggested_buy = round(avg_market_price * 0.6, 2)
                confidence = 'high'
                reason = f'Based on {len(recent_sales)} recent sales'
            else:
                # Default pricing
                suggested_buy = base_buy
                confidence = 'medium'
                reason = 'Based on country defaults'
            
            suggested_sell = round(suggested_buy * 1.67, 2)  # 67% markup
            
            return {
                'country': country,
                'suggested_buy_price': suggested_buy,
                'suggested_sell_price': suggested_sell,
                'confidence': confidence,
                'reason': reason
            }
            
        except Exception as e:
            logger.error(f"Error suggesting pricing: {e}")
            return {'error': str(e)}