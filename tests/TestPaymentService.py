import pytest
from app.services.payment_service import PaymentService

class TestPaymentService:
    
    def setup_method(self):
        """Setup test method"""
        self.payment_service = PaymentService()
    
    @pytest.mark.asyncio
    async def test_create_upi_payment_simulation(self):
        """Test UPI payment creation in simulation mode"""
        result = await self.payment_service.create_upi_payment(100.0, 12345)
        
        assert result["success"] is True
        assert "payment_id" in result
        assert "payment_url" in result
        assert "qr_code" in result
        assert result["payment_url"].startswith("upi://pay")
    
    @pytest.mark.asyncio
    async def test_create_crypto_payment_simulation(self):
        """Test crypto payment creation in simulation mode"""
        result = await self.payment_service.create_crypto_payment(50.0, 12345, "USDT")
        
        assert result["success"] is True
        assert "payment_id" in result
        assert "wallet_address" in result
        assert result["currency"] == "USDT"
        assert result["network"] == "TRC20"
    
    @pytest.mark.asyncio
    async def test_verify_upi_payment_simulation(self):
        """Test UPI payment verification in simulation mode"""
        result = await self.payment_service.verify_upi_payment("test_payment_id", "test_ref")
        
        assert result["success"] is True
        assert result["verified"] is True
        assert "transaction_id" in result
    
    @pytest.mark.asyncio
    async def test_verify_crypto_payment_simulation(self):
        """Test crypto payment verification in simulation mode"""
        result = await self.payment_service.verify_crypto_payment("test_payment_id", "test_hash", "USDT")
        
        assert result["success"] is True
        assert result["verified"] is True
        assert result["tx_hash"] == "test_hash"
    
    @pytest.mark.asyncio
    async def test_process_upi_payout_simulation(self):
        """Test UPI payout processing in simulation mode"""
        result = await self.payment_service.process_payout(12345, 100.0, "upi", {"upi_id": "test@upi"})
        
        assert result["success"] is True
        assert result["method"] == "upi"
        assert result["amount"] == 100.0
    
    @pytest.mark.asyncio
    async def test_process_crypto_payout_simulation(self):
        """Test crypto payout processing in simulation mode"""
        result = await self.payment_service.process_payout(12345, 50.0, "crypto", {"address": "test_address"})
        
        assert result["success"] is True
        assert result["method"] == "crypto"
        assert result["amount"] == 50.0
    
    def test_generate_mock_wallet_address(self):
        """Test mock wallet address generation"""
        usdt_address = self.payment_service._generate_mock_wallet_address("USDT")
        btc_address = self.payment_service._generate_mock_wallet_address("BTC")
        
        assert usdt_address.startswith("TR")
        assert btc_address.startswith("1")
    
    @pytest.mark.asyncio
    async def test_unsupported_payout_method(self):
        """Test unsupported payout method"""
        result = await self.payment_service.process_payout(12345, 100.0, "unsupported", {})
        
        assert result["success"] is False
        assert "Unsupported payout method" in result["error"]