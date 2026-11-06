from pydantic import BaseModel, Field
from typing import List, Optional


class LocationModel(BaseModel):
    type: str = "Point"
    coordinates: List[float]


class MediaResponse(BaseModel):
    media_id: str
    url: str
    media_type: str
    filename: Optional[str] = None
    detected_mime: Optional[str] = None


class ComparePropertiesRequest(BaseModel):
    property_ids: List[str] = Field(..., min_items=2, max_items=3)