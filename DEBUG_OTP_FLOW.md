# OTP Flow Debug Analysis

## Expected Flow:
1. User sends `/start` → Shows main menu with "📱 Sell via OTP" button
2. User clicks "📱 Sell via OTP" → Triggers `handle_sell_via_otp()` → Shows method selection
3. User clicks "📱 Use Phone + OTP" → Triggers `handle_use_phone_otp()` → Sets state to `awaiting_phone_otp`
4. User sends phone number → `handle_text()` detects state → Calls `process_phone_number()`
5. OTP sent → State changes to `awaiting_otp_code`
6. User sends OTP → `handle_text()` detects state → Calls `process_otp_code()`

## Buttons:
- Main menu: `sell_via_otp` ✅
- Method selection: `use_phone_otp` ✅
- Both buttons exist in keyboards.py ✅

## State Flow:
- Initial: `None`
- After clicking "Use Phone + OTP": `awaiting_phone_otp`
- After sending phone: `awaiting_otp_code`
- After sending OTP: `awaiting_2fa_password` (if 2FA enabled)

## Potential Issues:
1. State not being set properly in `handle_use_phone_otp()`
2. Text handler not detecting the state
3. Database update not persisting
4. Race condition between state set and text message

## Test Steps:
1. Send `/start`
2. Send `/debug` → Should show state: None
3. Click "📱 Sell via OTP"
4. Send `/debug` → Should still show state: None (no state set yet)
5. Click "📱 Use Phone + OTP"
6. Send `/debug` → Should show state: awaiting_phone_otp
7. Send phone number
8. Check logs for "PHONE OTP FLOW STARTED"
