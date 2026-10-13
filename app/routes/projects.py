from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from datetime import datetime

from app.routes.auth import get_current_user
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    TowerCreate,
    FloorCreate,
    UnitCreate,
    UnitUpdate,
)
from app.database import (
    project_collection,
    tower_collection,
    floor_collection,
    unit_collection,
)
from app.utils.builder_helper import (
    project_serializer,
    tower_serializer,
    floor_serializer,
    unit_serializer,
    get_project_analytics,
)

router = APIRouter()


def require_builder(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["builder", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only builders can perform this action"
        )
    return current_user


@router.post("/")
async def create_project(
    payload: ProjectCreate,
    current_user: dict = Depends(require_builder)
):
    now = datetime.utcnow()
    doc = payload.dict()
    doc["builder_id"] = str(current_user["_id"])
    doc["construction_progress"] = 0
    doc["created_at"] = now
    doc["updated_at"] = now

    result = await project_collection.insert_one(doc)

    return {"id": str(result.inserted_id)}


@router.get("/")
async def list_projects(
    current_user: dict = Depends(require_builder)
):
    builder_id = str(current_user["_id"])
    role = current_user.get("role")

    query = {} if role == "admin" else {"builder_id": builder_id}

    results = []
    async for doc in project_collection.find(query).sort("created_at", -1):
        results.append(project_serializer(doc))

    return {
        "count": len(results),
        "results": results
    }


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    current_user: dict = Depends(require_builder)
):
    try:
        obj_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project ID format")

    project = await project_collection.find_one({"_id": obj_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return project_serializer(project)


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    current_user: dict = Depends(require_builder)
):
    try:
        obj_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project ID format")

    project = await project_collection.find_one({"_id": obj_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    is_owner = project.get("builder_id") == str(current_user["_id"])
    is_admin = current_user.get("role") == "admin"
    if not (is_owner or is_admin):
        raise HTTPException(status_code=403, detail="Not authorized")

    update_fields = {k: v for k, v in payload.dict().items() if v is not None}

    if not update_fields:
        return {"message": "No fields to update", "updated_fields": []}

    update_fields["updated_at"] = datetime.utcnow()

    await project_collection.update_one(
        {"_id": obj_id},
        {"$set": update_fields}
    )

    return {
        "id": project_id,
        "construction_progress": update_fields.get(
            "construction_progress",
            project.get("construction_progress", 0)
        )
    }


@router.post("/{project_id}/towers")
async def create_tower(
    project_id: str,
    payload: TowerCreate,
    current_user: dict = Depends(require_builder)
):
    try:
        obj_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project ID format")

    project = await project_collection.find_one({"_id": obj_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.get("builder_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not your project")

    now = datetime.utcnow()
    doc = {
        "project_id": project_id,
        "name": payload.name,
        "total_floors": payload.total_floors,
        "builder_id": str(current_user["_id"]),
        "created_at": now,
    }

    result = await tower_collection.insert_one(doc)

    return {"id": str(result.inserted_id)}


@router.post("/towers/{tower_id}/floors")
async def create_floor(
    tower_id: str,
    payload: FloorCreate,
    current_user: dict = Depends(require_builder)
):
    try:
        tower_obj_id = ObjectId(tower_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid tower ID format")

    tower = await tower_collection.find_one({"_id": tower_obj_id})
    if not tower:
        raise HTTPException(status_code=404, detail="Tower not found")

    if tower.get("builder_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not your tower")

    now = datetime.utcnow()
    doc = {
        "tower_id": tower_id,
        "project_id": tower.get("project_id"),
        "floor_number": payload.floor_number,
        "builder_id": str(current_user["_id"]),
        "created_at": now,
    }

    result = await floor_collection.insert_one(doc)

    return {"id": str(result.inserted_id)}


@router.post("/floors/{floor_id}/units")
async def create_unit(
    floor_id: str,
    payload: UnitCreate,
    current_user: dict = Depends(require_builder)
):
    try:
        floor_obj_id = ObjectId(floor_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid floor ID format")

    floor = await floor_collection.find_one({"_id": floor_obj_id})
    if not floor:
        raise HTTPException(status_code=404, detail="Floor not found")

    if floor.get("builder_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not your floor")

    now = datetime.utcnow()
    doc = {
        "floor_id": floor_id,
        "tower_id": floor.get("tower_id"),
        "project_id": floor.get("project_id"),
        "unit_number": payload.unit_number,
        "bhk": payload.bhk,
        "area_sqft": payload.area_sqft,
        "price": payload.price,
        "status": payload.status,
        "facing": payload.facing,
        "parking": payload.parking,
        "builder_id": str(current_user["_id"]),
        "created_at": now,
    }

    result = await unit_collection.insert_one(doc)

    return {
        "id": str(result.inserted_id),
        "status": payload.status
    }


@router.patch("/units/{unit_id}")
async def update_unit(
    unit_id: str,
    payload: UnitUpdate,
    current_user: dict = Depends(require_builder)
):
    try:
        obj_id = ObjectId(unit_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid unit ID format")

    unit = await unit_collection.find_one({"_id": obj_id})
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    if unit.get("builder_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not your unit")

    update_fields = {k: v for k, v in payload.dict().items() if v is not None}

    if not update_fields:
        return {"message": "No fields to update"}

    update_fields["updated_at"] = datetime.utcnow()

    await unit_collection.update_one(
        {"_id": obj_id},
        {"$set": update_fields}
    )

    updated = await unit_collection.find_one({"_id": obj_id})

    return {
        "id": unit_id,
        "status": updated.get("status")
    }


@router.get("/{project_id}/analytics")
async def project_analytics(
    project_id: str,
    current_user: dict = Depends(require_builder)
):
    try:
        ObjectId(project_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project ID format")

    analytics = await get_project_analytics(project_id)

    return {
        "sales": analytics["sales"],
        "bookings": analytics["bookings"],
        "revenue": analytics["revenue"],
        "available_units": analytics["available_units"],
        "detailed": analytics
    }