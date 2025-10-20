from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from bson import ObjectId

class User(BaseModel):
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    telegram_user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = None
    is_admin: bool = False
    balance: float = 0.0
    tos_accepted: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    upload_count_today: int = 0
    last_upload_date: Optional[datetime] = None
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}