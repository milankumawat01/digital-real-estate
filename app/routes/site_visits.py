from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from datetime import datetime, date

from app.routes.auth import get_current_user, require_buyer
from app.schemas.site_visit import SiteVisitCreate, SiteVisitUpdate
from app.database import site_visit_collection, property_collection
from app.utils.notification_helper import create_notification

router = APIRouter()


def site_visit_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "property_id": doc.get("property_id"),
        "buyer_id": doc.get("buyer_id"),
        "seller_id": doc.get("seller_id"),
        "date": doc.get("date"),
        "time": doc.get("time"),
        "notes": doc.get("notes"),
        "status": doc.get("status", "pending"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


def validate_visit_date_time(date_str: str, time_str: str):
    try:
        visit_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD"
        )

    if visit_date < date.today():
        raise HTTPException(
            status_code=400,
            detail="Visit date cannot be in the past"
        )

    try:
        datetime.strptime(time_str, "%H:%M")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid time format. Use HH:MM (24-hour)"
        )


@router.post("/")
async def request_site_visit(
    visit_data: SiteVisitCreate,
    current_user: dict = Depends(require_buyer)
):
    try:
        obj_id = ObjectId(visit_data.property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    prop = await property_collection.find_one({"_id": obj_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    if prop.get("seller_id") == str(current_user["_id"]):
        raise HTTPException(
            status_code=400,
            detail="You cannot request a visit for your own property"
        )

    validate_visit_date_time(visit_data.date, visit_data.time)

    existing = await site_visit_collection.find_one({
        "property_id": visit_data.property_id,
        "buyer_id": str(current_user["_id"]),
        "status": {"$in": ["pending", "approved", "rescheduled"]}
    })
    if existing:
        raise HTTPException(
            status_code=400,
            detail="You already have an active visit request for this property"
        )

    doc = {
        "property_id": visit_data.property_id,
        "buyer_id": str(current_user["_id"]),
        "seller_id": prop.get("seller_id"),
        "date": visit_data.date,
        "time": visit_data.time,
        "notes": visit_data.notes,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await site_visit_collection.insert_one(doc)

    await create_notification(
        user_id=prop.get("seller_id"),
        title="New site visit request",
        body=f"{current_user.get('name', 'Buyer')} wants to visit on {visit_data.date} at {visit_data.time}",
        notif_type="site_visit_requested",
        reference_id=str(result.inserted_id),
        reference_type="site_visit",
    )

    return {
        "id": str(result.inserted_id),
        "status": "pending"
    }


@router.get("/")
async def list_site_visits(
    current_user: dict = Depends(get_current_user)
):
    user_id = str(current_user["_id"])
    role = current_user.get("role", "buyer")

    if role == "admin":
        query = {}
    elif role in ["seller", "builder", "agent"]:
        query = {"seller_id": user_id}
    else:
        query = {"buyer_id": user_id}

    results = []
    cursor = site_visit_collection.find(query).sort("created_at", -1)

    async for doc in cursor:
        results.append(site_visit_serializer(doc))

    return {
        "count": len(results),
        "results": results
    }


@router.get("/{visit_id}")
async def get_site_visit(
    visit_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(visit_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid visit ID format")

    visit = await site_visit_collection.find_one({"_id": obj_id})
    if not visit:
        raise HTTPException(status_code=404, detail="Site visit not found")

    user_id = str(current_user["_id"])
    role = current_user.get("role")
    is_participant = (
        visit.get("buyer_id") == user_id or
        visit.get("seller_id") == user_id or
        role == "admin"
    )
    if not is_participant:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to view this site visit"
        )

    return site_visit_serializer(visit)


@router.patch("/{visit_id}")
async def update_site_visit(
    visit_id: str,
    update_data: SiteVisitUpdate,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(visit_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid visit ID format")

    visit = await site_visit_collection.find_one({"_id": obj_id})
    if not visit:
        raise HTTPException(status_code=404, detail="Site visit not found")

    user_id = str(current_user["_id"])
    role = current_user.get("role")
    is_seller = visit.get("seller_id") == user_id
    is_admin = role == "admin"
    if not (is_seller or is_admin):
        raise HTTPException(
            status_code=403,
            detail="Only the property seller or admin can update this site visit"
        )

    update_fields = {k: v for k, v in update_data.dict().items() if v is not None}

    if not update_fields:
        return {
            "message": "No fields to update",
            "updated_fields": []
        }

    if "status" in update_fields:
        valid_statuses = ["approved", "rescheduled", "cancelled", "completed"]
        if update_fields["status"] not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Status must be one of: {valid_statuses}"
            )

    if update_fields.get("status") == "rescheduled":
        if "date" not in update_fields or "time" not in update_fields:
            raise HTTPException(
                status_code=400,
                detail="New date and time are required when rescheduling"
            )
        validate_visit_date_time(update_fields["date"], update_fields["time"])

    update_fields["updated_at"] = datetime.utcnow()

    await site_visit_collection.update_one(
        {"_id": obj_id},
        {"$set": update_fields}
    )

    updated = await site_visit_collection.find_one({"_id": obj_id})

    notif_map = {
        "approved": ("Site visit approved ", "site_visit_approved"),
        "rescheduled": ("Site visit rescheduled ", "site_visit_requested"),
        "cancelled": ("Site visit cancelled ", "site_visit_cancelled"),
    }

    if update_fields.get("status") in notif_map:
        title, ntype = notif_map[update_fields["status"]]
        await create_notification(
            user_id=visit.get("buyer_id"),
            title=title,
            body="Updated by seller.",
            notif_type=ntype,
            reference_id=visit_id,
            reference_type="site_visit",
        )

    return {
        "id": str(updated["_id"]),
        "status": updated.get("status")
    }
