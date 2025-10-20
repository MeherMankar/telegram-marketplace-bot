from fastapi import APIRouter, Request, HTTPException
from app.services.UpiPaymentService import UpiPaymentService
from app.database.connection import DatabaseConnection
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request):
    """Handle Razorpay webhook events"""
    try:
        # Get raw body and signature
        body = await request.body()
        signature = request.headers.get('X-Razorpay-Signature')
        
        if not signature:
            raise HTTPException(status_code=400, detail="Missing signature")
        
        # Initialize UPI service
        db_connection = DatabaseConnection()
        await db_connection.connect()
        upi_service = UpiPaymentService(db_connection)
        
        # Verify signature
        if not await upi_service.verify_webhook_signature(body.decode(), signature):
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Parse payload
        payload = json.loads(body.decode())
        
        # Handle webhook
        result = await upi_service.handle_webhook(payload)
        
        await db_connection.close()
        return {"status": "success", "result": result}
        
    except Exception as e:
        logger.error(f"Razorpay webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")