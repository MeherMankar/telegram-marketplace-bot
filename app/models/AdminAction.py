from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId
from enum import Enum

class ActionType(str, Enum):
    ACCOUNT_REVIEW = "account_review"
    PAYMENT_APPROVAL = "payment_approval"
    PAYOUT_APPROVAL = "payout_approval"
    PRICE_UPDATE = "price_update"
    USER_ACTION = "user_action"

class AdminAction(BaseModel):
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    admin_id: int
    action_type: ActionType
    target_id: Optional[str] = None  # user_id, account_id, etc.
    details: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}