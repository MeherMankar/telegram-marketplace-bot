#!/usr/bin/env python3
"""
Script to test session upload and verification flow
"""
import asyncio
import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import init_db, db
from app.services import VerificationService
from app.utils import SessionImporter
from unittest.mock import AsyncMock, patch
from datetime import datetime

load_dotenv()

async def test_session_upload_flow():
    """Test the complete session upload and verification flow"""
    try:
        await init_db()
        
        print("🧪 Testing session upload flow...")
        
        # Step 1: Test session import
        print("\n1️⃣ Testing session import...")
        session_importer = SessionImporter()
        
        # Test with mock session string
        mock_session_string = "mock_session_string_for_testing"
        
        with patch('app.utils.session_importer.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.connect = AsyncMock()
            mock_client.is_user_authorized = AsyncMock(return_value=True)
            mock_client.disconnect = AsyncMock()
            
            # Mock get_me response
            mock_me = AsyncMock()
            mock_me.id = 123456789
            mock_me.username = "testuser"
            mock_me.first_name = "Test"
            mock_me.last_name = "User"
            mock_me.phone = "+1234567890"
            mock_client.get_me = AsyncMock(return_value=mock_me)
            
            # Mock session save
            mock_client.session.save = AsyncMock(return_value=mock_session_string)
            
            import_result = await session_importer.import_session(session_string=mock_session_string)
            
            if import_result and import_result.get("success"):
                print("✅ Session import successful")
                print(f"   Account ID: {import_result['account_info']['id']}")
                print(f"   Username: {import_result['account_info']['username']}")
            else:
                print(f"❌ Session import failed: {import_result.get('error', 'Unknown error')}")
                return
        
        # Step 2: Test account creation
        print("\n2️⃣ Testing account creation...")
        
        account_data = {
            "seller_id": 987654321,
            "telegram_account_id": import_result["account_info"]["id"],
            "username": import_result["account_info"]["username"],
            "first_name": import_result["account_info"]["first_name"],
            "last_name": import_result["account_info"]["last_name"],
            "phone_number": import_result["account_info"]["phone"],
            "session_string": import_result["session_string"],
            "status": "pending",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = await self.db_connection.accounts.insert_one(account_data)
        account_id = str(result.inserted_id)
        print(f"✅ Account created with ID: {account_id}")
        
        # Step 3: Test verification
        print("\n3️⃣ Testing verification...")
        
        verification_service = VerificationService()
        
        with patch('app.services.verification_service.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.connect = AsyncMock()
            mock_client.is_user_authorized = AsyncMock(return_value=True)
            mock_client.disconnect = AsyncMock()
            mock_client.get_me = AsyncMock(return_value=mock_me)
            
            # Mock verification methods
            mock_client.get_contacts = AsyncMock(return_value=[])  # Zero contacts
            mock_client.get_dialogs = AsyncMock(return_value=[])  # No dialogs
            mock_client.send_message = AsyncMock()
            mock_client.get_messages = AsyncMock(return_value=[])
            mock_client.get_permissions = AsyncMock()
            
            verification_result = await verification_service.verify_account(
                import_result["session_string"], 
                account_id
            )
            
            print(f"✅ Verification completed: {verification_result['overall_status']}")
            
            # Print check results
            for check_name, check_result in verification_result["checks"].items():
                status = "✅" if check_result.get("passed", False) else "❌"
                print(f"   {status} {check_name.replace('_', ' ').title()}")
        
        # Step 4: Update account with verification results
        print("\n4️⃣ Updating account with verification results...")
        
        update_data = {
            "checks": verification_result["checks"],
            "verification_logs": verification_result["logs"],
            "status": "approved" if verification_result["overall_status"] == "passed" else "rejected",
            "country": verification_result["checks"].get("country", {}).get("country", "unknown"),
            "creation_year": verification_result["checks"].get("creation_year", {}).get("year", 2024),
            "updated_at": datetime.utcnow()
        }
        
        await self.db_connection.accounts.update_one({"_id": account_id}, {"$set": update_data})
        print("✅ Account updated with verification results")
        
        # Step 5: Test admin approval simulation
        print("\n5️⃣ Testing admin approval...")
        
        if verification_result["overall_status"] == "passed":
            # Simulate admin approval
            price = 40.0  # Default price for testing
            
            await self.db_connection.accounts.update_one(
                {"_id": account_id},
                {
                    "$set": {
                        "status": "approved",
                        "price": price,
                        "admin_reviewer_id": 111222333,  # Mock admin ID
                        "reviewed_at": datetime.utcnow()
                    }
                }
            )
            
            # Create marketplace listing
            listing_data = {
                "account_id": account_id,
                "seller_id": account_data["seller_id"],
                "country": update_data["country"],
                "creation_year": update_data["creation_year"],
                "price": price,
                "status": "active",
                "created_at": datetime.utcnow()
            }
            
            listing_result = await self.db_connection.listings.insert_one(listing_data)
            listing_id = str(listing_result.inserted_id)
            
            print(f"✅ Account approved and listed with ID: {listing_id}")
            print(f"   Price: ${price}")
            print(f"   Country: {update_data['country']}")
            print(f"   Creation Year: {update_data['creation_year']}")
        else:
            print("❌ Account failed verification, not approved")
        
        print("\n🎉 Test session upload flow completed successfully!")
        
        # Clean up test data
        print("\n🧹 Cleaning up test data...")
        await self.db_connection.accounts.delete_one({"_id": account_id})
        if 'listing_id' in locals():
            await self.db_connection.listings.delete_one({"_id": listing_id})
        print("✅ Test data cleaned up")
        
    except Exception as e:
        print(f"❌ Error in test session upload flow: {str(e)}")
        import traceback
        traceback.print_exc()

async def main():
    """Main test function"""
    print("🧪 Starting session upload flow test...")
    await test_session_upload_flow()

if __name__ == "__main__":
    asyncio.run(main())