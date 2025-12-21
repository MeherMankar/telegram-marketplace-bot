#!/usr/bin/env python3
"""Quick proxy setup script"""
import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from app.models.ProxySettings import ProxySettings, ProxyManager
from dotenv import load_dotenv
import os

load_dotenv()

async def setup_proxy():
    """Interactive proxy setup"""
    print("🌐 Proxy Setup Wizard\n")
    
    # Connect to database
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/telegram_marketplace')
    client = AsyncIOMotorClient(mongo_uri)
    db = client.get_database()
    proxy_manager = ProxyManager(db)
    
    # Get current proxy
    current = await proxy_manager.get_proxy()
    if current and current.enabled:
        print(f"✅ Current proxy: {current.proxy_type}://{current.proxy_host}:{current.proxy_port}")
        choice = input("\nDisable current proxy? (y/n): ").lower()
        if choice == 'y':
            await proxy_manager.disable_proxy()
            print("✅ Proxy disabled")
            return
    
    # Proxy type
    print("\nSelect proxy type:")
    print("1. SOCKS5 (recommended)")
    print("2. SOCKS4")
    print("3. HTTP")
    print("4. MTProto")
    
    type_choice = input("\nChoice (1-4): ").strip()
    proxy_types = {'1': 'socks5', '2': 'socks4', '3': 'http', '4': 'mtproto'}
    proxy_type = proxy_types.get(type_choice, 'socks5')
    
    # Host and port
    host = input("\nProxy host (e.g., proxy.example.com): ").strip()
    port = int(input("Proxy port (e.g., 1080): ").strip())
    
    # Credentials
    username = None
    password = None
    secret = None
    
    if proxy_type == 'mtproto':
        secret = input("MTProto secret: ").strip()
    else:
        has_auth = input("\nDoes proxy require authentication? (y/n): ").lower()
        if has_auth == 'y':
            username = input("Username: ").strip()
            password = input("Password: ").strip()
    
    # Create proxy settings
    proxy = ProxySettings(
        proxy_type=proxy_type,
        proxy_host=host,
        proxy_port=port,
        proxy_username=username,
        proxy_password=password,
        proxy_secret=secret,
        enabled=True
    )
    
    # Save
    await proxy_manager.set_proxy(proxy)
    
    print(f"\n✅ Proxy configured successfully!")
    print(f"   Type: {proxy_type}")
    print(f"   Host: {host}:{port}")
    print(f"\n⚠️  Restart bots to apply changes: python main.py")
    
    client.close()

if __name__ == "__main__":
    try:
        asyncio.run(setup_proxy())
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
