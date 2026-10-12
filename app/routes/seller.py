from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId
from datetime import datetime

from app.routes.auth import get_current_user, require_seller
from app.routes.properties import property_serializer
from app.database import (
    property_collection,
    offer_collection,
    site_visit_collection,
    conversation_collection,
    message_collection,
)
from app.utils.analytics_helper import get_seller_analytics

router = APIRouter()


def site_visit_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "property_id": doc.get("property_id"),
        "buyer_id": doc.get("buyer_id"),
        "date": doc.get("date"),
        "time": doc.get("time"),
        "status": doc.get("status", "pending"),
        "notes": doc.get("notes"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
    }


def offer_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "property_id": doc.get("property_id"),
        "buyer_id": doc.get("buyer_id"),
        "amount": doc.get("amount"),
        "status": doc.get("status", "pending"),
        "message": doc.get("message"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
    }


@router.get("/properties")
async def seller_properties(
    current_user: dict = Depends(require_seller)
):
    seller_id = str(current_user["_id"])

    results = []
    cursor = property_collection.find({"seller_id": seller_id}).sort("created_at", -1)

    async for prop in cursor:
        results.append(property_serializer(prop))

    return {
        "count": len(results),
        "results": results
    }


@router.get("/inquiries")
async def seller_inquiries(
    current_user: dict = Depends(require_seller)
):
    seller_id = str(current_user["_id"])

    offers = []
    async for doc in offer_collection.find({"seller_id": seller_id}).sort("created_at", -1):
        offers.append(offer_serializer(doc))

    site_visits = []
    async for doc in site_visit_collection.find({"seller_id": seller_id}).sort("created_at", -1):
        site_visits.append(site_visit_serializer(doc))

    messages = []
    conversation_ids = []
    async for conv in conversation_collection.find({"participants": seller_id}):
        conversation_ids.append(str(conv["_id"]))

    if conversation_ids:
        async for msg in message_collection.find({
            "conversation_id": {"$in": conversation_ids},
            "sender_id": {"$ne": seller_id}
        }).sort("created_at", -1).limit(50):
            messages.append({
                "id": str(msg["_id"]),
                "conversation_id": msg.get("conversation_id"),
                "sender_id": msg.get("sender_id"),
                "message": msg.get("message"),
                "created_at": msg.get("created_at").isoformat() if msg.get("created_at") else None,
            })

    total = len(offers) + len(site_visits) + len(messages)

    return {
        "count": total,
        "offers": offers,
        "site_visits": site_visits,
        "messages": messages
    }


@router.get("/analytics")
async def seller_analytics(
    current_user: dict = Depends(require_seller)
):
    seller_id = str(current_user["_id"])
    analytics = await get_seller_analytics(seller_id)

    return {
        "views": analytics["views"],
        "inquiries": analytics["inquiries_count"],
        "site_visits": analytics["site_visits_count"],
        "offers": analytics["offers_count"],
        "bookings": analytics["bookings_count"],
        "detailed": analytics
    }