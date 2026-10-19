from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from datetime import datetime

from app.routes.auth import get_current_user, require_seller
from app.schemas.verification import VerificationSubmit, VerificationUpdate
from app.database import verification_collection, property_collection, document_collection
from app.schemas.property_status import PropertyStatus

router = APIRouter()


def verification_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "property_id": doc.get("property_id"),
        "submitted_by": doc.get("submitted_by"),
        "document_ids": doc.get("document_ids", []),
        "status": doc.get("status", "under_review"),
        "notes": doc.get("notes"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


@router.post("/properties/{property_id}")
async def submit_verification(
    property_id: str,
    payload: VerificationSubmit,
    current_user: dict = Depends(require_seller)
):
    try:
        obj_id = ObjectId(property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    prop = await property_collection.find_one({"_id": obj_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    if prop.get("seller_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="You can only submit your own property")

    valid_docs = []
    for did in payload.document_ids:
        try:
            doc = await document_collection.find_one({"_id": ObjectId(did)})
            if doc:
                valid_docs.append(did)
        except Exception:
            continue

    if not valid_docs:
        raise HTTPException(status_code=400, detail="No valid documents provided")

    now = datetime.utcnow()
    doc = {
        "property_id": property_id,
        "submitted_by": str(current_user["_id"]),
        "document_ids": valid_docs,
        "status": "under_review",
        "notes": payload.notes,
        "created_at": now,
        "updated_at": now,
    }

    result = await verification_collection.insert_one(doc)

    await property_collection.update_one(
        {"_id": obj_id},
        {"$set": {"status": PropertyStatus.UNDER_VERIFICATION.value}}
    )

    return {
        "property_id": property_id,
        "status": "under_review",
        "verification_id": str(result.inserted_id)
    }


@router.patch("/{verification_id}")
async def update_verification(
    verification_id: str,
    payload: VerificationUpdate,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admin can update verifications")

    try:
        obj_id = ObjectId(verification_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid verification ID format")

    ver = await verification_collection.find_one({"_id": obj_id})
    if not ver:
        raise HTTPException(status_code=404, detail="Verification not found")

    now = datetime.utcnow()
    await verification_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": payload.status,
            "notes": payload.notes or ver.get("notes"),
            "updated_at": now
        }}
    )

    status_map = {
        "verified": PropertyStatus.AVAILABLE.value,
        "rejected": PropertyStatus.REJECTED.value,
        "under_review": PropertyStatus.UNDER_VERIFICATION.value
    }

    new_prop_status = status_map.get(payload.status, PropertyStatus.UNDER_VERIFICATION.value)

    try:
        prop_obj_id = ObjectId(ver["property_id"])
        await property_collection.update_one(
            {"_id": prop_obj_id},
            {"$set": {"status": new_prop_status}}
        )
    except Exception:
        pass

    return {
        "id": verification_id,
        "status": payload.status
    }