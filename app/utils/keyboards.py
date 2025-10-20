from telethon import Button
from typing import List, Dict, Any

def create_main_menu(is_seller: bool = False, is_admin: bool = False) -> List[List[Button]]:
    """Create main menu keyboard"""
    if is_admin:
        return [
            [Button.inline("📋 Review Accounts", "review_accounts"), Button.inline("💰 Payments", "approve_payments")],
            [Button.inline("💵 Pricing Control", "admin_pricing"), Button.inline("📊 Analytics", "view_stats")],
            [Button.inline("👥 Users", "user_management"), Button.inline("🛡️ Security", "security_logs")],
            [Button.inline("💾 Backup", "backup_system"), Button.inline("⚙️ Settings", "admin_settings")]
        ]
    elif is_seller:
        return [
            [Button.inline("📤 Upload Account", "upload_account"), Button.inline("📱 Sell via OTP", "sell_via_otp")],
            [Button.inline("💰 My Balance", "my_balance"), Button.inline("📊 My Listings", "my_accounts")],
            [Button.inline("💸 Request Payout", "request_payout"), Button.inline("⭐ My Rating", "my_rating")],
            [Button.inline("📈 Analytics", "seller_stats"), Button.inline("❓ Help", "help")]
        ]
    else:
        return [
            [Button.inline("🛒 Browse Accounts", "browse_accounts"), Button.inline("💰 My Purchases", "my_purchases")],
            [Button.inline("💵 My Balance", "my_balance"), Button.inline("💸 Add Funds", "add_funds")],
            [Button.inline("❓ Help", "help")]
        ]

def create_country_menu(countries: List[str]) -> List[List[Button]]:
    """Create country selection menu"""
    country_flags = {
        'US': '🇺🇸', 'IN': '🇮🇳', 'GB': '🇬🇧', 'CA': '🇨🇦', 'AU': '🇦🇺', 'DE': '🇩🇪', 
        'FR': '🇫🇷', 'BR': '🇧🇷', 'RU': '🇷🇺', 'JP': '🇯🇵', 'KR': '🇰🇷', 'CN': '🇨🇳'
    }
    
    buttons = []
    for i in range(0, len(countries), 3):
        row = []
        for j in range(3):
            if i + j < len(countries):
                country = countries[i + j]
                flag = country_flags.get(country, '🌍')
                row.append(Button.inline(f"{flag} {country}", f"country_{country}"))
        buttons.append(row)
    
    buttons.append([Button.inline("🔙 Back to Menu", "back_to_main")])
    return buttons

def create_year_menu(years: List[int], country: str) -> List[List[Button]]:
    """Create year selection menu"""
    buttons = []
    for i in range(0, len(years), 4):
        row = []
        for j in range(4):
            if i + j < len(years):
                year = years[i + j]
                row.append(Button.inline(f"📅 {year}", f"year_{country}_{year}"))
        buttons.append(row)
    
    buttons.append([Button.inline("🔙 Back to Countries", "browse_accounts")])
    return buttons

def create_admin_review_keyboard(account_id: str) -> List[List[Button]]:
    """Create admin review keyboard"""
    return [
        [Button.inline("✅ Approve", f"admin_approve_{account_id}"), Button.inline("❌ Reject", f"admin_reject_{account_id}")],
        [Button.inline("💰 Auto Price", f"auto_price_{account_id}"), Button.inline("🔍 Verify", f"admin_verify_{account_id}")],
        [Button.inline("📊 Quality Score", f"admin_quality_{account_id}"), Button.inline("🛡️ Security Check", f"admin_security_{account_id}")],
        [Button.inline("🔙 Back to Queue", "review_accounts")]
    ]

def create_payment_keyboard(listing_id: str) -> List[List[Button]]:
    """Create payment method keyboard"""
    return [
        [Button.inline("💳 UPI Payment", f"pay_upi_{listing_id}"), Button.inline("₿ Bitcoin", f"pay_bitcoin_{listing_id}")],
        [Button.inline("💎 USDT (TRC20)", f"pay_usdt_{listing_id}"), Button.inline("💰 Wallet", f"pay_wallet_{listing_id}")],
        [Button.inline("📱 Buy via OTP", f"pay_otp_{listing_id}"), Button.inline("🎫 Discount Code", f"discount_{listing_id}")],
        [Button.inline("🔙 Back to Account", "browse_accounts")]
    ]

