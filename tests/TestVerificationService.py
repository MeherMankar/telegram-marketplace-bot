import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.verification_service import VerificationService

class TestVerificationService:
    
    def setup_method(self):
        """Setup test method"""
        self.verification_service = VerificationService()
    
    @pytest.mark.asyncio
    async def test_verify_account_unauthorized_session(self):
        """Test verification with unauthorized session"""
        with patch('app.services.verification_service.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.connect = AsyncMock()
            mock_client.is_user_authorized = AsyncMock(return_value=False)
            mock_client.disconnect = AsyncMock()
            
            result = await self.verification_service.verify_account("invalid_session", "test_account_id")
            
            assert result["overall_status"] == "failed"
            assert "Session not authorized" in result["logs"]
    
    @pytest.mark.asyncio
    async def test_verify_account_exception_handling(self):
        """Test verification with exception"""
        with patch('app.services.verification_service.TelegramClient') as mock_client_class:
            mock_client_class.side_effect = Exception("Connection failed")
            
            result = await self.verification_service.verify_account("test_session", "test_account_id")
            
            assert result["overall_status"] == "error"
            assert any("Verification error" in log for log in result["logs"])
    
    @pytest.mark.asyncio
    async def test_enable_otp_destroyer_success(self):
        """Test OTP destroyer enable success"""
        with patch('app.services.verification_service.TelegramClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.connect = AsyncMock()
            mock_client.disconnect = AsyncMock()
            
            result = await self.verification_service.enable_otp_destroyer("test_session")
            
            # Since we're mocking, this should succeed
            assert result is True
    
    @pytest.mark.asyncio
    async def test_disable_otp_destroyer(self):
        """Test OTP destroyer disable"""
        result = await self.verification_service.disable_otp_destroyer("test_session")
        
        # This is a placeholder implementation, should return True
        assert result is True
    
    def test_verification_service_initialization(self):
        """Test VerificationService initialization"""
        service = VerificationService()
        assert service.spam_bot_username == "spambot"
        assert len(service.test_targets) == 3