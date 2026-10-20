from fastapi import APIRouter, HTTPException, Depends, Request
from bson import ObjectId
from datetime import datetime
import uuid
import hmac
import hashlib
import os

from app.routes.auth import get_current_user
from app.schemas.payment import PaymentOrderCreate, PaymentVerify, PaymentWebhook
from app.database import payment_collection, booking_collection
from app.utils.notification_helper import create_notification

router = APIRouter()

GATEWAY_SECRET = os.getenv("GATEWAY_SECRET", "test_secret_key_for_development")


def verify_gateway_signature(order_id: str, payment_id: str, signature: str) -> bool:
    expected = hmac.new(
        GATEWAY_SECRET.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def payment_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "booking_id": doc.get("booking_id"),
        "buyer_id": doc.get("buyer_id"),
        "amount": doc.get("amount"),
        "currency": doc.get("currency", "INR"),
        "gateway_order_id": doc.get("gateway_order_id"),
        "gateway_payment_id": doc.get("gateway_payment_id"),
        "status": doc.get("status", "created"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


@router.post("/order")
async def create_payment_order(
    payload: PaymentOrderCreate,
    current_user: dict = Depends(get_current_user)
):
    try:
        booking_obj_id = ObjectId(payload.booking_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")

    booking = await booking_collection.find_one({"_id": booking_obj_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.get("buyer_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="You can only pay for your own booking")

    if booking.get("status") != "payment_pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pay for booking with status: {booking.get('status')}"
        )

    total_paid = 0
    async for p in payment_collection.find({
        "booking_id": payload.booking_id,
        "status": "paid"
    }):
        total_paid += p.get("amount", 0)

    total_pending_orders = 0
    async for p in payment_collection.find({
        "booking_id": payload.booking_id,
        "status": "created"
    }):
        total_pending_orders += p.get("amount", 0)

    remaining = booking["booking_amount"] - total_paid - total_pending_orders

    if payload.amount > remaining:
        raise HTTPException(
            status_code=400,
            detail=f"Amount exceeds remaining booking amount: ₹{remaining}"
        )

    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    gateway_order_id = f"order_{uuid.uuid4().hex[:16]}"

    now = datetime.utcnow()
    doc = {
        "booking_id": payload.booking_id,
        "buyer_id": str(current_user["_id"]),
        "amount": payload.amount,
        "currency": payload.currency,
        "gateway_order_id": gateway_order_id,
        "status": "created",
        "created_at": now,
        "updated_at": now,
    }

    result = await payment_collection.insert_one(doc)

    return {
        "payment_id": str(result.inserted_id),
        "gateway_order_id": gateway_order_id,
        "status": "created"
    }


@router.post("/verify")
async def verify_payment(
    payload: PaymentVerify,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(payload.payment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payment ID format")

    payment = await payment_collection.find_one({"_id": obj_id})
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.get("buyer_id") != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="You can only verify your own payment")

    if payment.get("status") == "paid":
        return {"payment_id": payload.payment_id, "status": "paid"}

    if payment.get("gateway_order_id") != payload.gateway_order_id:
        raise HTTPException(status_code=400, detail="Order ID mismatch")

    if not verify_gateway_signature(
        payload.gateway_order_id,
        payload.gateway_payment_id,
        payload.signature
    ):
        raise HTTPException(status_code=400, detail="Invalid signature")

    now = datetime.utcnow()
    await payment_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": "paid",
            "gateway_payment_id": payload.gateway_payment_id,
            "updated_at": now
        }}
    )

    total_paid = 0
    async for p in payment_collection.find({
        "booking_id": payment["booking_id"],
        "status": "paid"
    }):
        total_paid += p.get("amount", 0)

    booking = await booking_collection.find_one({"_id": ObjectId(payment["booking_id"])})
    if booking and total_paid >= booking.get("booking_amount", 0):
        await booking_collection.update_one(
            {"_id": ObjectId(payment["booking_id"])},
            {"$set": {"status": "confirmed", "updated_at": now}}
        )

    await create_notification(
        user_id=payment.get("buyer_id"),
        title="Payment successful ",
        body=f"₹{payment.get('amount', 0):,} received",
        notif_type="payment_received",
        reference_id=payload.payment_id,
        reference_type="payment",
    )

    return {
        "payment_id": payload.payment_id,
        "status": "paid"
    }


@router.post("/webhook")
async def payment_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature header")

    expected = hmac.new(
        GATEWAY_SECRET.encode(),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    valid_statuses = ["created", "paid", "failed", "refunded"]
    status = payload.get("status")
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")

    payment_id = payload.get("payment_id")
    if not payment_id:
        raise HTTPException(status_code=400, detail="Missing payment_id")

    try:
        obj_id = ObjectId(payment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payment ID format")

    payment = await payment_collection.find_one({"_id": obj_id})
    if not payment:
        return {"received": True, "note": "Payment not found"}

    now = datetime.utcnow()
    await payment_collection.update_one(
        {"_id": obj_id},
        {"$set": {"status": status, "updated_at": now}}
    )

    if status == "paid":
        try:
            booking_obj_id = ObjectId(payment["booking_id"])
            await booking_collection.update_one(
                {"_id": booking_obj_id},
                {"$set": {"status": "confirmed", "updated_at": now}}
            )
        except Exception:
            pass

    return {"received": True}


@router.get("/{payment_id}")
async def get_payment(
    payment_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(payment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payment ID format")

    payment = await payment_collection.find_one({"_id": obj_id})
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    user_id = str(current_user["_id"])
    role = current_user.get("role")
    is_participant = payment.get("buyer_id") == user_id or role == "admin"

    if not is_participant:
        try:
            booking = await booking_collection.find_one({"_id": ObjectId(payment["booking_id"])})
            if booking and booking.get("seller_id") == user_id:
                is_participant = True
        except Exception:
            pass

    if not is_participant:
        raise HTTPException(status_code=403, detail="Not authorized")

    return payment_serializer(payment)