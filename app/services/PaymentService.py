from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
from app.utils.datetime_utils import utc_now
from app.utils.security_utils import sanitize_message
from app.services.PaytmPaymentService import PaytmPaymentService

logger = logging.getLogger(__name__)

class PaymentService:
    """Unified Payment Service with Paytm and UPI"""
    
    def __init__(self, db_connection):
        self.db_connection = db_connection
        self.paytm_service = PaytmPaymentService()
        
        self.payment_methods = {
            "upi_direct": {
                "name": "Direct UPI",
                "fee_percentage": 0.0,
                "fee_fixed": 0.0,
                "requires_manual_verification": True,
                "auto_verification": False
            },
            "paytm": {
                "name": "Paytm Wallet",
                "fee_percentage": 1.0,
                "fee_fixed": 0.0,
                "requires_manual_verification": False,
                "auto_verification": True
            },
            "crypto": {
                "name": "Cryptocurrency",
                "fee_percentage": 1.5,
                "fee_fixed": 0.0,
                "requires_manual_verification": True,
                "auto_verification": False
            }
        }
    
    async def calculate_payment_amount(self, base_amount: float, payment_method: str) -> Dict[str, Any]:
        """Calculate total amount including fees"""
        try:
            if payment_method not in self.payment_methods:
                return {"error": "Invalid payment method"}
            
            method_config = self.payment_methods[payment_method]
            
            fee_percentage = method_config["fee_percentage"]
            fee_fixed = method_config["fee_fixed"]
            
            fee_amount = (base_amount * fee_percentage / 100) + fee_fixed
            total_amount = base_amount + fee_amount
            
            return {
                "base_amount": base_amount,
                "fee_amount": round(fee_amount, 2),
                "total_amount": round(total_amount, 2),
                "fee_percentage": fee_percentage,
                "fee_fixed": fee_fixed,
                "payment_method": payment_method,
                "method_name": method_config["name"],
                "requires_manual_verification": method_config["requires_manual_verification"],
                "auto_verification": method_config["auto_verification"]
            }
        except (ValueError, TypeError) as e:
            logger.error(f"Payment calculation validation error: {str(e)}")
            return {"error": "Calculation failed"}
        except Exception as e:
            logger.error(f"Failed to calculate payment amount: {str(e)}", exc_info=True)
            return {"error": "Calculation failed"}
    
    async def create_payment_order(self, user_id: int, base_amount: float, payment_method: str, purpose: str = "account_purchase", user_email: str = "", user_phone: str = "") -> Dict[str, Any]:
        """Create payment order with fees"""
        try:
            calculation = await self.calculate_payment_amount(base_amount, payment_method)
            if "error" in calculation:
                return calculation
            
            order_id = self._generate_order_id()
            
            order_doc = {
                "order_id": order_id,
                "user_id": user_id,
                "base_amount": calculation["base_amount"],
                "fee_amount": calculation["fee_amount"],
                "total_amount": calculation["total_amount"],
                "payment_method": payment_method,
                "purpose": purpose,
                "status": "pending",
                "requires_manual_verification": calculation["requires_manual_verification"],
                "auto_verification": calculation["auto_verification"],
                "requires_screenshot": payment_method == "upi_direct",
                "screenshot_uploaded": False,
                "created_at": utc_now(),
                "expires_at": utc_now() + timedelta(minutes=30)
            }
            
            await self.db_connection.payment_orders.insert_one(order_doc)
            
            result = {
                "order_id": order_id,
                "calculation": calculation,
                "order_doc": order_doc
            }
            
            if payment_method == "paytm":
                paytm_request = await self.paytm_service.create_payment_request(
                    order_id, 
                    calculation["total_amount"],
                    user_id,
                    user_email,
                    user_phone
                )
                if paytm_request.get("success"):
                    result["paytm_data"] = paytm_request["data"]
                    result["payment_url"] = paytm_request["payment_url"]
            
            return result
            
        except (ValueError, OSError) as e:
            logger.error(f"Payment order creation error: {str(e)}")
            return {"error": "Order creation failed"}
        except Exception as e:
            logger.error(f"Failed to create payment order: {str(e)}", exc_info=True)
            return {"error": "Order creation failed"}
    
    async def handle_paytm_callback(self, callback_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Paytm payment callback"""
        try:
            if not self.paytm_service.verify_checksum(callback_data):
                return {"error": "Invalid checksum"}
            
            order_id = callback_data.get("ORDERID")
            transaction_id = callback_data.get("TXNID")
            status = callback_data.get("STATUS")
            
            order = await self.db_connection.payment_orders.find_one({"order_id": order_id})
            if not order:
                return {"error": "Order not found"}
            
            if status == "TXN_SUCCESS":
                await self.db_connection.payment_orders.update_one(
                    {"order_id": order_id},
                    {
                        "$set": {
                            "status": "verified",
                            "transaction_id": transaction_id,
                            "verified_at": utc_now(),
                            "payment_response": callback_data
                        }
                    }
                )
                
                await self._notify_user_verification_result(order["user_id"], order_id, True, "Payment successful")
                
                return {"success": True, "status": "verified"}
            else:
                await self.db_connection.payment_orders.update_one(
                    {"order_id": order_id},
                    {
                        "$set": {
                            "status": "failed",
                            "failure_reason": callback_data.get("RESPMSG"),
                            "payment_response": callback_data
                        }
                    }
                )
                
                return {"success": False, "status": "failed", "reason": callback_data.get("RESPMSG")}
        except ValueError as e:
            logger.error(f"Paytm callback validation error: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Paytm callback handling error: {e}", exc_info=True)
            return {"error": "Callback processing failed"}
    
    async def submit_payment_proof(self, order_id: str, proof_data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit payment proof for manual verification (UPI only)"""
        try:
            order = await self.db_connection.payment_orders.find_one({"order_id": order_id})
            if not order:
                return {"error": "Order not found"}
            
            if order["status"] != "pending":
                return {"error": "Order is not pending"}
            
            if order.get("requires_screenshot", False) and not proof_data.get("screenshot_file_id"):
                return {"error": "Screenshot is required for this payment method"}
            
            update_data = {
                "status": "proof_submitted",
                "proof_data": proof_data,
                "proof_submitted_at": utc_now()
            }
            
            if proof_data.get("screenshot_file_id"):
                update_data["screenshot_uploaded"] = True
                update_data["screenshot_file_id"] = proof_data["screenshot_file_id"]
            
            await self.db_connection.payment_orders.update_one(
                {"order_id": order_id},
                {"$set": update_data}
            )
            
            await self._create_admin_verification_task(order_id, order, proof_data)
            
            return {
                "success": True,
                "message": "Payment proof submitted. Admin will verify within 24 hours.",
                "order_id": order_id
            }
            
        except (ValueError, OSError) as e:
            logger.error(f"Payment proof submission error: {str(e)}")
            return {"error": "Proof submission failed"}
        except Exception as e:
            logger.error(f"Failed to submit payment proof: {str(e)}", exc_info=True)
            return {"error": "Proof submission failed"}
    
    async def verify_payment(self, order_id: str, admin_id: int, verified: bool, notes: str = "") -> Dict[str, Any]:
        """Admin verification of payment"""
        try:
            order = await self.db_connection.payment_orders.find_one({"order_id": order_id})
            if not order:
                return {"error": "Order not found"}
            
            if order["status"] != "proof_submitted":
                return {"error": "Order is not awaiting verification"}
            
            new_status = "verified" if verified else "rejected"
            
            await self.db_connection.payment_orders.update_one(
                {"order_id": order_id},
                {
                    "$set": {
                        "status": new_status,
                        "verified_by": admin_id,
                        "verified_at": utc_now(),
                        "verification_notes": sanitize_message(notes)
                    }
                }
            )
            
            await self._notify_user_verification_result(order["user_id"], order_id, verified, notes)
            
            return {
                "success": True,
                "order_id": order_id,
                "verified": verified,
                "status": new_status
            }
            
        except (ValueError, OSError) as e:
            logger.error(f"Payment verification error: {str(e)}")
            return {"error": "Verification failed"}
        except Exception as e:
            logger.error(f"Failed to verify payment: {str(e)}", exc_info=True)
            return {"error": "Verification failed"}
    
    async def get_pending_verifications(self) -> list:
        """Get payments pending admin verification"""
        try:
            orders = await self.db_connection.payment_orders.find({
                "status": "proof_submitted"
            }).sort("proof_submitted_at", 1).to_list(length=50)
            
            return orders
        except (ValueError, OSError) as e:
            logger.error(f"Pending verifications retrieval error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Failed to get pending verifications: {str(e)}", exc_info=True)
            return []
    
    async def get_payment_methods_with_fees(self, base_amount: float) -> list:
        """Get available payment methods with calculated fees"""
        try:
            methods = []
            
            for method_id, config in self.payment_methods.items():
                calculation = await self.calculate_payment_amount(base_amount, method_id)
                if "error" not in calculation:
                    methods.append({
                        "id": method_id,
                        "name": config["name"],
                        "base_amount": calculation["base_amount"],
                        "fee_amount": calculation["fee_amount"],
                        "total_amount": calculation["total_amount"],
                        "requires_manual_verification": config["requires_manual_verification"],
                        "auto_verification": config["auto_verification"]
                    })
            
            return methods
        except (ValueError, OSError) as e:
            logger.error(f"Payment methods retrieval error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Failed to get payment methods: {str(e)}", exc_info=True)
            return []
    
    def create_payment_summary_message(self, calculation: Dict[str, Any]) -> str:
        """Create payment summary message with fees"""
        method_name = sanitize_message(calculation.get('method_name', 'Unknown'))
        screenshot_note = "\n📸 **Screenshot Required:** You must upload payment screenshot for verification." if calculation['payment_method'] == 'upi_direct' else ""
        
        return f"""💰 **Payment Summary**

**Item Amount:** ₹{calculation['base_amount']:.2f}
**Payment Method:** {method_name}
**Processing Fee:** ₹{calculation['fee_amount']:.2f}
**Total Amount:** ₹{calculation['total_amount']:.2f}

{'🔍 **Manual Verification Required**' if calculation['requires_manual_verification'] else '⚡ **Auto Verification**'}
{'Admin will verify your payment within 24 hours.' if calculation['requires_manual_verification'] else 'Payment verified automatically.'}{screenshot_note}"""
    
    def create_fee_breakdown_message(self, base_amount: float) -> str:
        """Create fee breakdown for all payment methods"""
        message = f"💳 **Payment Methods & Fees**\n\n**Item Price:** ₹{base_amount:.2f}\n\n"
        
        for method_id, config in self.payment_methods.items():
            fee_amount = (base_amount * config["fee_percentage"] / 100) + config["fee_fixed"]
            total_amount = base_amount + fee_amount
            
            verification_type = "Manual" if config["requires_manual_verification"] else "Auto"
            screenshot_req = "📸 Screenshot Required" if method_id == "upi_direct" else "No Screenshot"
            
            method_name = sanitize_message(config['name'])
            message += f"**{method_name}**\n"
            message += f"Fee: ₹{fee_amount:.2f} | Total: ₹{total_amount:.2f}\n"
            message += f"Verification: {verification_type} | {screenshot_req}\n\n"
        
        return message
    
    async def _create_admin_verification_task(self, order_id: str, order: Dict, proof_data: Dict):
        """Create admin verification task"""
        try:
            task_doc = {
                "type": "payment_verification",
                "order_id": order_id,
                "user_id": order["user_id"],
                "amount": order["total_amount"],
                "payment_method": order["payment_method"],
                "proof_data": proof_data,
                "created_at": utc_now(),
                "status": "pending"
            }
            
            await self.db_connection.admin_tasks.insert_one(task_doc)
        except (ValueError, OSError) as e:
            logger.error(f"Admin task creation error: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to create admin task: {str(e)}", exc_info=True)
    
    async def _notify_user_verification_result(self, user_id: int, order_id: str, verified: bool, notes: str):
        """Notify user of verification result"""
        try:
            notification_doc = {
                "user_id": user_id,
                "type": "payment_verification_result",
                "order_id": order_id,
                "verified": verified,
                "notes": sanitize_message(notes),
                "created_at": utc_now(),
                "read": False
            }
            
            await self.db_connection.user_notifications.insert_one(notification_doc)
        except (ValueError, OSError) as e:
            logger.error(f"User notification creation error: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to create user notification: {str(e)}", exc_info=True)
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID"""
        import random
        timestamp = utc_now().strftime("%Y%m%d%H%M%S")
        random_digits = f"{random.randint(1000, 9999)}"
        return f"PAY{timestamp}{random_digits}"
