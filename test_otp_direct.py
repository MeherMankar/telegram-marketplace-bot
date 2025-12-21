"""Direct OTP test script"""
import asyncio
import os
from dotenv import load_dotenv
from app.services.SimpleOtpService import SimpleOtpService

load_dotenv()

async def test_otp():
    api_id = int(os.getenv('API_ID'))
    api_hash = os.getenv('API_HASH')
    
    print(f"API_ID: {api_id}")
    print(f"API_HASH: {api_hash[:10]}...")
    
    otp_service = SimpleOtpService(api_id, api_hash)
    
    # Test phone number - replace with your actual phone
    phone = input("Enter phone number (with country code, e.g., +1234567890): ")
    user_id = 123456  # Test user ID
    
    print(f"\nSending OTP to {phone}...")
    result = await otp_service.send_otp(phone, user_id)
    
    print(f"\nResult: {result}")
    
    if result.get('success'):
        print("\n✅ OTP sent successfully!")
        print(f"Code hash: {result.get('code_hash', 'N/A')[:20]}...")
        
        # Wait for OTP input
        otp_code = input("\nEnter the OTP code you received: ")
        
        print(f"\nVerifying OTP...")
        verify_result = await otp_service.verify_otp(phone, otp_code, user_id)
        
        print(f"\nVerification result: {verify_result}")
        
        if verify_result.get('success'):
            print("\n✅ OTP verified successfully!")
            print(f"Account info: {verify_result.get('account_info')}")
        elif verify_result.get('requires_password'):
            print("\n🔐 2FA detected! Enter your password...")
            password = input("Enter 2FA password: ")
            
            print(f"\nVerifying with password...")
            verify_result = await otp_service.verify_otp(phone, otp_code, user_id, password)
            
            if verify_result.get('success'):
                print("\n✅ OTP verified successfully with 2FA!")
                print(f"Account info: {verify_result.get('account_info')}")
            else:
                print(f"\n❌ Verification failed: {verify_result.get('error')}")
        else:
            print(f"\n❌ Verification failed: {verify_result.get('error')}")
    else:
        print(f"\n❌ Failed to send OTP: {result.get('error')}")
    
    # Cleanup
    await otp_service.cleanup_expired_sessions()

if __name__ == "__main__":
    asyncio.run(test_otp())
