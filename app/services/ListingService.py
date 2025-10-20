import logging
from datetime import datetime
from typing import List, Dict, Any
from app.models import SettingsManager

logger = logging.getLogger(__name__)

class ListingService:
    """Manage account listings and marketplace operations"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
        self.settings_manager = SettingsManager(db_connection)
    
    async def create_listing(self, account_id: str, seller_id: int) -> dict:
        """Create listing from approved account"""
        try:
            # Get account details
            account = await self.db_connection.accounts.find_one({"_id": account_id})
            if not account:
                return {"success": False, "error": "Account not found"}
            
            if account["status"] != "approved":
                return {"success": False, "error": "Account not approved"}
            
            # Get pricing
            country = account.get("country", "Unknown")
            year = account.get("creation_year", "2024")
            
            price_doc = await self.db_connection.admin_settings.find_one({"type": "price_table"})
            if price_doc:
                prices = price_doc.get("prices", {})
                country_prices = prices.get(country, {})
                year_prices = country_prices.get(str(year), {"buy": 30, "sell": 40})
                
                if isinstance(year_prices, dict):
                    sell_price = year_prices.get("sell", 40)
                else:
                    sell_price = year_prices  # Legacy format
            else:
                sell_price = 40  # Default price
            
            # Create listing
            listing_data = {
                "account_id": account_id,
                "seller_id": seller_id,
                "telegram_account_id": account.get("telegram_account_id"),
                "username": account.get("username"),
                "country": country,
                "creation_year": year,
                "price": sell_price,
                "currency": "INR",
                "status": "active",
                "created_at": datetime.utcnow(),
                "views": 0,
                "featured": False
            }
            
            result = await self.db_connection.listings.insert_one(listing_data)
            listing_id = result.inserted_id
            
            # Update account status
            await self.db_connection.accounts.update_one(
                {"_id": account_id},
                {"$set": {"status": "listed", "listing_id": listing_id}}
            )
            
            logger.info(f"Listing created: {listing_id} for account {account_id}")
            return {"success": True, "listing_id": listing_id, "price": sell_price}
            
        except Exception as e:
            logger.error(f"Failed to create listing: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def get_listings(self, filters: dict = None, limit: int = 20, skip: int = 0) -> List[dict]:
        """Get listings with filters"""
        try:
            query = {"status": "active"}
            
            if filters:
                if filters.get("country"):
                    query["country"] = filters["country"]
                if filters.get("creation_year"):
                    query["creation_year"] = filters["creation_year"]
                if filters.get("min_price"):
                    query["price"] = {"$gte": filters["min_price"]}
                if filters.get("max_price"):
                    if "price" in query:
                        query["price"]["$lte"] = filters["max_price"]
                    else:
                        query["price"] = {"$lte": filters["max_price"]}
                if filters.get("has_username"):
                    query["username"] = {"$ne": None, "$exists": True}
            
            # Sort by featured first, then by creation date
            sort_criteria = [("featured", -1), ("created_at", -1)]
            
            listings = await self.db_connection.listings.find(query)\
                .sort(sort_criteria)\
                .skip(skip)\
                .limit(limit)\
                .to_list(length=limit)
            
            return listings
            
        except Exception as e:
            logger.error(f"Failed to get listings: {str(e)}")
            return []
    
    async def get_listing_by_id(self, listing_id: str) -> dict:
        """Get specific listing by ID"""
        try:
            listing = await self.db_connection.listings.find_one({"_id": listing_id})
            if listing:
                # Increment view count
                await self.db_connection.listings.update_one(
                    {"_id": listing_id},
                    {"$inc": {"views": 1}}
                )
            return listing
            
        except Exception as e:
            logger.error(f"Failed to get listing {listing_id}: {str(e)}")
            return None
    
    async def reserve_listing(self, listing_id: str, buyer_id: int) -> dict:
        """Reserve listing for purchase"""
        try:
            listing = await self.db_connection.listings.find_one({"_id": listing_id})
            if not listing:
                return {"success": False, "error": "Listing not found"}
            
            if listing["status"] != "active":
                return {"success": False, "error": "Listing not available"}
            
            # Reserve the listing
            await self.db_connection.listings.update_one(
                {"_id": listing_id},
                {
                    "$set": {
                        "status": "reserved",
                        "reserved_by": buyer_id,
                        "reserved_at": datetime.utcnow()
                    }
                }
            )
            
            return {"success": True, "message": "Listing reserved"}
            
        except Exception as e:
            logger.error(f"Failed to reserve listing: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def release_reservation(self, listing_id: str) -> dict:
        """Release listing reservation"""
        try:
            await self.db_connection.listings.update_one(
                {"_id": listing_id},
                {
                    "$set": {"status": "active"},
                    "$unset": {"reserved_by": "", "reserved_at": ""}
                }
            )
            
            return {"success": True, "message": "Reservation released"}
            
        except Exception as e:
            logger.error(f"Failed to release reservation: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def mark_as_sold(self, listing_id: str, buyer_id: int, sale_price: float) -> dict:
        """Mark listing as sold"""
        try:
            await self.db_connection.listings.update_one(
                {"_id": listing_id},
                {
                    "$set": {
                        "status": "sold",
                        "buyer_id": buyer_id,
                        "sold_at": datetime.utcnow(),
                        "sale_price": sale_price
                    }
                }
            )
            
            return {"success": True, "message": "Listing marked as sold"}
            
        except Exception as e:
            logger.error(f"Failed to mark listing as sold: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def get_countries_with_counts(self) -> List[dict]:
        """Get countries with listing counts"""
        try:
            pipeline = [
                {"$match": {"status": "active"}},
                {"$group": {
                    "_id": "$country",
                    "count": {"$sum": 1},
                    "min_price": {"$min": "$price"},
                    "max_price": {"$max": "$price"}
                }},
                {"$sort": {"count": -1}}
            ]
            
            result = await self.db_connection.listings.aggregate(pipeline).to_list(length=None)
            return result
            
        except Exception as e:
            logger.error(f"Failed to get countries with counts: {str(e)}")
            return []
    
    async def get_years_for_country(self, country: str) -> List[dict]:
        """Get creation years for a country with counts"""
        try:
            pipeline = [
                {"$match": {"status": "active", "country": country}},
                {"$group": {
                    "_id": "$creation_year",
                    "count": {"$sum": 1},
                    "min_price": {"$min": "$price"},
                    "max_price": {"$max": "$price"}
                }},
                {"$sort": {"_id": -1}}
            ]
            
            result = await self.db_connection.listings.aggregate(pipeline).to_list(length=None)
            return result
            
        except Exception as e:
            logger.error(f"Failed to get years for country {country}: {str(e)}")
            return []
    
    async def search_listings(self, query: str, limit: int = 10) -> List[dict]:
        """Search listings by username or other criteria"""
        try:
            search_query = {
                "status": "active",
                "$or": [
                    {"username": {"$regex": query, "$options": "i"}},
                    {"country": {"$regex": query, "$options": "i"}}
                ]
            }
            
            listings = await self.db_connection.listings.find(search_query)\
                .sort("created_at", -1)\
                .limit(limit)\
                .to_list(length=limit)
            
            return listings
            
        except Exception as e:
            logger.error(f"Failed to search listings: {str(e)}")
            return []
    
    async def get_seller_listings(self, seller_id: int, status: str = None) -> List[dict]:
        """Get listings for a specific seller"""
        try:
            query = {"seller_id": seller_id}
            if status:
                query["status"] = status
            
            listings = await self.db_connection.listings.find(query)\
                .sort("created_at", -1)\
                .to_list(length=None)
            
            return listings
            
        except Exception as e:
            logger.error(f"Failed to get seller listings: {str(e)}")
            return []
    
    async def get_buyer_purchases(self, buyer_id: int) -> List[dict]:
        """Get purchases for a specific buyer"""
        try:
            purchases = await self.db_connection.listings.find({
                "buyer_id": buyer_id,
                "status": "sold"
            }).sort("sold_at", -1).to_list(length=None)
            
            return purchases
            
        except Exception as e:
            logger.error(f"Failed to get buyer purchases: {str(e)}")
            return []
    
    async def update_listing_price(self, listing_id: str, new_price: float) -> dict:
        """Update listing price"""
        try:
            await self.db_connection.listings.update_one(
                {"_id": listing_id},
                {"$set": {"price": new_price, "updated_at": datetime.utcnow()}}
            )
            
            return {"success": True, "message": "Price updated"}
            
        except Exception as e:
            logger.error(f"Failed to update listing price: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def feature_listing(self, listing_id: str, featured: bool = True) -> dict:
        """Feature or unfeature a listing"""
        try:
            await self.db_connection.listings.update_one(
                {"_id": listing_id},
                {"$set": {"featured": featured, "updated_at": datetime.utcnow()}}
            )
            
            action = "featured" if featured else "unfeatured"
            return {"success": True, "message": f"Listing {action}"}
            
        except Exception as e:
            logger.error(f"Failed to feature listing: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def get_marketplace_stats(self) -> dict:
        """Get marketplace statistics"""
        try:
            stats = {}
            
            # Total listings
            stats["total_active"] = await self.db_connection.listings.count_documents({"status": "active"})
            stats["total_sold"] = await self.db_connection.listings.count_documents({"status": "sold"})
            
            # By country
            country_pipeline = [
                {"$match": {"status": "active"}},
                {"$group": {"_id": "$country", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]
            stats["top_countries"] = await self.db_connection.listings.aggregate(country_pipeline).to_list(length=5)
            
            # Price ranges
            price_pipeline = [
                {"$match": {"status": "active"}},
                {"$group": {
                    "_id": None,
                    "min_price": {"$min": "$price"},
                    "max_price": {"$max": "$price"},
                    "avg_price": {"$avg": "$price"}
                }}
            ]
            price_stats = await self.db_connection.listings.aggregate(price_pipeline).to_list(length=1)
            if price_stats:
                stats.update(price_stats[0])
                del stats["_id"]
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get marketplace stats: {str(e)}")
            return {}