from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from datetime import datetime

from app.routes.auth import get_current_user
from app.schemas.booking import BookingCreate, BookingUpdate
from app.database import (
    booking_collection,
    property_collection,
    offer_collection,
    payment_collection,
)
from app.utils.notification_helper import create_notification

router = APIRouter()


def booking_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "property_id": doc.get("property_id"),
        "offer_id": doc.get("offer_id"),
        "buyer_id": doc.get("buyer_id"),
        "seller_id": doc.get("seller_id"),
        "agreed_price": doc.get("agreed_price"),
        "booking_amount": doc.get("booking_amount"),
        "status": doc.get("status", "payment_pending"),
        "notes": doc.get("notes"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


@router.post("/")
async def create_booking(
    payload: BookingCreate,
    current_user: dict = Depends(get_current_user)
):
    try:
        prop_obj_id = ObjectId(payload.property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    prop = await property_collection.find_one({"_id": prop_obj_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    try:
        offer_obj_id = ObjectId(payload.offer_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid offer ID format")

    offer = await offer_collection.find_one({"_id": offer_obj_id})
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    if offer.get("status") != "accepted":
        raise HTTPException(
            status_code=400,
            detail="Offer must be accepted before creating a booking"
        )

    if offer.get("buyer_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="You can only book your own offer")

    if offer.get("property_id") != payload.property_id:
        raise HTTPException(status_code=400, detail="Property mismatch with offer")

    existing = await booking_collection.find_one({
        "offer_id": payload.offer_id,
        "status": {"$ne": "cancelled"}
    })
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A booking already exists for this offer"
        )

    agreed_price = offer.get("counter_amount") or offer.get("amount")
    booking_amount = payload.booking_amount

    if booking_amount > agreed_price:
        raise HTTPException(
            status_code=400,
            detail="Booking amount cannot exceed agreed price"
        )

    now = datetime.utcnow()
    doc = {
        "property_id": payload.property_id,
        "offer_id": payload.offer_id,
        "buyer_id": str(current_user["_id"]),
        "seller_id": prop.get("seller_id"),
        "agreed_price": agreed_price,
        "booking_amount": booking_amount,
        "status": "payment_pending",
        "created_at": now,
        "updated_at": now,
    }

    result = await booking_collection.insert_one(doc)

    await create_notification(
        user_id=prop.get("seller_id"),
        title="New booking created",
        body=f"Buyer booked your property for ₹{agreed_price:,}",
        notif_type="booking_created",
        reference_id=str(result.inserted_id),
        reference_type="booking",
    )

    return {
        "id": str(result.inserted_id),
        "status": "payment_pending"
    }


@router.get("/")
async def list_bookings(
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
    async for doc in booking_collection.find(query).sort("created_at", -1):
        results.append(booking_serializer(doc))

    return {
        "count": len(results),
        "results": results
    }


@router.get("/{booking_id}")
async def get_booking(
    booking_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")

    booking = await booking_collection.find_one({"_id": obj_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    user_id = str(current_user["_id"])
    role = current_user.get("role")
    is_participant = (
        booking.get("buyer_id") == user_id or
        booking.get("seller_id") == user_id or
        role == "admin"
    )
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not authorized to view this booking")

    return booking_serializer(booking)


@router.patch("/{booking_id}")
async def update_booking(
    booking_id: str,
    payload: BookingUpdate,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")

    booking = await booking_collection.find_one({"_id": obj_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    user_id = str(current_user["_id"])
    role = current_user.get("role")
    is_seller = booking.get("seller_id") == user_id
    is_admin = role == "admin"
    if not (is_seller or is_admin):
        raise HTTPException(
            status_code=403,
            detail="Only the seller or admin can update this booking"
        )

    VALID_TRANSITIONS = {
        "payment_pending": ["confirmed", "cancelled"],
        "confirmed": ["completed", "cancelled"],
        "cancelled": [],
        "completed": []
    }

    current_status = booking.get("status")
    if payload.status not in VALID_TRANSITIONS.get(current_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current_status} to {payload.status}"
        )

    now = datetime.utcnow()
    await booking_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": payload.status,
            "notes": payload.notes,
            "updated_at": now
        }}
    )

    if payload.status == "cancelled":
        try:
            prop_obj_id = ObjectId(booking["property_id"])
            await property_collection.update_one(
                {"_id": prop_obj_id},
                {"$set": {"status": "available"}}
            )
        except Exception:
            pass

    if payload.status in ["confirmed", "completed"]:
        try:
            prop_obj_id = ObjectId(booking["property_id"])
            await property_collection.update_one(
                {"_id": prop_obj_id},
                {"$set": {"status": "sold"}}
            )
        except Exception:
            pass

    if payload.status == "confirmed":
        await create_notification(
            user_id=booking.get("buyer_id"),
            title="Booking confirmed ",
            body="Your booking has been confirmed by the seller.",
            notif_type="booking_confirmed",
            reference_id=booking_id,
            reference_type="booking",
        )

    return {
        "id": booking_id,
        "status": payload.status
    }


@router.get("/{booking_id}/payments")
async def get_booking_payments(
    booking_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(booking_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")

    booking = await booking_collection.find_one({"_id": obj_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    user_id = str(current_user["_id"])
    role = current_user.get("role")
    is_participant = (
        booking.get("buyer_id") == user_id or
        booking.get("seller_id") == user_id or
        role == "admin"
    )
    if not is_participant:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to view payments for this booking"
        )

    results = []
    total_paid = 0
    async for doc in payment_collection.find({"booking_id": booking_id}).sort("created_at", -1):
        results.append({
            "id": str(doc["_id"]),
            "amount": doc.get("amount"),
            "currency": doc.get("currency", "INR"),
            "status": doc.get("status"),
            "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        })
        if doc.get("status") == "paid":
            total_paid += doc.get("amount", 0)

    return {
        "booking_id": booking_id,
        "booking_amount": booking.get("booking_amount"),
        "total_paid": total_paid,
        "payments": results
    }