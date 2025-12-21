# Country-Based Proxy System - Updated

## Overview
Sellers must add country-specific proxies BEFORE uploading accounts. The system detects the country and prompts for matching proxy.

## Flow

### Upload Flow
1. User clicks "Upload Account"
2. Bot asks: "Select Account Country" (India, USA, UK, etc.)
3. User selects country (e.g., 🇮🇳 India)
4. Bot shows: "⚠️ PROXY REQUIRED FOR 🇮🇳 India ACCOUNT"
5. User adds Indian proxy or skips (with warning)
6. User uploads session file/string

### OTP Flow
1. User clicks "Sell via OTP"
2. User enters phone number (e.g., +91987654321)
3. Bot detects country from phone (India)
4. Bot shows: "⚠️ PROXY REQUIRED FOR 🇮🇳 India ACCOUNT"
5. User adds Indian proxy or skips (with warning)
6. Bot sends OTP and continues

## Country Detection

### From Phone Number
```python
+91... → India
+1...  → USA
+44... → UK
+61... → Australia
+49... → Germany
+33... → France
+7...  → Russia
+86... → China
```

### Manual Selection
- 🇮🇳 India
- 🇺🇸 USA
- 🇬🇧 UK
- 🇨🇦 Canada
- 🇦🇺 Australia
- 🇩🇪 Germany
- 🌐 Other

## Proxy Prompt

```
⚠️ PROXY REQUIRED FOR 🇮🇳 India ACCOUNT

You're adding a 🇮🇳 India account.
**You need a 🇮🇳 India proxy!**

**Why Proxy?**
• Prevents account freezing
• Matches account location
• Required for verification

**Supported Types:**
• SOCKS5 (recommended)
• SOCKS4
• HTTP

❌ MTProto NOT supported

**1 proxy per 10 accounts**

⚠️ WARNING: If you skip and account gets frozen, 
NO MONEY will be added!

[➕ Add India Proxy] [⏭️ Skip (Risky)]
```

## Skip Warning

```
⚠️ WARNING: Skip Proxy?

**Risks:**
❌ Account may get frozen
❌ Verification may fail
❌ NO MONEY if account frozen

[✅ Yes, Skip] [❌ No, Add Proxy]
```

## Example Usage

### Indian Account with Proxy
```
User: [clicks Upload Account]
Bot: Select Account Country
User: [clicks 🇮🇳 India]
Bot: ⚠️ PROXY REQUIRED FOR 🇮🇳 India ACCOUNT
     You need a 🇮🇳 India proxy!
     [Add India Proxy] [Skip]

User: [clicks Add India Proxy]
Bot: Send your 🇮🇳 India proxy:
User: socks5://user:pass@india-proxy.com:1080
Bot: ✅ India Proxy Added!
     Type: SOCKS5
     Host: india-proxy.com:1080
     
     📤 Now Upload Your Account
     
User: [uploads session]
Bot: ✅ Session imported!
     🔍 Starting verification with India proxy...
```

### US Account via OTP
```
User: [clicks Sell via OTP]
Bot: Enter Your Phone Number
User: +1234567890
Bot: ⚠️ PROXY REQUIRED FOR 🇺🇸 USA ACCOUNT
     Detected: 🇺🇸 USA account
     Phone: +1234567890
     You need a 🇺🇸 USA proxy!
     [Add USA Proxy] [Skip]

User: [clicks Add USA Proxy]
Bot: Send your 🇺🇸 USA proxy:
User: socks5://us-proxy.com:1080
Bot: ✅ USA Proxy Added!
     
     📱 Sending OTP...
```

## Benefits

1. **Country Matching**: Proxy matches account location
2. **Early Warning**: User knows proxy needed before upload
3. **Auto-Detection**: Phone numbers auto-detect country
4. **Clear Labels**: Country flags and names everywhere
5. **Prevents Issues**: Matching proxy prevents freezing

## Technical Details

### Country Detection Function
```python
def detect_country_from_phone(self, phone):
    phone = phone.strip().replace("+", "")
    if phone.startswith("91"): return "IN"
    elif phone.startswith("1"): return "US"
    elif phone.startswith("44"): return "GB"
    # ... more countries
```

### Proxy Storage
```javascript
{
  "seller_id": 123456789,
  "proxy_type": "socks5",
  "proxy_host": "india-proxy.com",
  "proxy_port": 1080,
  "accounts_count": 0,
  "max_accounts": 10
}
```

### User Temp Data
```javascript
{
  "temp_country": "IN",
  "temp_phone": "+91987654321",
  "temp_proxy_host": "india-proxy.com",
  "has_proxy": true
}
```

## Key Changes from Previous Version

❌ **Before**: Proxy prompt AFTER account upload
✅ **Now**: Proxy prompt BEFORE account upload

❌ **Before**: Generic proxy prompt
✅ **Now**: Country-specific proxy prompt

❌ **Before**: No country detection
✅ **Now**: Auto-detects from phone number

❌ **Before**: No country selection
✅ **Now**: Manual country selection for uploads

This ensures sellers add the RIGHT proxy for the RIGHT country BEFORE uploading!
