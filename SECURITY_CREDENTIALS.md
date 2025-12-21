# Security Credentials Management

## Overview
This document outlines how credentials and sensitive information are managed in the Telegram Account Marketplace system.

## Credential Types

### 1. Telegram API Credentials
- **API_ID**: Telegram application ID
- **API_HASH**: Telegram application hash
- **BOT_TOKENS**: Telegram bot tokens for buyer, seller, and admin bots

**Storage**: Environment variables only
**Configuration**: Set in `.env` file (never commit to repository)

### 2. Database Credentials
- **MONGO_URI**: MongoDB connection string with credentials

**Storage**: Environment variables only
**Configuration**: Set in `.env` file

### 3. Encryption Keys
- **SESSION_ENCRYPTION_KEY**: 32-byte key for session encryption
- **WEBHOOK_SECRET**: Secret for webhook signature verification

**Storage**: Environment variables only
**Configuration**: Set in `.env` file

### 4. Payment Gateway Credentials

#### Razorpay
- **RAZORPAY_KEY_ID**: Razorpay API key ID
- **RAZORPAY_KEY_SECRET**: Razorpay API key secret
- **RAZORPAY_WEBHOOK_SECRET**: Razorpay webhook secret

**Storage**: Environment variables (for initial setup) → Database (for runtime)
**Configuration**: 
1. Set environment variables for initial deployment
2. Configure via Admin Bot interface for runtime changes
3. Stored encrypted in MongoDB admin_settings collection

#### Paytm
- **PAYTM_MERCHANT_KEY**: Paytm merchant key
- **PAYTM_MERCHANT_ID**: Paytm merchant ID
- **PAYTM_CALLBACK_URL**: Paytm callback URL

**Storage**: Environment variables only
**Configuration**: Set in `.env` file

#### UPI
- **Merchant VPA**: UPI ID (e.g., merchant@paytm)
- **Merchant Name**: Business name for UPI payments

**Storage**: Database only (admin_settings collection)
**Configuration**: Admin Bot interface only
**Note**: Never hardcode UPI credentials

#### Cryptocurrency
- **Wallet Addresses**: Bitcoin and USDT wallet addresses
- **API Keys**: Blockchain API keys for verification

**Storage**: Database only (admin_settings collection)
**Configuration**: Admin Bot interface only
**Note**: Never hardcode wallet addresses

### 5. Admin Configuration
- **ADMIN_USER_IDS**: Comma-separated list of admin Telegram user IDs

**Storage**: Environment variables only
**Configuration**: Set in `.env` file

## Security Best Practices

### 1. Environment Variables
- Never commit `.env` file to repository
- Use `.env.example` as template
- Rotate credentials regularly
- Use strong, random values for encryption keys

### 2. Database Storage
- Credentials stored in `admin_settings` collection are encrypted
- Only admin users can modify credentials via Admin Bot
- All credential changes are logged in audit trail

### 3. Credential Rotation
- Razorpay: Update via Admin Bot → Settings → Payment Settings → Razorpay Settings
- Paytm: Update environment variables and restart application
- UPI: Update via Admin Bot → Settings → UPI Settings
- Crypto: Update via Admin Bot → Settings → Crypto Settings

### 4. Audit Logging
All credential modifications are logged with:
- Admin user ID who made the change
- Timestamp of change
- Type of credential modified
- Previous and new values (masked for sensitive data)

### 5. Deployment Security
- Use secrets management service (AWS Secrets Manager, HashiCorp Vault, etc.)
- Never log sensitive credentials
- Use HTTPS for all external communications
- Implement rate limiting on payment endpoints

## Credential Validation

### Razorpay
- Key ID must start with `rzp_test_` or `rzp_live_`
- Key Secret must be at least 10 characters
- Webhook Secret must start with `whsec_`

### UPI
- Merchant VPA must contain `@` symbol
- Merchant Name must be at least 2 characters

### Cryptocurrency
- Wallet Address must be at least 20 characters
- API Key must be at least 10 characters

## Incident Response

If credentials are compromised:

1. **Immediate Actions**:
   - Revoke compromised credentials immediately
   - Generate new credentials
   - Update environment variables or database

2. **Razorpay**:
   - Revoke API keys in Razorpay dashboard
   - Generate new keys
   - Update via Admin Bot

3. **Paytm**:
   - Contact Paytm support to revoke credentials
   - Generate new credentials
   - Update environment variables
   - Restart application

4. **UPI/Crypto**:
   - Update via Admin Bot immediately
   - Monitor for unauthorized transactions

5. **Audit**:
   - Review logs for unauthorized access
   - Check transaction history
   - Document incident

## Testing

### Development
- Use test/sandbox credentials
- Set `PAYTM_WEBSITE=WEBSTAGING`
- Enable `SIMULATE_PAYMENTS=true`

### Production
- Use production credentials only
- Set `PAYTM_WEBSITE=WEBPROD`
- Disable `SIMULATE_PAYMENTS=false`
- Enable audit logging

## Compliance

- PCI DSS: Payment credentials handled securely
- GDPR: User data encrypted and access controlled
- SOC 2: Audit trails maintained for all credential changes

## References

- [Razorpay API Documentation](https://razorpay.com/docs/api/)
- [Paytm Integration Guide](https://paytm.com/business/payments)
- [UPI Specification](https://www.npci.org.in/upi-specification)
- [Environment Variables Best Practices](https://12factor.net/config)
