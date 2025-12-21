"""Monitoring and analytics service"""
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class MonitoringService:
    """Monitor bot performance and metrics"""
    
    def __init__(self, db_connection):
        self.db = db_connection
    
    async def log_metric(self, metric_name: str, value: float, tags: Dict[str, str] = None):
        """Log a metric"""
        metric_doc = {
            "name": metric_name,
            "value": value,
            "tags": tags or {},
            "timestamp": datetime.utcnow()
        }
        await self.db.metrics.insert_one(metric_doc)
    
    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get dashboard statistics"""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        
        # User stats
        total_users = await self.db.users.count_documents({})
        active_today = await self.db.users.count_documents({
            "last_activity": {"$gte": today_start}
        })
        
        # Account stats
        total_accounts = await self.db.accounts.count_documents({})
        pending_accounts = await self.db.accounts.count_documents({"status": "pending"})
        approved_accounts = await self.db.accounts.count_documents({"status": "approved"})
        
        # Transaction stats
        total_transactions = await self.db.transactions.count_documents({})
        pending_transactions = await self.db.transactions.count_documents({"status": "pending"})
        
        # Revenue stats
        revenue_pipeline = [
            {"$match": {"status": "confirmed", "type": "account_sale"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        revenue_result = await self.db.transactions.aggregate(revenue_pipeline).to_list(length=1)
        total_revenue = revenue_result[0]["total"] if revenue_result else 0
        
        # Today's revenue
        today_revenue_pipeline = [
            {"$match": {
                "status": "confirmed",
                "type": "account_sale",
                "created_at": {"$gte": today_start}
            }},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        today_revenue_result = await self.db.transactions.aggregate(today_revenue_pipeline).to_list(length=1)
        today_revenue = today_revenue_result[0]["total"] if today_revenue_result else 0
        
        # Conversion rate
        total_listings = await self.db.listings.count_documents({})
        sold_listings = await self.db.listings.count_documents({"status": "sold"})
        conversion_rate = (sold_listings / total_listings * 100) if total_listings > 0 else 0
        
        return {
            "users": {
                "total": total_users,
                "active_today": active_today
            },
            "accounts": {
                "total": total_accounts,
                "pending": pending_accounts,
                "approved": approved_accounts
            },
            "transactions": {
                "total": total_transactions,
                "pending": pending_transactions
            },
            "revenue": {
                "total": total_revenue,
                "today": today_revenue
            },
            "conversion_rate": round(conversion_rate, 2),
            "timestamp": now
        }
    
    async def get_response_time_stats(self) -> Dict[str, float]:
        """Get bot response time statistics"""
        pipeline = [
            {"$match": {"name": "response_time"}},
            {"$group": {
                "_id": None,
                "avg": {"$avg": "$value"},
                "min": {"$min": "$value"},
                "max": {"$max": "$value"}
            }}
        ]
        result = await self.db.metrics.aggregate(pipeline).to_list(length=1)
        
        if result:
            return {
                "avg_ms": round(result[0]["avg"], 2),
                "min_ms": round(result[0]["min"], 2),
                "max_ms": round(result[0]["max"], 2)
            }
        return {"avg_ms": 0, "min_ms": 0, "max_ms": 0}
