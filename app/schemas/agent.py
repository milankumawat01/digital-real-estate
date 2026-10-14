from pydantic import BaseModel, Field
from typing import Optional, Literal


class LeadCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    mobile: str = Field(..., min_length=10, max_length=15)
    email: Optional[str] = None
    property_id: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=1000)
    source: Optional[str] = None


class LeadUpdate(BaseModel):
    status: Optional[Literal["new", "contacted", "qualified", "site_visit", "negotiation", "closed_won", "closed_lost"]] = None
    notes: Optional[str] = None
    next_follow_up: Optional[str] = None
    assigned_property_id: Optional[str] = None