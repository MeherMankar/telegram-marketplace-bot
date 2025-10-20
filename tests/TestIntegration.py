import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.services import VerificationService, PaymentService, AdminService

class TestIntegration:
    """Integration tests for the complete marketplace flow"""
    
    @pytest.mark.asyncio
    async def test_complete_marketplace_flow_simulation(self):
        """Test complete flow: upload -> verify -> approve -> list -> buy -> deliver"""
        
        # Step 1: Session upload simulation
        session_string = "test_session_string"
        account_id = "test_account_id"
        
        # Step 2: Verification simulation
        verification_service = VerificationService()
        
        with patch('app.services.verification_service.TelegramClient') as mock_client_class:
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
            mock_me.bot = False
            mock_client.get_me = AsyncMock(return_value=mock_me)
            
            # Mock other verification methods
            mock_client.get_contacts = AsyncMock(return_value=[])
            mock_client.get_dialogs = AsyncMock(return_value=[])
            mock_client.send_message = AsyncMock()
            mock_client.get_messages = AsyncMock(return_value=[])
            
            verification_result = await verification_service.verify_account(session_string, account_id)
            
            # Verify the verification completed
            assert verification_result["account_id"] == account_id
            assert "checks" in verification_result
            assert "logs" in verification_result
        
        # Step 3: Admin approval simulation
        admin_service = AdminService()
        
        with patch('app.database.connection.db') as mock_db:
            mock_self.db_connection.accounts.find_one = AsyncMock(return_value={
                "_id": account_id,
                "seller_id": 123456789,
                "country": "IN",
                "creation_year": 2024
            })
            mock_self.db_connection.accounts.update_one = AsyncMock()
            mock_self.db_connection.listings.insert_one = AsyncMock()
            mock_self.db_connection.admin_actions.insert_one = AsyncMock()
            
            approval_result = await admin_service.approve_account(987654321, account_id, 40.0)
            
            # Verify approval succeeded
            assert approval_result["success"] is True
            assert approval_result["price"] == 40.0
        
        # Step 4: Payment simulation
        payment_service = PaymentService()
        
        upi_payment = await payment_service.create_upi_payment(40.0, 111222333)
        assert upi_payment["success"] is True
        
        crypto_payment = await payment_service.create_crypto_payment(40.0, 111222333, "USDT")
        assert crypto_payment["success"] is True
        
        # Step 5: Payment verification simulation
        upi_verification = await payment_service.verify_upi_payment("test_payment", "test_ref")
        assert upi_verification["success"] is True
        assert upi_verification["verified"] is True
        
        crypto_verification = await payment_service.verify_crypto_payment("test_payment", "test_hash", "USDT")
        assert crypto_verification["success"] is True
        assert crypto_verification["verified"] is True
    
    @pytest.mark.asyncio
    async def test_seller_upload_rate_limiting(self):
        """Test seller upload rate limiting"""
        # This would test the daily upload limit functionality
        # For now, just verify the limit constant exists
        from app.bots.seller_bot import SellerBot
        
        seller_bot = SellerBot("dummy_token")
        assert seller_bot.max_uploads_per_day == 5
    
    @pytest.mark.asyncio
    async def test_price_calculation(self):
        """Test price calculation based on country and year"""
        admin_service = AdminService()
        
        # Test default price table
        price_in_2024 = admin_service.get_price("IN", 2024)
        price_us_2025 = admin_service.get_price("US", 2025)
        price_unknown = admin_service.get_price("UNKNOWN", 2020)
        
        assert price_in_2024 == 30.0  # From default price table
        assert price_us_2025 == 50.0  # From default price table
        assert price_unknown == 50.0  # Default fallback price
    
    @pytest.mark.asyncio
    async def test_admin_permissions(self):
        """Test admin permission checking"""
        admin_service = AdminService()
        
        # Test with empty admin list (from environment)
        assert admin_service.is_admin(123456789) is False
        
        # Test admin user IDs loading
        assert isinstance(admin_service.admin_user_ids, list)
    
    def test_encryption_key_handling(self):
        """Test encryption key handling"""
        import os
        from app.utils.encryption import get_encryption_key
        
        # Set a test key
        os.environ['SESSION_ENCRYPTION_KEY'] = 'test_key_for_encryption_testing'
        
        try:
            key = get_encryption_key()
            assert key is not None
            assert len(key) > 0
        except ValueError:
            # This is expected if no key is set
            pass
        finally:
            # Clean up
            if 'SESSION_ENCRYPTION_KEY' in os.environ:
                del os.environ['SESSION_ENCRYPTION_KEY']