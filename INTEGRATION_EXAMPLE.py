"""
Integration Examples for New Features
Copy these code snippets into your bot handlers
"""

# ============================================
# 1. RATE LIMITING INTEGRATION
# ============================================

from app.utils.rate_limiter import rate_limiter

# Add to SellerBot.handle_upload_account
async def handle_upload_account(self, event, user):
    # Check rate limit
    allowed, message = rate_limiter.is_allowed(
        user.telegram_user_id, 
        "upload_account", 
        max_requests=5,  # 5 uploads
        window_seconds=300  # per 5 minutes
    )
    
    if not allowed:
        await self.edit_message(event, f"⚠️ **Rate Limit**\n\n{message}")
        return
    
    # Continue with upload logic...


# Add to BuyerBot.handle_browse_accounts
async def handle_browse_accounts(self, event):
    user = await self.get_or_create_user(event)
    
    # Check rate limit
    allowed, message = rate_limiter.is_allowed(
        user.telegram_user_id,
        "browse_accounts",
        max_requests=20,  # 20 browses
        window_seconds=60  # per minute
    )
    
    if not allowed:
        await self.edit_message(event, f"⚠️ {message}")
        return
    
    # Continue with browse logic...


# ============================================
# 2. CACHING INTEGRATION
# ============================================

from app.services.CacheService import cache_service

# Add to BuyerBot.handle_country_selection
async def handle_country_selection(self, event, country):
    # Try cache first
    cache_key = f"listings:{country}"
    cached_listings = cache_service.get(cache_key)
    
    if cached_listings:
        # Use cached data
        await self.show_listings(event, cached_listings)
        return
    
    # Fetch from database
    listings = await self.db_connection.listings.find({
        "status": "active",
        "country": country
    }).to_list(length=100)
    
    # Cache for 5 minutes
    cache_service.set(cache_key, listings, ttl_seconds=300)
    
    await self.show_listings(event, listings)


# Add to AdminBot - cache bot settings
async def get_bot_settings(self, setting_type):
    cache_key = f"settings:{setting_type}"
    cached = cache_service.get(cache_key)
    
    if cached:
        return cached
    
    settings = await self.db_connection.bot_settings.find_one({"type": setting_type})
    cache_service.set(cache_key, settings, ttl_seconds=1800)  # 30 min
    
    return settings


# ============================================
# 3. ERROR TRACKING INTEGRATION
# ============================================

from app.utils.error_tracker import ErrorTracker

# Add to any bot handler
async def handle_payment(self, event, user, listing_id):
    error_tracker = ErrorTracker(self.db_connection)
    
    try:
        # Payment processing logic
        result = await self.process_payment(user, listing_id)
        
    except Exception as e:
        # Log error with context
        await error_tracker.log_error(e, {
            "action": "payment_processing",
            "user_id": user.telegram_user_id,
            "listing_id": listing_id,
            "bot": "buyer"
        }, user.telegram_user_id)
        
        # Show user-friendly message
        await self.send_message(
            event.chat_id,
            "❌ Payment processing failed. Our team has been notified."
        )


# ============================================
# 4. REFERRAL SYSTEM INTEGRATION
# ============================================

from app.services.ReferralService import ReferralService

# Add to BuyerBot/SellerBot.handle_start
async def handle_start(self, event):
    user = await self.get_or_create_user(event)
    referral_service = ReferralService(self.db_connection)
    
    # Check for referral code in /start command
    # Format: /start REF_CODE
    if event.message.text and len(event.message.text.split()) > 1:
        referral_code = event.message.text.split()[1].upper()
        
        result = await referral_service.apply_referral(
            user.telegram_user_id,
            referral_code
        )
        
        if result["success"]:
            await self.send_message(
                event.chat_id,
                f"🎉 **Referral Applied!**\n\n"
                f"You received ₹{result['referee_bonus']} bonus!\n"
                f"Your referrer received ₹{result['referrer_bonus']} bonus!"
            )
    
    # Show welcome message...


# Add referral menu option
async def handle_my_referrals(self, event, user):
    referral_service = ReferralService(self.db_connection)
    
    # Get or generate referral code
    code = await referral_service.generate_referral_code(user.telegram_user_id)
    
    # Get stats
    stats = await referral_service.get_referral_stats(user.telegram_user_id)
    
    message = f"""
🎁 **Your Referral Program**

📋 **Your Code:** `{code}`
👥 **Total Referrals:** {stats['total_referrals']}
💰 **Total Earned:** ₹{stats['total_earned']:.2f}

**How it works:**
• Share your code with friends
• They get ₹5 bonus on signup
• You get ₹10 bonus per referral

**Share Link:**
https://t.me/{self.client.me.username}?start={code}
"""
    
    await self.edit_message(event, message, [
        [Button.inline("🔙 Back", "back_to_main")]
    ])


# ============================================
# 5. MONITORING INTEGRATION
# ============================================

from app.services.MonitoringService import MonitoringService
import time

