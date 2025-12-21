"""Debug bot to test phone number processing"""
import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient, events
from app.services.SimpleOtpService import SimpleOtpService

load_dotenv()

async def main():
    api_id = int(os.getenv('API_ID'))
    api_hash = os.getenv('API_HASH')
    bot_token = os.getenv('SELLER_BOT_TOKEN')
    
    bot = TelegramClient('debug_bot', api_id, api_hash)
    
    user_states = {}
    # Single OTP service instance to maintain session context
    otp_service = SimpleOtpService(api_id, api_hash)
    
    @bot.on(events.NewMessage)
    async def handler(event):
        print(f"Received message from {event.sender_id}: {event.text}")
        user_id = event.sender_id
        
        if event.text == '/start':
            await event.reply("🔧 **Debug Bot Started**\n\nSend your phone number (e.g., +918459770125) to test OTP service")
            return
            
        if event.text and (event.text.startswith('+91') or event.text.startswith('+')):
            phone = event.text.strip()
            print(f"Processing phone: {phone}")
            
            await event.reply("📱 **Processing your phone number...**")
            
            # Use existing OTP service instance
            result = await otp_service.send_otp(phone, user_id)
            
            if result.get('success'):
                user_states[user_id] = {'phone': phone, 'awaiting_otp': True}
                await event.reply(f"✅ **OTP Sent!**\n\nPhone: {phone}\nPlease enter the OTP code:")
            else:
                await event.reply(f"❌ **Failed to send OTP**\n\n{result.get('error')}")
                
        elif user_id in user_states and user_states[user_id].get('awaiting_otp'):
            # Clean OTP code - remove spaces and keep only digits
            otp_code = ''.join(filter(str.isdigit, event.text.strip()))
            phone = user_states[user_id]['phone']
            print(f"Verifying OTP: {otp_code} for phone: {phone} (original: '{event.text.strip()}')")
            
            await event.reply("🔐 **Verifying OTP...**")
            
            # Use existing OTP service instance
            result = await otp_service.verify_otp(phone, otp_code, user_id)
            
            if result.get('success'):
                await event.reply(f"✅ **OTP Verified Successfully!**\n\nPhone: {phone}\nSession created!")
                user_states.pop(user_id, None)
            else:
                await event.reply(f"❌ **OTP Verification Failed**\n\n{result.get('error')}")
                
        else:
            await event.reply("Please send a phone number starting with + (e.g., +918459770125)")
    
    await bot.start(bot_token=bot_token)
    print("Debug bot started. Send your phone number...")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())