def create_tos_keyboard() -> List[List[Button]]:
    """Create Terms of Service acceptance keyboard"""
    return [
        [Button.inline("✅ I Accept Terms", "accept_tos")],
        [Button.inline("❌ Cancel", "cancel_upload")]
    ]

def create_otp_method_keyboard() -> List[List[Button]]:
    """Create OTP method selection keyboard"""
    return [
        [Button.inline("📱 Use Phone + OTP", "use_phone_otp")],
        [Button.inline("🔙 Back to Menu", "back_to_main")]
    ]

def create_otp_verification_keyboard(user_id: int) -> List[List[Button]]:
    """Create OTP verification keyboard"""
    return [
        [Button.inline("🔄 Resend OTP", f"resend_otp_{user_id}"), Button.inline("❌ Cancel", "cancel_otp")]
    ]

def create_account_actions_keyboard(account_id: str) -> List[List[Button]]:
    """Create account action buttons"""
    return [
        [Button.inline("💰 Buy Now", f"buy_{account_id}"), Button.inline("❤️ Wishlist", f"wishlist_{account_id}")],
        [Button.inline("📊 View Details", f"details_{account_id}"), Button.inline("📱 Contact Seller", f"contact_{account_id}")],
        [Button.inline("🔙 Back to Browse", "browse_accounts")]
    ]

def create_seller_account_keyboard(account_id: str) -> List[List[Button]]:
    """Create seller account management buttons"""
    return [
        [Button.inline("✏️ Edit Price", f"edit_price_{account_id}"), Button.inline("📝 Edit Description", f"edit_desc_{account_id}")],
        [Button.inline("🗑️ Delete Listing", f"delete_{account_id}"), Button.inline("📊 View Stats", f"stats_{account_id}")],
        [Button.inline("🔙 Back to Listings", "my_accounts")]
    ]

def create_pagination_keyboard(current_page: int, total_pages: int, callback_prefix: str) -> List[List[Button]]:
    """Create pagination navigation buttons"""
    buttons = []
    
    nav_row = []
    if current_page > 1:
        nav_row.append(Button.inline("⬅️ Previous", f"{callback_prefix}_page_{current_page-1}"))
    
    nav_row.append(Button.inline(f"📄 {current_page}/{total_pages}", "current_page"))
    
    if current_page < total_pages:
        nav_row.append(Button.inline("➡️ Next", f"{callback_prefix}_page_{current_page+1}"))
    
    if nav_row:
        buttons.append(nav_row)
    
    return buttons

def create_support_keyboard() -> List[List[Button]]:
    """Create support and help buttons"""
    return [
        [Button.inline("🎫 Create Ticket", "create_ticket"), Button.inline("❓ FAQ", "faq")],
        [Button.inline("💬 Live Chat", "live_chat"), Button.inline("📞 Contact Admin", "contact_admin")],
        [Button.inline("🔙 Back to Menu", "back_to_main")]
    ]

def create_admin_pricing_keyboard() -> List[List[Button]]:
    """Create admin pricing management keyboard"""
    return [
        [Button.inline("💰 Set Buy Price", "set_country_buy_price"), Button.inline("💵 Set Sell Price", "set_country_sell_price")],
        [Button.inline("⚙️ Set Both Prices", "set_country_both_prices"), Button.inline("📈 View All Pricing", "view_country_pricing")],
        [Button.inline("📊 Pricing Stats", "pricing_stats"), Button.inline("🤖 AI Suggestions", "pricing_suggestions")],
        [Button.inline("🗑️ Delete Pricing", "delete_country_pricing"), Button.inline("🔙 Back", "admin_menu")]
    ]

