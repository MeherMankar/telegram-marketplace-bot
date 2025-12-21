"""Check if we can connect to Telegram"""
import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

async def test_connection():
    api_id = int(os.getenv('API_ID'))
    api_hash = os.getenv('API_HASH')
    
    print(f"Testing Telegram connection...")
    print(f"API_ID: {api_id}")
    print(f"API_HASH: {api_hash[:10]}...")
    
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    try:
        print("\nConnecting to Telegram...")
        await client.connect()
        
        if client.is_connected():
            print("✅ Connected to Telegram successfully!")
            
            # Try to send code request
            phone = input("\nEnter phone number to test (e.g., +918459770125): ")
            print(f"\nSending code request to {phone}...")
            
            sent_code = await client.send_code_request(phone)
            print(f"✅ Code request sent successfully!")
            print(f"Code hash: {sent_code.phone_code_hash}")
            print(f"\n🔔 CHECK YOUR TELEGRAM APP NOW!")
            print(f"You should see a login code message.")
            print(f"The code is valid for 5 minutes.")
            
        else:
            print("❌ Failed to connect to Telegram")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(test_connection())