# Add to AdminBot - Dashboard
async def show_dashboard(self, event):
    monitoring = MonitoringService(self.db_connection)
    
    stats = await monitoring.get_dashboard_stats()
    response_stats = await monitoring.get_response_time_stats()
    
    message = f"""
📊 **Admin Dashboard**

👥 **Users:**
• Total: {stats['users']['total']:,}
• Active Today: {stats['users']['active_today']:,}

📦 **Accounts:**
• Total: {stats['accounts']['total']:,}
• Pending: {stats['accounts']['pending']:,}
• Approved: {stats['accounts']['approved']:,}

💰 **Revenue:**
• Total: ₹{stats['revenue']['total']:,.2f}
• Today: ₹{stats['revenue']['today']:,.2f}

📈 **Performance:**
• Conversion Rate: {stats['conversion_rate']}%
• Avg Response: {response_stats['avg_ms']:.0f}ms

🕐 **Last Updated:** {stats['timestamp'].strftime('%H:%M:%S')}
"""
    
    await self.edit_message(event, message, [
        [Button.inline("🔄 Refresh", "dashboard")],
        [Button.inline("🔙 Back", "admin_menu")]
    ])


# Track response times
async def handle_any_command(self, event):
    start_time = time.time()
    monitoring = MonitoringService(self.db_connection)
    
    try:
        # Your command logic
        await self.process_command(event)
        
    finally:
        # Log response time
        response_time = (time.time() - start_time) * 1000  # ms
        await monitoring.log_metric(
            "response_time",
            response_time,
            {"bot": "buyer", "command": "browse"}
        )


# ============================================
# 6. ACCOUNT PREVIEW INTEGRATION
# ============================================

from app.services.AccountPreviewService import AccountPreviewService

# Add to BuyerBot.handle_listing_details
async def handle_listing_details(self, event, listing_id):
    listing = await self.db_connection.listings.find_one({"_id": listing_id})
    
    if not listing:
        await self.edit_message(event, "❌ Listing not found")
        return
    
    # Generate preview
    preview_service = AccountPreviewService(self.db_connection)
    preview = await preview_service.generate_preview(listing["account_id"])
    
    if not preview:
        await self.edit_message(event, "❌ Preview unavailable")
        return
    
    # Build message with preview
    method_emoji = "📱" if preview["obtained_via"] == "otp" else "📤"
    
    message = f"""
💎 **Account Preview**

{method_emoji} **Method:** {preview["obtained_via"].upper()}
🌍 **Country:** {preview["country"]}
📅 **Year:** {preview["creation_year"]}
👤 **Username:** {preview["username"]}
📱 **Phone:** {preview["phone"]}

⭐ **Quality Score:** {preview["quality_score"]}%
✅ **Checks Passed:** {preview["checks_passed"]}

**Features:**
{"✅" if preview["features"]["zero_contacts"] else "❌"} Zero Contacts
{"✅" if preview["features"]["no_spam"] else "❌"} No Spam
{"✅" if preview["features"]["clean_groups"] else "❌"} Clean Groups
{"✅" if preview["features"]["active"] else "❌"} Active Account

💰 **Price:** ₹{listing["price"]:.2f}
"""
    
    await self.edit_message(event, message, [
        [Button.inline("🛒 Buy Now", f"buy_{listing_id}")],
        [Button.inline("🔙 Back", "browse_accounts")]
    ])


# ============================================
# 7. PAYMENT TIMEOUT NOTIFICATION
# ============================================

# The PaymentTimeoutService runs automatically in background
# To notify users when their payment expires, add this to your bot:

async def notify_payment_expired(self, user_id, transaction_id):
    """Called by PaymentTimeoutService when payment expires"""
    await self.send_message(
        user_id,
        "⏰ **Payment Expired**\n\n"
        "Your payment session has expired after 30 minutes.\n"
        "Please start a new purchase if you're still interested.\n\n"
        f"Transaction ID: {transaction_id}"
    )


# ============================================
# 8. COMPLETE INTEGRATION EXAMPLE
# ============================================

# Example: Enhanced upload handler with all features
async def enhanced_upload_handler(self, event, user):
    from app.utils.rate_limiter import rate_limiter
    from app.utils.error_tracker import ErrorTracker
    from app.services.MonitoringService import MonitoringService
    import time
    
    start_time = time.time()
    error_tracker = ErrorTracker(self.db_connection)
    monitoring = MonitoringService(self.db_connection)
    
    try:
        # 1. Rate limiting
        allowed, message = rate_limiter.is_allowed(
            user.telegram_user_id, "upload", 5, 300
        )
        if not allowed:
            await self.edit_message(event, f"⚠️ {message}")
            return
        
        # 2. Process upload
        result = await self.process_upload(event, user)
        
        # 3. Log success metric
        await monitoring.log_metric("upload_success", 1, {
            "user_id": str(user.telegram_user_id)
        })
        
    except Exception as e:
        # 4. Error tracking
        await error_tracker.log_error(e, {
            "action": "upload",
            "user_id": user.telegram_user_id
        }, user.telegram_user_id)
        
        await self.send_message(
            event.chat_id,
            "❌ Upload failed. Please try again."
        )
        
    finally:
        # 5. Log response time
        response_time = (time.time() - start_time) * 1000
        await monitoring.log_metric("response_time", response_time, {
            "bot": "seller",
            "action": "upload"
        })


# ============================================
# USAGE NOTES
# ============================================

"""
1. Copy relevant code snippets to your bot handlers
2. Adjust rate limits based on your needs
3. Set appropriate cache TTLs
4. Test error tracking in development
5. Monitor metrics in production
6. Adjust referral bonuses as needed

For full documentation, see IMPROVEMENTS.md
"""
