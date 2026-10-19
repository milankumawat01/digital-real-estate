from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from datetime import datetime

from app.routes.auth import get_current_user
from app.routes.properties import property_serializer
from app.utils.admin_helper import log_admin_action, get_platform_stats
from app.schemas.admin import (
    UserStatusUpdate,
    PropertyApprovalUpdate,
    ComplaintCreate,
    ReviewModerationUpdate,
    AdminNotificationSend,
)
from app.database import (
    user_collection,
    property_collection,
    document_collection,
    verification_collection,
    site_visit_collection,
    offer_collection,
    payment_collection,
    review_collection,
    complaint_collection,
    audit_log_collection,
    notification_collection,
)
from app.schemas.property_status import PropertyStatus

router = APIRouter()


def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admin can access this resource")
    return current_user


def user_public_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name"),
        "email": doc.get("email"),
        "mobile": doc.get("mobile"),
        "role": doc.get("role"),
        "status": doc.get("status", "active"),
        "is_verified": doc.get("is_verified", False),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
    }


@router.get("/users")
async def list_users(
    role: str = None,
    status: str = None,
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    query = {}
    if role:
        query["role"] = role
    if status:
        query["status"] = status

    results = []
    async for doc in user_collection.find(query).sort("created_at", -1).limit(limit):
        results.append(user_public_serializer(doc))

    return {"count": len(results), "results": results}


@router.patch("/users/{user_id}")
async def update_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    admin: dict = Depends(require_admin),
):
    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    user = await user_collection.find_one({"_id": obj_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await user_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": payload.status,
            "status_reason": payload.reason,
            "updated_at": datetime.utcnow(),
        }}
    )

    await log_admin_action(
        admin_id=str(admin["_id"]),
        action=f"user_{payload.status}",
        target=user_id,
        details={"reason": payload.reason},
    )

    return {"id": user_id, "status": payload.status}


