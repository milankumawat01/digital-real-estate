from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class UserStatusUpdate(BaseModel):
    status: Literal["active", "suspended", "banned"]
    reason: Optional[str] = None


class PropertyApprovalUpdate(BaseModel):
    status: Literal["approved", "rejected", "pending"]
    notes: Optional[str] = None


class ComplaintCreate(BaseModel):
    subject: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=10, max_length=2000)
    booking_id: Optional[str] = None
    property_id: Optional[str] = None
    against_user_id: Optional[str] = None


class ReviewModerationUpdate(BaseModel):
    status: Literal["published", "rejected", "hidden"]
    reason: Optional[str] = None


class AdminNotificationSend(BaseModel):
    recipient_ids: List[str] = Field(..., min_items=1)
    type: str = "announcement"
    title: str = Field(..., min_length=2, max_length=200)
    message: str = Field(..., min_length=2, max_length=1000)
    channels: List[str] = ["in_app"]