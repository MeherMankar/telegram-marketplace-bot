from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId
from enum import Enum

class AccountStatus(str, Enum):
    PENDING = "pending"
    CHECKING = "checking"
    APPROVED = "approved"
    REJECTED = "rejected"
    SOLD = "sold"
    BLOCKED = "blocked"

class Account(BaseModel):
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    seller_id: int
    telegram_account_id: Optional[int] = None
    phone_number: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    country: Optional[str] = None
    creation_year: Optional[int] = None
    session_file_path: Optional[str] = None
    session_string: Optional[str] = None
    status: AccountStatus = AccountStatus.PENDING
    price: Optional[float] = None
    
    # Verification results
    checks: Dict[str, Any] = Field(default_factory=dict)
    verification_logs: List[str] = Field(default_factory=list)
    
    # Flags
    otp_destroyer_enabled: bool = False
    blocked_from_payment: bool = False
    possibly_limited: bool = False
    
    # Admin review
    admin_reviewer_id: Optional[int] = None
    admin_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}