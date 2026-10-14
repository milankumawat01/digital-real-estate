from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from datetime import datetime

from app.routes.auth import get_current_user
from app.routes.properties import property_serializer
from app.schemas.agent import LeadCreate, LeadUpdate
from app.database import (
    property_collection,
    lead_collection,
    commission_collection,
)
from app.utils.agent_helper import lead_serializer, commission_serializer

router = APIRouter()


def require_agent(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["agent", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only agents can access this resource"
        )
    return current_user


@router.get("/properties")
async def agent_properties(
    current_user: dict = Depends(require_agent)
):
    agent_id = str(current_user["_id"])

    results = []
    cursor = property_collection.find({
        "$or": [
            {"assigned_agent_id": agent_id},
            {"seller_id": agent_id}
        ]
    }).sort("created_at", -1)

    async for prop in cursor:
        results.append(property_serializer(prop))

    return {
        "count": len(results),
        "results": results
    }


@router.get("/leads")
async def list_leads(
    current_user: dict = Depends(require_agent)
):
    agent_id = str(current_user["_id"])
    role = current_user.get("role")

    query = {} if role == "admin" else {"agent_id": agent_id}

    results = []
    cursor = lead_collection.find(query).sort("created_at", -1)

    async for doc in cursor:
        results.append(lead_serializer(doc))

    return {
        "count": len(results),
        "results": results
    }


@router.post("/leads")
async def create_lead(
    payload: LeadCreate,
    current_user: dict = Depends(require_agent)
):
    if payload.property_id:
        try:
            ObjectId(payload.property_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid property ID format")

    now = datetime.utcnow()
    doc = {
        "agent_id": str(current_user["_id"]),
        "name": payload.name,
        "mobile": payload.mobile,
        "email": payload.email,
        "property_id": payload.property_id,
        "status": "new",
        "notes": payload.notes,
        "source": payload.source,
        "next_follow_up": None,
        "created_at": now,
        "updated_at": now,
    }

    result = await lead_collection.insert_one(doc)

    return {
        "id": str(result.inserted_id),
        "status": "new"
    }


@router.patch("/leads/{lead_id}")
async def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    current_user: dict = Depends(require_agent)
):
    try:
        obj_id = ObjectId(lead_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead ID format")

    lead = await lead_collection.find_one({"_id": obj_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    is_owner = lead.get("agent_id") == str(current_user["_id"])
    is_admin = current_user.get("role") == "admin"
    if not (is_owner or is_admin):
        raise HTTPException(status_code=403, detail="Not your lead")

    update_fields = {k: v for k, v in payload.dict().items() if v is not None}

    if not update_fields:
        return {"message": "No fields to update"}

    update_fields["updated_at"] = datetime.utcnow()

    await lead_collection.update_one(
        {"_id": obj_id},
        {"$set": update_fields}
    )

    updated = await lead_collection.find_one({"_id": obj_id})

    return {
        "id": lead_id,
        "status": updated.get("status")
    }


@router.get("/commissions")
async def list_commissions(
    current_user: dict = Depends(require_agent)
):
    agent_id = str(current_user["_id"])
    role = current_user.get("role")

    query = {} if role == "admin" else {"agent_id": agent_id}

    results = []
    total_pending = 0
    total_paid = 0
    total_earned = 0

    async for doc in commission_collection.find(query).sort("created_at", -1):
        results.append(commission_serializer(doc))

        amount = doc.get("commission_amount", 0)
        total_earned += amount

        if doc.get("status") == "paid":
            total_paid += amount
        else:
            total_pending += amount

    return {
        "count": len(results),
        "summary": {
            "total_earned": total_earned,
            "total_paid": total_paid,
            "total_pending": total_pending,
        },
        "results": results
    }