"""Test the simplified OTP service"""
import asyncio
import os
from dotenv import load_dotenv
from app.services.SimpleOtpService import SimpleOtpService

load_dotenv()

async def test_otp():
    api_id = int(os.getenv('API_ID'))
    api_hash = os.getenv('API_HASH')
    
    otp_service = SimpleOtpService(api_id, api_hash)
    
    phone = "+918459770125"
    user_id = 123456789
    
    print(f"Testing OTP service with phone: {phone}")
    
    # Send OTP
    result = await otp_service.send_otp(phone, user_id)
    print(f"OTP send result: {result}")
    
    if result.get('success'):
        print("[SUCCESS] OTP sent successfully!")
        print("\nCheck your phone for the OTP code and enter it below:")
        otp_code = input("Enter OTP code: ").strip()
        
        # Verify OTP
        verify_result = await otp_service.verify_otp(user_id, otp_code)
        print(f"OTP verify result: {verify_result}")
        
        if verify_result.get('success'):
            print("[SUCCESS] OTP verification successful!")
            account_info = verify_result.get('account_info', {})
            print(f"Account: {account_info.get('first_name')} {account_info.get('last_name')}")
            print(f"Phone: {account_info.get('phone')}")
            print(f"Username: @{account_info.get('username', 'None')}")
        else:
            print(f"[ERROR] OTP verification failed: {verify_result.get('error')}")
    else:
        print(f"[ERROR] OTP send failed: {result.get('error')}")

if __name__ == "__main__":
    asyncio.run(test_otp())