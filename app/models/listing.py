from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from enum import Enum

class ListingStatus(str, Enum):
    ACTIVE = "active"
    SOLD = "sold"
    EXPIRED = "expired"
    REMOVED = "removed"

class Listing(BaseModel):
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    account_id: ObjectId
    seller_id: int
    country: str
    creation_year: int
    price: float
    status: ListingStatus = ListingStatus.ACTIVE
    buyer_id: Optional[int] = None
    sold_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}