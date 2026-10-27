from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from datetime import datetime

from app.routes.auth import get_current_user, require_buyer
from app.schemas.offer import OfferCreate, CounterOfferRequest, RejectOfferRequest
from app.database import offer_collection, property_collection
from app.utils.notification_helper import create_notification

router = APIRouter()


def offer_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "property_id": doc.get("property_id"),
        "buyer_id": doc.get("buyer_id"),
        "seller_id": doc.get("seller_id"),
        "amount": doc.get("amount"),
        "message": doc.get("message"),
        "status": doc.get("status", "pending"),
        "counter_amount": doc.get("counter_amount"),
        "counter_message": doc.get("counter_message"),
        "last_counter_by": doc.get("last_counter_by"),
        "reject_reason": doc.get("reject_reason"),
        "history": doc.get("history", []),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


@router.post("/")
async def submit_offer(
    offer_data: OfferCreate,
    current_user: dict = Depends(require_buyer)
):
    try:
        obj_id = ObjectId(offer_data.property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    prop = await property_collection.find_one({"_id": obj_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    if prop.get("seller_id") == str(current_user["_id"]):
        raise HTTPException(
            status_code=400,
            detail="You cannot make an offer on your own property"
        )

    existing = await offer_collection.find_one({
        "property_id": offer_data.property_id,
        "buyer_id": str(current_user["_id"]),
        "status": {"$in": ["pending", "countered"]}
    })
    if existing:
        raise HTTPException(
            status_code=400,
            detail="You already have an active offer on this property"
        )

    now = datetime.utcnow()
    doc = {
        "property_id": offer_data.property_id,
        "buyer_id": str(current_user["_id"]),
        "seller_id": prop.get("seller_id"),
        "amount": offer_data.amount,
        "message": offer_data.message,
        "status": "pending",
        "history": [
            {
                "action": "submitted",
                "amount": offer_data.amount,
                "by": str(current_user["_id"]),
                "at": now.isoformat()
            }
        ],
        "created_at": now,
        "updated_at": now,
    }

    result = await offer_collection.insert_one(doc)

    await create_notification(
        user_id=prop.get("seller_id"),
        title="New offer received",
        body=f"Offer of ₹{offer_data.amount:,} on your property",
        notif_type="offer_received",
        reference_id=str(result.inserted_id),
        reference_type="offer",
    )

    return {
        "id": str(result.inserted_id),
        "amount": offer_data.amount,
        "status": "pending"
    }


@router.get("/")
async def list_offers(
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
    cursor = offer_collection.find(query).sort("created_at", -1)
    async for doc in cursor:
        results.append(offer_serializer(doc))

    return {
        "count": len(results),
        "results": results
    }


@router.get("/{offer_id}")
async def get_offer(
    offer_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(offer_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid offer ID format")

    offer = await offer_collection.find_one({"_id": obj_id})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    user_id = str(current_user["_id"])
    role = current_user.get("role")
    is_participant = (
        offer.get("buyer_id") == user_id or
        offer.get("seller_id") == user_id or
        role == "admin"
    )
    if not is_participant:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to view this offer"
        )

    return offer_serializer(offer)


@router.post("/{offer_id}/counter")
async def counter_offer(
    offer_id: str,
    counter_data: CounterOfferRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(offer_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid offer ID format")

    offer = await offer_collection.find_one({"_id": obj_id})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    user_id = str(current_user["_id"])
    is_buyer = offer.get("buyer_id") == user_id
    is_seller = offer.get("seller_id") == user_id
    if not (is_buyer or is_seller):
        raise HTTPException(
            status_code=403,
            detail="Only the buyer or seller can counter this offer"
        )

    if offer.get("status") not in ["pending", "countered"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot counter an offer with status: {offer.get('status')}"
        )

    if offer.get("last_counter_by") == user_id:
        raise HTTPException(
            status_code=403,
            detail="Wait for the other party to respond before countering again"
        )

    now = datetime.utcnow()
    new_history_entry = {
        "action": "countered",
        "amount": counter_data.amount,
        "by": user_id,
        "at": now.isoformat()
    }

    await offer_collection.update_one(
        {"_id": obj_id},
        {
            "$set": {
                "counter_amount": counter_data.amount,
                "counter_message": counter_data.message,
                "status": "countered",
                "last_counter_by": user_id,
                "updated_at": now
            },
            "$push": {"history": new_history_entry}
        }
    )

    other_party = offer.get("buyer_id") if is_seller else offer.get("seller_id")
    await create_notification(
        user_id=other_party,
        title="Counter offer received",
        body=f"Counter of ₹{counter_data.amount:,}",
        notif_type="offer_countered",
        reference_id=offer_id,
        reference_type="offer",
    )

    return {
        "id": offer_id,
        "amount": counter_data.amount,
        "status": "countered"
    }


@router.post("/{offer_id}/accept")
async def accept_offer(
    offer_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(offer_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid offer ID format")

    offer = await offer_collection.find_one({"_id": obj_id})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    user_id = str(current_user["_id"])
    role = current_user.get("role")

    is_buyer = offer.get("buyer_id") == user_id
    is_seller = offer.get("seller_id") == user_id
    is_admin = role == "admin"

    if not (is_buyer or is_seller or is_admin):
        raise HTTPException(
            status_code=403,
            detail="Not a participant in this offer"
        )

    if offer.get("status") == "countered":
        if offer.get("last_counter_by") == user_id:
            raise HTTPException(
                status_code=403,
                detail="You cannot accept your own counter-offer"
            )
    elif not (is_seller or is_admin):
        raise HTTPException(
            status_code=403,
            detail="Only the seller can accept a pending offer"
        )

    if offer.get("status") not in ["pending", "countered"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot accept an offer with status: {offer.get('status')}"
        )

    reserved = await property_collection.find_one_and_update(
        {
            "_id": ObjectId(offer["property_id"]),
            "status": {"$in": ["available", "pending"]}
        },
        {"$set": {"status": "reserved"}}
    )

    if not reserved:
        raise HTTPException(
            status_code=409,
            detail="Property is already sold or reserved"
        )

    await offer_collection.update_many(
        {
            "property_id": offer["property_id"],
            "_id": {"$ne": obj_id},
            "status": {"$in": ["pending", "countered"]}
        },
        {"$set": {
            "status": "rejected",
            "reject_reason": "Property sold to another buyer"
        }}
    )

    now = datetime.utcnow()

    await offer_collection.update_one(
        {"_id": obj_id},
        {
            "$set": {"status": "accepted", "updated_at": now},
            "$push": {
                "history": {
                    "action": "accepted",
                    "by": user_id,
                    "at": now.isoformat()
                }
            }
        }
    )

    return {
        "id": offer_id,
        "status": "accepted"
    }


@router.post("/{offer_id}/reject")
async def reject_offer(
    offer_id: str,
    reject_data: RejectOfferRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(offer_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid offer ID format")

    offer = await offer_collection.find_one({"_id": obj_id})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    user_id = str(current_user["_id"])
    role = current_user.get("role")
    is_seller = offer.get("seller_id") == user_id
    is_admin = role == "admin"
    if not (is_seller or is_admin):
        raise HTTPException(
            status_code=403,
            detail="Only the seller or admin can reject this offer"
        )

    if offer.get("status") not in ["pending", "countered"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject an offer with status: {offer.get('status')}"
        )

    now = datetime.utcnow()

    await offer_collection.update_one(
        {"_id": obj_id},
        {
            "$set": {
                "status": "rejected",
                "reject_reason": reject_data.reason,
                "updated_at": now
            },
            "$push": {
                "history": {
                    "action": "rejected",
                    "reason": reject_data.reason,
                    "by": user_id,
                    "at": now.isoformat()
                }
            }
        }
    )

    return {
        "id": offer_id,
        "status": "rejected"
    }


@router.get("/{offer_id}/history")
async def get_offer_history(
    offer_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(offer_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid offer ID format")

    offer = await offer_collection.find_one({"_id": obj_id})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    user_id = str(current_user["_id"])
    role = current_user.get("role")
    is_participant = (
        offer.get("buyer_id") == user_id or
        offer.get("seller_id") == user_id or
        role == "admin"
    )
    if not is_participant:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to view this offer's history"
        )

    return {
        "offer_id": offer_id,
        "history": offer.get("history", [])
    }
