# Proxy Support

The system now supports proxy connections for all Telegram operations, similar to Teleguard.

## Features

- **Multiple Proxy Types**: SOCKS5, SOCKS4, HTTP, MTProto
- **Admin UI**: Easy configuration through AdminBot
- **Automatic Application**: All bots and services use configured proxy
- **Connection Testing**: Test proxy before enabling
- **Secure Storage**: Proxy credentials stored in database

## Configuration

### Via Admin Bot

1. Start AdminBot and go to **Security Settings**
2. Click **Proxy Settings**
3. Click **Add Proxy**
4. Send proxy configuration in one of these formats:

**SOCKS5 (Recommended):**
```
socks5://proxy.example.com:1080
socks5://username:password@proxy.example.com:1080
```

**SOCKS4:**
```
socks4://proxy.example.com:1080
socks4://username:password@proxy.example.com:1080
```

**HTTP:**
```
http://proxy.example.com:8080
http://username:password@proxy.example.com:8080
```

**MTProto:**
```
mtproto://proxy.example.com:443?secret=abc123def456
```

### Test Proxy

After adding a proxy, click **Test Proxy** to verify the connection works before enabling it system-wide.

### Disable Proxy

Click **Disable Proxy** to stop using the proxy. The configuration is saved and can be re-enabled later.

## How It Works

1. **BaseBot**: All bots inherit from BaseBot which checks for proxy configuration on startup
2. **OtpService**: Session creation uses proxy for OTP verification
3. **CodeInterceptor**: Code interception sessions use proxy
4. **Database Storage**: Proxy settings stored in `proxy_settings` collection

## Supported Operations

All Telegram operations use the configured proxy:
- Bot connections (Seller, Buyer, Admin)
- OTP verification and session creation
- Account verification
- Code interception
- Message sending/receiving

## Security Notes

- Proxy credentials are stored in MongoDB
- Use trusted proxy servers only
- MTProto proxies provide additional encryption
- Test mode recommended before production use

## Restart Required

After adding or changing proxy settings, **restart all bots** to apply the new configuration:

```bash
# Stop current instance
Ctrl+C

# Restart
python main.py
```

## Troubleshooting

**Connection fails after enabling proxy:**
- Verify proxy server is online
- Check proxy credentials are correct
- Test with a simple SOCKS5 proxy first
- Check firewall rules

**Proxy works but slow:**
- Try different proxy server
- Check proxy server location (closer is faster)
- Consider using MTProto proxy for better performance

**MTProto proxy not working:**
- Verify secret is correct (hex string)
- Ensure MTProto proxy server supports Telegram
- Check port is correct (usually 443)

## Example Proxy Providers

**Free Options:**
- Public SOCKS5 proxies (not recommended for production)
- Tor SOCKS5 proxy (localhost:9050)

**Paid Options:**
- Bright Data
- Oxylabs
- SmartProxy
- Dedicated VPS with proxy setup

**MTProto Proxies:**
- Public MTProto proxies from Telegram channels
- Self-hosted MTProto proxy (MTProtoProxy)

## Database Schema

```javascript
{
  "proxy_type": "socks5",  // socks5, socks4, http, mtproto
  "proxy_host": "proxy.example.com",
  "proxy_port": 1080,
  "proxy_username": "user",  // optional
  "proxy_password": "pass",  // optional
  "proxy_secret": "abc123",  // for mtproto only
  "enabled": true,
  "created_at": ISODate("2025-01-01T00:00:00Z"),
  "updated_at": ISODate("2025-01-01T00:00:00Z")
}
```

## API Reference

### ProxyManager

```python
from app.models import ProxyManager, ProxySettings

# Initialize
proxy_manager = ProxyManager(db_connection)

# Get active proxy
proxy = await proxy_manager.get_proxy()

# Set proxy
proxy = ProxySettings(
    proxy_type="socks5",
    proxy_host="proxy.example.com",
    proxy_port=1080,
    proxy_username="user",
    proxy_password="pass",
    enabled=True
)
await proxy_manager.set_proxy(proxy)

# Get Telethon-compatible dict
proxy_dict = await proxy_manager.get_proxy_dict()

# Disable proxy
await proxy_manager.disable_proxy()
```

### Using in Custom Code

```python
from telethon import TelegramClient
from app.models import ProxyManager

# Get proxy configuration
proxy_manager = ProxyManager(db_connection)
proxy = await proxy_manager.get_proxy_dict()

# Create client with proxy
client = TelegramClient(
    session_name,
    api_id,
    api_hash,
    proxy=proxy  # None if no proxy configured
)
```

## Benefits

1. **Privacy**: Hide your server's IP address
2. **Bypass Restrictions**: Access Telegram from restricted networks
3. **Load Distribution**: Use multiple proxies for different operations
4. **Geo-Location**: Appear from different countries
5. **Rate Limit Bypass**: Distribute requests across proxies

## Best Practices

1. Always test proxy before enabling
2. Use SOCKS5 for best compatibility
3. Keep proxy credentials secure
4. Monitor proxy performance
5. Have backup proxy ready
6. Document proxy configuration
7. Rotate proxies periodically for security
