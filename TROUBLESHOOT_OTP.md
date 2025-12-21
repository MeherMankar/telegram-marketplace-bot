# OTP Troubleshooting Guide

## Issue: Not receiving OTP from Telegram

### Quick Test
Run the direct test script:
```bash
python test_otp_direct.py
```

### Common Issues & Solutions

#### 1. **API Credentials Invalid**
- Check `.env` file has correct `API_ID` and `API_HASH`
- Verify credentials at https://my.telegram.org/apps
- Make sure there are no extra spaces or quotes

#### 2. **Phone Number Format**
- Must start with `+` and country code
- Examples: `+1234567890`, `+919876543210`
- No spaces, dashes, or parentheses

#### 3. **Telegram Rate Limiting**
- Telegram limits code requests per phone number
- Wait 5-10 minutes between attempts
- Try with a different phone number

#### 4. **Network/Firewall Issues**
- Check if Telegram servers are accessible
- Try disabling VPN/proxy temporarily
- Check firewall isn't blocking Telegram connections

#### 5. **Bot Not Running**
- Ensure seller bot is started: `python main.py`
- Check logs for errors
- Verify MongoDB connection is working

### Debug Steps

1. **Check Logs**
   - Look for `[OTP_SERVICE]` messages in console
   - Check for connection errors
   - Look for "Code sent!" message

2. **Test Direct Connection**
   ```bash
   python test_otp_direct.py
   ```

3. **Verify Bot State**
   - After clicking "Phone + OTP", check if state is set to `awaiting_phone_otp`
   - After entering phone, check logs for "Processing phone number" message

4. **Check Database**
   - Verify user state in MongoDB users collection
   - Check if `temp_phone` is stored after entering phone number

### Expected Flow

1. User clicks "Sell via OTP" → "Phone + OTP"
2. Bot sets state to `awaiting_phone_otp`
3. User sends phone number (e.g., `+1234567890`)
4. Bot calls `process_phone_number()`
5. OTP service creates Telegram client
6. Client connects to Telegram
7. Client sends code request
8. Telegram sends OTP to phone
9. Bot shows "OTP Sent Successfully" message

### Error Messages

- **"Invalid phone number format"**: Use international format with `+` and country code
- **"Failed to connect to Telegram"**: Network/firewall issue
- **"Too many requests"**: Rate limited, wait and try again
- **"Phone number banned"**: This number is banned from Telegram
- **"Failed to send OTP"**: Check API credentials and network

### Still Not Working?

1. Check if you can receive OTP using official Telegram app
2. Try with a different phone number
3. Verify API_ID and API_HASH are correct
4. Check MongoDB connection
5. Review full error logs
