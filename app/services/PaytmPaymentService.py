import hashlib
import hmac
import logging
import requests
from typing import Dict, Any
from app.utils.datetime_utils import utc_now
import os

logger = logging.getLogger(__name__)

class PaytmPaymentService:
    """Paytm Payment Gateway Integration"""
    
    def __init__(self):
        self.merchant_key = os.getenv('PAYTM_MERCHANT_KEY')
        self.merchant_id = os.getenv('PAYTM_MERCHANT_ID')
        self.website = os.getenv('PAYTM_WEBSITE', 'WEBSTAGING')
        self.callback_url = os.getenv('PAYTM_CALLBACK_URL')
        
        if not self.merchant_key or not self.merchant_id:
            logger.warning("Paytm credentials not configured - set PAYTM_MERCHANT_KEY and PAYTM_MERCHANT_ID environment variables")
        
        # Use staging by default, switch to production only when explicitly configured
        self.base_url = "https://securegw-stage.paytm.in" if self.website != "WEBPROD" else "https://securegw.paytm.in"
    
    def generate_checksum(self, data: Dict[str, Any], for_url: bool = False) -> str:
        """Generate Paytm checksum"""
        try:
            if for_url:
                checksum_str = self._prepare_checksum_string(data)
            else:
                checksum_str = self._prepare_checksum_string(data)
            
            checksum = hmac.new(
                self.merchant_key.encode(),
                checksum_str.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return checksum
        except Exception as e:
            logger.error(f"Checksum generation error: {e}")
            raise ValueError("Failed to generate checksum")
    
    def _prepare_checksum_string(self, data: Dict[str, Any]) -> str:
        """Prepare string for checksum calculation"""
        sorted_keys = sorted(data.keys())
        checksum_str = ""
        
        for key in sorted_keys:
            value = data[key]
            if value is not None:
                checksum_str += str(value) + "|"
        
        return checksum_str
    
    async def create_payment_request(self, order_id: str, amount: float, user_id: int, user_email: str, user_phone: str) -> Dict[str, Any]:
        """Create Paytm payment request"""
        try:
            if not self.merchant_key or not self.merchant_id:
                return {"error": "Paytm not configured", "message": "Set PAYTM_MERCHANT_KEY and PAYTM_MERCHANT_ID environment variables"}
            
            data = {
                "MID": self.merchant_id,
                "ORDER_ID": order_id,
                "CUST_ID": str(user_id),
                "TXN_AMOUNT": str(amount),
                "EMAIL": user_email,
                "MOBILE_NO": user_phone,
                "WEBSITE": self.website,
                "CHANNEL_ID": "WEB",
                "INDUSTRY_TYPE_ID": "Retail",
                "CALLBACK_URL": self.callback_url
            }
            
            checksum = self.generate_checksum(data)
            data["CHECKSUMHASH"] = checksum
            
            return {
                "success": True,
                "data": data,
                "payment_url": f"{self.base_url}/order/initiate"
            }
        except ValueError as e:
            logger.error(f"Payment request validation error: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Payment request creation error: {e}", exc_info=True)
            return {"error": "Failed to create payment request"}
    
    def verify_checksum(self, response_data: Dict[str, Any]) -> bool:
        """Verify Paytm response checksum"""
        try:
            received_checksum = response_data.get("CHECKSUMHASH")
            if not received_checksum:
                return False
            
            data_copy = response_data.copy()
            del data_copy["CHECKSUMHASH"]
            
            checksum_str = self._prepare_checksum_string(data_copy)
            
            expected_checksum = hmac.new(
                self.merchant_key.encode(),
                checksum_str.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_checksum, received_checksum)
        except Exception as e:
            logger.error(f"Checksum verification error: {e}")
            return False
    
    async def verify_payment(self, order_id: str, transaction_id: str) -> Dict[str, Any]:
        """Verify payment status with Paytm"""
        try:
            if not self.merchant_key or not self.merchant_id:
                return {"error": "Paytm not configured", "message": "Set PAYTM_MERCHANT_KEY and PAYTM_MERCHANT_ID environment variables"}
            
            data = {
                "MID": self.merchant_id,
                "ORDERID": order_id,
                "CHECKSUMHASH": ""
            }
            
            checksum = self.generate_checksum(data)
            data["CHECKSUMHASH"] = checksum
            
            url = f"{self.base_url}/order/status"
            
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("STATUS") == "TXN_SUCCESS":
                return {
                    "success": True,
                    "transaction_id": result.get("TXNID"),
                    "order_id": result.get("ORDERID"),
                    "amount": float(result.get("TXNAMOUNT", 0)),
                    "status": "completed"
                }
            else:
                return {
                    "success": False,
                    "status": result.get("STATUS"),
                    "error": result.get("RESPMSG")
                }
        except ValueError as e:
            logger.error(f"Payment verification validation error: {e}")
            return {"error": str(e)}
        except requests.RequestException as e:
            logger.error(f"Payment verification request error: {e}")
            return {"error": "Failed to verify payment"}
        except Exception as e:
            logger.error(f"Payment verification error: {e}", exc_info=True)
            return {"error": "Verification failed"}
    
    def get_payment_form_html(self, payment_data: Dict[str, Any]) -> str:
        """Generate HTML form for Paytm payment"""
        try:
            form_html = f"""
            <html>
            <head>
                <title>Paytm Payment</title>
            </head>
            <body>
                <form method="post" action="{self.base_url}/order/initiate" name="paytm_form">
            """
            
            for key, value in payment_data.items():
                form_html += f'                    <input type="hidden" name="{key}" value="{value}">\n'
            
            form_html += """
                    <input type="submit" value="Pay with Paytm">
                </form>
                <script>
                    document.paytm_form.submit();
                </script>
            </body>
            </html>
            """
            
            return form_html
        except Exception as e:
            logger.error(f"Form generation error: {e}")
            raise ValueError("Failed to generate payment form")
