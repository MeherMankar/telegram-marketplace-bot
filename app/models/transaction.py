from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from enum import Enum

class TransactionType(str, Enum):
    ACCOUNT_SALE = "account_sale"
    PAYOUT = "payout"
    REFUND = "refund"

class PaymentMethod(str, Enum):
    UPI = "upi"
    CRYPTO = "crypto"

class TransactionStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Transaction(BaseModel):
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    user_id: int
    type: TransactionType
    amount: float
    payment_method: PaymentMethod
    status: TransactionStatus = TransactionStatus.PENDING
    
    # Payment details
    payment_reference: Optional[str] = None
    payment_address: Optional[str] = None
    txn_hash: Optional[str] = None
    
    # Related objects
    account_id: Optional[ObjectId] = None
    listing_id: Optional[ObjectId] = None
    
    # Admin approval
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}