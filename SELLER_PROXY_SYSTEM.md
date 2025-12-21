# Seller Proxy System - Implementation Summary

## Overview
Added per-seller proxy system where sellers must add proxies for their accounts (1 proxy per 10 accounts) to prevent account freezing.

## Features Implemented

### 1. Proxy Prompt After Upload
- Shows after every account upload (session/OTP/TData)
- 2 buttons: "Add Proxy" and "Skip Proxy"
- Warning about account freezing if proxy not added

### 2. Proxy Requirements
- **1 proxy per 10 accounts**
- Supported types: SOCKS5, SOCKS4, HTTP
- **NOT supported:** MTProto (Telethon limitation)

### 3. Skip Warning Flow
When user clicks "Skip Proxy":
1. Shows confirmation dialog
2. Lists risks (account freeze, no payment)
3. Options: "Yes, Skip" or "No, Add Proxy"
4. Final warning before proceeding

### 4. Proxy Configuration
Format:
```
socks5://proxy.example.com:1080
socks5://user:pass@proxy.example.com:1080
http://proxy.example.com:8080
```

### 5. Database Schema

**seller_proxies collection:**
```javascript
{
  "seller_id": 123456789,
  "proxy_type": "socks5",
  "proxy_host": "proxy.example.com",
  "proxy_port": 1080,
  "proxy_username": "user",
  "proxy_password": "pass",
  "accounts_count": 5,  // Current usage
  "max_accounts": 10,   // Max capacity
  "created_at": ISODate()
}
```

**accounts collection (updated):**
```javascript
{
  ...existing fields...,
  "proxy_host": "proxy.example.com",
  "uses_proxy": true
}
```

## User Flow

### With Proxy (Recommended)
1. User uploads account
2. Bot shows: "✅ Session imported successfully!"
3. Proxy prompt appears with warning
4. User clicks "Add Proxy"
5. User sends proxy config
6. Bot validates and saves proxy
7. Verification starts with proxy

### Without Proxy (Risky)
1. User uploads account
2. Proxy prompt appears
3. User clicks "Skip Proxy"
4. Warning dialog: "Are you sure?"
5. User confirms skip
6. Bot warns: "No payment if frozen!"
7. Verification starts without proxy

## Key Points

### Warnings Shown
- ⚠️ Account can get frozen without proxy
- ❌ NO MONEY if account gets frozen
- 🔒 Proxy protects privacy and prevents freezing
- 📊 1 proxy needed per 10 accounts

### Proxy Management
- Tracks usage per proxy (accounts_count)
- Auto-selects available proxy slot
- Prompts for new proxy when capacity reached
- Links each account to its proxy

### Supported Formats
✅ SOCKS5 (recommended)
✅ SOCKS4
✅ HTTP
❌ MTProto (Telethon doesn't support)

## Files Modified

1. **app/models/SellerProxy.py** - New model for seller proxies
2. **app/models/__init__.py** - Export SellerProxy
3. **app/bots/SellerBot.py** - Added proxy prompt and handlers
   - `show_proxy_prompt()` - Shows proxy prompt
   - `handle_add_proxy()` - Handles add proxy
   - `handle_skip_proxy_confirm()` - Shows skip confirmation
   - `handle_skip_proxy_final()` - Final skip handler
   - `process_proxy_config()` - Processes proxy configuration

## Integration Points

### After Session Import
```python
account_id = login_result["account_id"]
await self.show_proxy_prompt(event.chat_id, user.telegram_user_id, account_id)
```

### After OTP Verification
```python
account_id = str(result.inserted_id)
await self.show_proxy_prompt(event.chat_id, user_id, account_id)
```

### After TData Import
```python
account_id = login_result["account_id"]
await self.show_proxy_prompt(event.chat_id, user.telegram_user_id, account_id)
```

## Usage Example

### Seller adds account:
```
User: [uploads session file]
Bot: ✅ Session imported successfully!

Bot: ⚠️ IMPORTANT: Proxy Required
     
     To protect your account from being frozen, you need to add a proxy.
     
     **1 proxy per 10 accounts**
     You need to add a proxy now.
     
     ❌ WARNING: If you skip and your account gets frozen, 
     NO MONEY will be added to your balance!
     
     [Add Proxy] [Skip Proxy]

User: [clicks Add Proxy]
Bot: Send proxy in format:
     socks5://proxy.example.com:1080

User: socks5://user:pass@proxy.example.com:1080
Bot: ✅ Proxy Added Successfully!
     Type: SOCKS5
     Host: proxy.example.com:1080
     Capacity: 1/10 accounts
     
     🔍 Starting verification with proxy...
```

### Seller skips proxy:
```
User: [clicks Skip Proxy]
Bot: ⚠️ WARNING: Skip Proxy?
     
     Are you sure you want to skip adding a proxy?
     
     **Risks:**
     ❌ Account may get frozen
     ❌ NO MONEY if account frozen
     
     [Yes, Skip] [No, Add Proxy]

User: [clicks Yes, Skip]
Bot: ⚠️ Proxy Skipped
     🔍 Starting verification without proxy...
     ⚠️ Remember: No payment if account gets frozen!
```

## Benefits

1. **Account Protection**: Proxies prevent account freezing
2. **Seller Awareness**: Clear warnings about risks
3. **Flexible**: Sellers can skip if they accept risks
4. **Scalable**: 1 proxy handles 10 accounts
5. **Cost-Effective**: Sellers only need 1 proxy per 10 accounts

## Future Enhancements

- Auto-detect when new proxy needed
- Proxy health monitoring
- Proxy rotation for better distribution
- Bulk proxy import for power sellers
- Proxy testing before verification
