from fastapi import APIRouter, Request, HTTPException
from app.services.PaymentService import PaymentService
from app.database.connection import DatabaseConnection
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/webhook/paytm")
async def paytm_callback(request: Request):
    """Handle Paytm payment callback"""
    try:
        db_connection = DatabaseConnection()
        await db_connection.connect()
        
        payment_service = PaymentService(db_connection)
        
        callback_data = await request.form()
        callback_dict = dict(callback_data)
        
        result = await payment_service.handle_paytm_callback(callback_dict)
        
        await db_connection.close()
        
        if result.get("error"):
            logger.error(f"Paytm callback error: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])
        
        return {"status": "success", "data": result}
        
    except ValueError as e:
        logger.error(f"Paytm callback validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Paytm callback error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Callback processing failed")
