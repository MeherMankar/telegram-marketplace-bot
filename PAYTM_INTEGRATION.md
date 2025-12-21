# Paytm Payment Gateway Integration

## Overview
Replaced Razorpay with Paytm as the primary payment gateway. Supports automatic payment verification with manual UPI fallback.

---

## Setup Instructions

### 1. Get Paytm Credentials

1. Visit [Paytm Business](https://business.paytm.com)
2. Sign up or login to your account
3. Go to Settings → API Keys
4. Copy your:
   - Merchant ID
   - Merchant Key
   - Website name (WEBSTAGING for testing, WEBPROD for production)

### 2. Configure Environment Variables

Add to `.env`:
```env
PAYTM_MERCHANT_ID=your_merchant_id
PAYTM_MERCHANT_KEY=your_merchant_key
PAYTM_WEBSITE=WEBSTAGING
PAYTM_CALLBACK_URL=https://yourdomain.com/webhook/paytm
WEBHOOK_SECRET=your-secure-webhook-secret
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Payment Methods

### 1. Paytm Wallet (Auto-verified)
- **Fee**: 1% processing fee
- **Verification**: Automatic via Paytm callback
- **Status**: Instant confirmation
- **Screenshot**: Not required

### 2. Direct UPI (Manual verification)
- **Fee**: No fee
- **Verification**: Manual admin review
- **Status**: Pending admin approval
- **Screenshot**: Required

### 3. Cryptocurrency (Manual verification)
- **Fee**: 1.5% processing fee
- **Verification**: Manual admin review
- **Status**: Pending admin approval
- **Screenshot**: Not required

---

## Payment Flow

### Paytm Payment Flow
```
1. User selects Paytm payment
2. System creates payment order
3. User redirected to Paytm gateway
4. User completes payment on Paytm
5. Paytm sends callback to webhook
6. System verifies checksum
7. Payment marked as verified
8. User notified of success
9. Account transferred to buyer
```

### UPI Payment Flow
```
1. User selects UPI payment
2. System creates payment order
3. User uploads payment screenshot
4. Admin reviews screenshot
5. Admin approves/rejects payment
6. User notified of result
7. If approved, account transferred
```

---

## API Integration

### Create Payment Order

```python
from app.services.PaymentService import PaymentService

payment_service = PaymentService(db_connection)

result = await payment_service.create_payment_order(
    user_id=123,
    base_amount=500.0,
    payment_method="paytm",
    user_email="user@example.com",
    user_phone="+919876543210"
)

if result.get("paytm_data"):
    # Redirect user to Paytm payment page
    payment_data = result["paytm_data"]
    payment_url = result["payment_url"]
```

### Handle Paytm Callback

The webhook automatically handles Paytm callbacks:
```
POST /webhook/paytm
```

Paytm will send:
- ORDER_ID
- TXNID (Transaction ID)
- STATUS (TXN_SUCCESS or TXN_FAILURE)
- CHECKSUMHASH (for verification)

### Verify Payment Status

```python
verification = await payment_service.paytm_service.verify_payment(
    order_id="PAY20240115123456",
    transaction_id="20240115123456"
)
```

---

## Checksum Verification

Paytm uses HMAC-SHA256 checksums for security:

```python
# Checksum is automatically verified in callback handler
# All parameters are sorted and concatenated
# HMAC-SHA256 hash is computed with merchant key
# Received checksum is compared with computed checksum
```

---

## Testing

### Staging Environment
- Use `PAYTM_WEBSITE=WEBSTAGING`
- Test credentials provided by Paytm
- No real money involved

### Test Cards
Paytm provides test cards for staging:
- Visa: 4111111111111111
- Mastercard: 5555555555554444
- Debit: 6011111111111117

### Test Callback
```bash
curl -X POST http://localhost:8000/webhook/paytm \
  -d "ORDER_ID=PAY20240115123456" \
  -d "TXNID=20240115123456" \
  -d "STATUS=TXN_SUCCESS" \
  -d "CHECKSUMHASH=<computed_hash>"
```

---

## Production Deployment

### 1. Update Configuration
```env
PAYTM_WEBSITE=WEBPROD
PAYTM_CALLBACK_URL=https://yourdomain.com/webhook/paytm
```

### 2. SSL Certificate
- Ensure HTTPS is enabled
- Paytm requires secure callback URLs

### 3. Webhook Endpoint
- Must be publicly accessible
- Must handle POST requests
- Must verify checksums

### 4. Error Handling
- Implement retry logic for failed payments
- Log all payment transactions
- Monitor webhook failures

---

## Troubleshooting

### Checksum Mismatch
- Verify merchant key is correct
- Check parameter order (must be sorted)
- Ensure no extra spaces in parameters

### Callback Not Received
- Verify callback URL is correct
- Check firewall/security groups
- Ensure webhook endpoint is accessible
- Check logs for errors

### Payment Verification Failed
- Verify order exists in database
- Check transaction ID format
- Ensure merchant credentials are correct

### Test Payment Not Working
- Use staging credentials
- Use test card numbers
- Check merchant ID and key
- Verify website parameter

---

## Security Considerations

1. **Checksum Verification**: Always verify checksums before processing
2. **HTTPS Only**: Use HTTPS for all payment URLs
3. **Merchant Key**: Never expose merchant key in client-side code
4. **Webhook Secret**: Use strong webhook secret for additional security
5. **Rate Limiting**: Implement rate limiting on webhook endpoint
6. **Logging**: Log all payment transactions for audit trail

---

## Migration from Razorpay

### Changes Made
1. Replaced Razorpay with Paytm in payment methods
2. Updated fee structure (1% for Paytm vs 2% for Razorpay)
3. Changed auto-verification logic
4. Updated webhook handler
5. Modified payment form generation

### Backward Compatibility
- UPI payment method remains unchanged
- Cryptocurrency payment method remains unchanged
- Manual verification process unchanged
- Database schema compatible

---

## Support

For Paytm support:
- [Paytm Business Help](https://business.paytm.com/help)
- [Paytm API Documentation](https://developer.paytm.com)
- [Paytm Support Email](support@paytm.com)

For integration issues:
- Check logs in `logs/app.log`
- Verify environment variables
- Test with staging credentials first
- Review webhook endpoint accessibility

