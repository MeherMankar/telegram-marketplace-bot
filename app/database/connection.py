import os
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional

class Database:
    client: Optional[AsyncIOMotorClient] = None
    database = None

db = Database()

async def init_db():
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/telegram_marketplace')
    db.client = AsyncIOMotorClient(mongo_uri)
    self.db_connection = db.client.get_default_database()
    
    # Create indexes
    await create_indexes()

async def create_indexes():
    # User indexes
    await self.db_connection.users.create_index("telegram_user_id", unique=True)
    
    # Account indexes
    await self.db_connection.accounts.create_index("seller_id")
    await self.db_connection.accounts.create_index("status")
    await self.db_connection.accounts.create_index("telegram_account_id")
    
    # Listing indexes
    await self.db_connection.listings.create_index("country")
    await self.db_connection.listings.create_index("creation_year")
    await self.db_connection.listings.create_index("status")
    await self.db_connection.listings.create_index([("country", 1), ("creation_year", 1)])
    
    # Transaction indexes
    await self.db_connection.transactions.create_index("user_id")
    await self.db_connection.transactions.create_index("status")

async def close_db():
    if db.client:
        db.client.close()

class DatabaseConnection:
    def __init__(self):
        self.client = None
        self.db = None
    
    async def connect(self):
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/telegram_marketplace')
        self.client = AsyncIOMotorClient(mongo_uri)
        # Use explicit database name as fallback
        try:
            self.db = self.client.get_default_database()
        except:
            self.db = self.client.telegram_marketplace
        
        # Collections
        self.users = self.db.users
        self.accounts = self.db.accounts
        self.listings = self.db.listings
        self.transactions = self.db.transactions
        self.admin_actions = self.db.admin_actions
        self.admin_settings = self.db.admin_settings
        self.payment_verifications = self.db.payment_verifications
        self.user_notifications = self.db.user_notifications
        self.country_pricing = self.db.country_pricing
        self.support_tickets = self.db.support_tickets
        self.marketing_campaigns = self.db.marketing_campaigns
        self.discount_codes = self.db.discount_codes
        self.user_ratings = self.db.user_ratings
        self.security_logs = self.db.security_logs
        self.compliance_logs = self.db.compliance_logs
        self.upi_orders = self.db.upi_orders
        self.payment_orders = self.db.payment_orders
        self.admin_notifications = self.db.admin_notifications
        self.encryption_keys = self.db.encryption_keys
        self.error_logs = self.db.error_logs
        self.metrics = self.db.metrics
        self.referrals = self.db.referrals
        self.bot_settings = self.db.bot_settings
        
        await self._create_indexes()
    
    async def _create_indexes(self):
        # User indexes
        await self.users.create_index("telegram_user_id", unique=True)
        
        # Account indexes
        await self.accounts.create_index("user_id")
        await self.accounts.create_index("verification_status")
        await self.accounts.create_index("country")
        
        # Pricing indexes
        await self.country_pricing.create_index("country", unique=True)
    
    async def close(self):
        if self.client:
            self.client.close()