def create_country_pricing_keyboard() -> List[List[Button]]:
    """Create country selection for pricing"""
    return [
        [Button.inline("🇺🇸 USA", "price_US"), Button.inline("🇮🇳 India", "price_IN"), Button.inline("🇬🇧 UK", "price_GB")],
        [Button.inline("🇨🇦 Canada", "price_CA"), Button.inline("🇦🇺 Australia", "price_AU"), Button.inline("🇩🇪 Germany", "price_DE")],
        [Button.inline("🇫🇷 France", "price_FR"), Button.inline("🇧🇷 Brazil", "price_BR"), Button.inline("🇷🇺 Russia", "price_RU")],
        [Button.inline("🔙 Back to Pricing", "admin_pricing")]
    ]

def create_country_action_keyboard(country: str) -> List[List[Button]]:
    """Create pricing action keyboard for specific country"""
    return [
        [Button.inline("💰 Set Buy Price", f"set_buy_{country}"), Button.inline("💵 Set Sell Price", f"set_sell_{country}")],
        [Button.inline("⚙️ Set Both Prices", f"set_both_{country}"), Button.inline("📊 View Current", f"view_{country}")],
        [Button.inline("🤖 AI Suggestion", f"suggest_{country}"), Button.inline("🗑️ Delete", f"delete_{country}")],
        [Button.inline("🔙 Back to Countries", "select_country_pricing")]
    ]

def create_payment_verification_keyboard(verification_id: str) -> List[List[Button]]:
    """Create payment verification keyboard for admin"""
    return [
        [Button.inline("✅ Approve Payment", f"approve_payment_{verification_id}"), Button.inline("❌ Reject Payment", f"reject_payment_{verification_id}")],
        [Button.inline("📊 View User Details", f"user_details_{verification_id}"), Button.inline("📝 Add Note", f"add_note_{verification_id}")],
        [Button.inline("🔙 Back to Queue", "payment_queue")]
    ]

def create_deposit_keyboard() -> List[List[Button]]:
    """Create deposit method keyboard"""
    return [
        [Button.inline("💳 UPI Deposit", "deposit_upi"), Button.inline("₿ Bitcoin Deposit", "deposit_bitcoin")],
        [Button.inline("💎 USDT Deposit", "deposit_usdt"), Button.inline("🏦 Bank Transfer", "deposit_bank")],
        [Button.inline("🔙 Back to Menu", "back_to_main")]
    ]

def create_balance_keyboard() -> List[List[Button]]:
    """Create balance management keyboard"""
    return [
        [Button.inline("💰 Add Funds", "add_funds"), Button.inline("📊 View History", "balance_history")],
        [Button.inline("💸 Withdraw", "withdraw_funds"), Button.inline("🔄 Refresh Balance", "refresh_balance")],
        [Button.inline("🔙 Back to Menu", "back_to_main")]
    ]

def format_account_message(account: Dict) -> str:
    """Format account information message"""
    country_flags = {'US': '🇺🇸', 'IN': '🇮🇳', 'GB': '🇬🇧', 'CA': '🇨🇦', 'AU': '🇦🇺', 'DE': '🇩🇪'}
    flag = country_flags.get(account.get('country', ''), '🌍')
    username = f"@{account.get('username')}" if account.get('username') else "No username"
    quality_stars = "⭐" * min(int(account.get('quality_score', 0) / 20), 5)
    
    return f"""
🔥 **Premium Telegram Account**

{flag} **Country:** {account.get('country', 'Unknown')}
📱 **Phone:** {account.get('phone', 'Hidden')}
👤 **Username:** {username}
📅 **Created:** {account.get('creation_year', 'Unknown')}
{quality_stars} **Quality:** {account.get('quality_score', 0)}/100
💰 **Price:** ${account.get('price', 0)}

✅ **Verified Account**
🛡️ **Secure Transfer**
🔒 **OTP Protected**
    """.strip()

def format_balance_message(balance: float, history: list) -> str:
    """Format user balance message"""
    recent_transactions = history[-5:] if history else []
    
    message = f"""
💰 **Your Balance**

💵 **Current Balance:** ${balance:.2f}

📈 **Recent Transactions:**
"""
    
    if recent_transactions:
        for tx in recent_transactions:
            emoji = "⬆️" if tx['type'] == 'deposit' else "⬇️"
            message += f"{emoji} ${tx['amount']:.2f} - {tx['method']} ({tx['timestamp'].strftime('%m/%d %H:%M')})\n"
    else:
        message += "No recent transactions\n"
    
    return message.strip()