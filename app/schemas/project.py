from pydantic import BaseModel, Field
from typing import Optional, Literal


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    city: str = Field(..., min_length=2)
    locality: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    status: Literal["planning", "under_construction", "completed", "launched"] = "planning"
    rera_number: Optional[str] = None
    possession_date: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Literal["planning", "under_construction", "completed", "launched"]] = None
    construction_progress: Optional[int] = Field(None, ge=0, le=100)
    possession_date: Optional[str] = None


class TowerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    total_floors: int = Field(..., ge=1, le=100)


class FloorCreate(BaseModel):
    floor_number: int = Field(..., ge=-5, le=200)


class UnitCreate(BaseModel):
    unit_number: str = Field(..., min_length=1, max_length=50)
    bhk: int = Field(..., ge=1, le=10)
    area_sqft: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    status: Literal["available", "reserved", "sold", "blocked"] = "available"
    facing: Optional[str] = None
    parking: Optional[int] = 0


class UnitUpdate(BaseModel):
    price: Optional[float] = Field(None, gt=0)
    status: Optional[Literal["available", "reserved", "sold", "blocked"]] = None
    parking: Optional[int] = None