@router.get("/properties")
async def list_all_properties(
    status: str = None,
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    query = {}
    if status:
        query["status"] = status

    results = []
    async for doc in property_collection.find(query).sort("created_at", -1).limit(limit):
        results.append(property_serializer(doc))

    return {"count": len(results), "results": results}


@router.patch("/properties/{property_id}")
async def approve_property(
    property_id: str,
    payload: PropertyApprovalUpdate,
    admin: dict = Depends(require_admin),
):
    try:
        obj_id = ObjectId(property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    prop = await property_collection.find_one({"_id": obj_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    status_map = {
        "approved": "available",
        "rejected": "rejected",
        "pending": "pending"
    }
    new_status = status_map.get(payload.status, "pending")

    await property_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": new_status,
            "admin_notes": payload.notes,
            "updated_at": datetime.utcnow(),
        }}
    )

    await log_admin_action(
        admin_id=str(admin["_id"]),
        action=f"property_{payload.status}",
        target=property_id,
        details={"notes": payload.notes},
    )

    return {"id": property_id, "status": new_status}


@router.get("/documents")
async def list_documents(
    status: str = None,
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    query = {}
    if status:
        query["status"] = status

    results = []
    async for doc in document_collection.find(query).sort("created_at", -1).limit(limit):
        results.append({
            "id": str(doc["_id"]),
            "property_id": doc.get("property_id"),
            "document_type": doc.get("document_type"),
            "file_url": doc.get("file_url"),
            "status": doc.get("status"),
            "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        })

    return {"count": len(results), "results": results}


@router.get("/verifications")
async def verification_queue(
    status: str = "under_review",
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    results = []
    async for doc in verification_collection.find({"status": status}).sort("created_at", -1).limit(limit):
        results.append({
            "id": str(doc["_id"]),
            "property_id": doc.get("property_id"),
            "submitted_by": doc.get("submitted_by"),
            "document_ids": doc.get("document_ids", []),
            "status": doc.get("status"),
            "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        })

    return {"count": len(results), "results": results}


@router.get("/site-visits")
async def monitor_site_visits(
    status: str = None,
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    query = {}
    if status:
        query["status"] = status

    results = []
    async for doc in site_visit_collection.find(query).sort("created_at", -1).limit(limit):
        results.append({
            "id": str(doc["_id"]),
            "property_id": doc.get("property_id"),
            "buyer_id": doc.get("buyer_id"),
            "seller_id": doc.get("seller_id"),
            "date": doc.get("date"),
            "time": doc.get("time"),
            "status": doc.get("status"),
        })

    return {"count": len(results), "results": results}


@router.get("/offers")
async def monitor_offers(
    status: str = None,
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    query = {}
    if status:
        query["status"] = status

    results = []
    async for doc in offer_collection.find(query).sort("created_at", -1).limit(limit):
        results.append({
            "id": str(doc["_id"]),
            "property_id": doc.get("property_id"),
            "buyer_id": doc.get("buyer_id"),
            "seller_id": doc.get("seller_id"),
            "amount": doc.get("amount"),
            "status": doc.get("status"),
            "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        })

    return {"count": len(results), "results": results}


@router.get("/payments")
async def monitor_payments(
    status: str = None,
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    query = {}
    if status:
        query["status"] = status

    results = []
    total = 0
    async for doc in payment_collection.find(query).sort("created_at", -1).limit(limit):
        results.append({
            "id": str(doc["_id"]),
            "booking_id": doc.get("booking_id"),
            "buyer_id": doc.get("buyer_id"),
            "amount": doc.get("amount"),
            "currency": doc.get("currency", "INR"),
            "status": doc.get("status"),
            "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        })
        if doc.get("status") == "paid":
            total += doc.get("amount", 0)

    return {"count": len(results), "total_paid": total, "results": results}


@router.get("/complaints")
async def list_complaints(
    status: str = None,
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    query = {}
    if status:
        query["status"] = status

    results = []
    async for doc in complaint_collection.find(query).sort("created_at", -1).limit(limit):
        results.append({
            "id": str(doc["_id"]),
            "subject": doc.get("subject"),
            "description": doc.get("description"),
            "raised_by": doc.get("raised_by"),
            "against_user_id": doc.get("against_user_id"),
            "booking_id": doc.get("booking_id"),
            "status": doc.get("status", "open"),
            "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        })

    return {"count": len(results), "results": results}


@router.post("/complaints")
async def create_complaint(
    payload: ComplaintCreate,
    current_user: dict = Depends(get_current_user),
):
    now = datetime.utcnow()
    doc = {
        "subject": payload.subject,
        "description": payload.description,
        "booking_id": payload.booking_id,
        "property_id": payload.property_id,
        "against_user_id": payload.against_user_id,
        "raised_by": str(current_user["_id"]),
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }

    result = await complaint_collection.insert_one(doc)

    return {"id": str(result.inserted_id), "status": "open"}


@router.get("/reviews")
async def moderate_reviews_list(
    status: str = None,
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    query = {}
    if status:
        query["status"] = status

    results = []
    async for doc in review_collection.find(query).sort("created_at", -1).limit(limit):
        results.append({
            "id": str(doc["_id"]),
            "property_id": doc.get("property_id"),
            "buyer_id": doc.get("buyer_id"),
            "buyer_name": doc.get("buyer_name"),
            "rating": doc.get("rating"),
            "comment": doc.get("comment"),
            "status": doc.get("status", "published"),
            "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        })

    return {"count": len(results), "results": results}


@router.patch("/reviews/{review_id}")
async def moderate_review(
    review_id: str,
    payload: ReviewModerationUpdate,
    admin: dict = Depends(require_admin),
):
    try:
        obj_id = ObjectId(review_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid review ID format")

    review = await review_collection.find_one({"_id": obj_id})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    await review_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": payload.status,
            "moderation_reason": payload.reason,
            "moderated_by": str(admin["_id"]),
            "moderated_at": datetime.utcnow(),
        }}
    )

    await log_admin_action(
        admin_id=str(admin["_id"]),
        action=f"review_{payload.status}",
        target=review_id,
        details={"reason": payload.reason},
    )

    return {"id": review_id, "status": payload.status}


@router.post("/notifications")
async def send_admin_notification(
    payload: AdminNotificationSend,
    admin: dict = Depends(require_admin),
):
    now = datetime.utcnow()
    count = 0

    for recipient_id in payload.recipient_ids:
        doc = {
            "user_id": recipient_id,
            "title": payload.title,
            "body": payload.message,
            "type": payload.type,
            "channels": payload.channels,
            "read": False,
            "sent_by": str(admin["_id"]),
            "created_at": now,
        }
        await notification_collection.insert_one(doc)
        count += 1

    await log_admin_action(
        admin_id=str(admin["_id"]),
        action="send_notification",
        target=f"{count}_recipients",
        details={"title": payload.title, "type": payload.type},
    )

    return {"message": "Notification queued", "count": count}


@router.get("/reports")
async def platform_reports(
    admin: dict = Depends(require_admin),
):
    stats = await get_platform_stats()
    return stats


@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = 100,
    admin: dict = Depends(require_admin),
):
    results = []
    async for doc in audit_log_collection.find({}).sort("created_at", -1).limit(limit):
        results.append({
            "id": str(doc["_id"]),
            "admin_id": doc.get("admin_id"),
            "action": doc.get("action"),
            "target": doc.get("target"),
            "details": doc.get("details", {}),
            "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        })

    return {"count": len(results), "results": results}