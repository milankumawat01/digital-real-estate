from fastapi import APIRouter, HTTPException, Depends
from bson import ObjectId

from app.routes.auth import get_current_user
from app.schemas.ai import (
    AssistantRequest,
    VoiceSearchRequest,
    RecommendationsRequest,
    PriceEstimationRequest,
)
from app.database import property_collection
from app.routes.properties import property_serializer
from app.utils.ai_helpers import extract_filters, build_reply, estimate_price

router = APIRouter()


CITY_PRICE_PER_SQFT = {
    "jaipur": 4000,
    "delhi": 12000,
    "mumbai": 25000,
    "bangalore": 8000,
    "bengaluru": 8000,
    "pune": 7000,
    "hyderabad": 6000,
    "chennai": 7500,
    "kolkata": 5500,
    "ahmedabad": 4500,
    "gurgaon": 10000,
    "noida": 7000,
}


async def search_properties_by_filters(filters: dict, limit: int = 10) -> list:
    query = {}

    if "bhk" in filters:
        query["bedrooms"] = filters["bhk"]

    if "max_budget" in filters:
        query["price"] = {"$lte": filters["max_budget"]}

    if "city" in filters:
        query["city"] = {"$regex": filters["city"], "$options": "i"}

    if "property_type" in filters:
        query["property_type"] = {"$regex": filters["property_type"], "$options": "i"}

    if "amenities" in filters and filters["amenities"]:
        query["amenities"] = {"$all": filters["amenities"]}

    if filters.get("parking"):
        query["parking"] = {"$regex": "car", "$options": "i"}

    # ✅ Hamesha available properties hi dikhao
    query["status"] = "available"

    results = []
    async for prop in property_collection.find(query).limit(limit):
        results.append(property_serializer(prop))

    return results


@router.post("/property-assistant")
async def property_assistant(
    payload: AssistantRequest,
    current_user: dict = Depends(get_current_user)
):
    filters = extract_filters(payload.message)

    if not filters:
        return {
            "reply": "Please tell me what you're looking for — for example, '3 BHK in Jaipur under 75 lakh with parking'.",
            "filters": {},
            "property_ids": []
        }

    properties = await search_properties_by_filters(filters)
    reply = build_reply(filters, len(properties))

    return {
        "reply": reply,
        "filters": filters,
        "property_ids": [p["id"] for p in properties],
        "properties": properties
    }


@router.post("/voice-search")
async def voice_search(
    payload: VoiceSearchRequest,
    current_user: dict = Depends(get_current_user)
):
    filters = extract_filters(payload.transcript)

    return {
        "transcript": payload.transcript,
        "filters": filters
    }


@router.post("/recommendations")
async def recommendations(
    payload: RecommendationsRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(payload.property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    base = await property_collection.find_one({"_id": obj_id})
    if not base:
        raise HTTPException(status_code=404, detail="Property not found")

    price = base.get("price", 0)
    price_min = price * 0.75
    price_max = price * 1.25

    query = {
        "_id": {"$ne": obj_id},
        "city": base.get("city"),
        "bedrooms": base.get("bedrooms"),
        "price": {"$gte": price_min, "$lte": price_max},
        "status": "available"
    }

    results = []
    async for prop in property_collection.find(query).limit(payload.limit):
        results.append(property_serializer(prop))

    if len(results) < payload.limit:
        fallback_query = {
            "_id": {"$ne": obj_id},
            "city": base.get("city"),
            "status": "available"
        }
        existing_ids = {p["id"] for p in results}

        async for prop in property_collection.find(fallback_query).limit(payload.limit * 2):
            pid = str(prop["_id"])
            if pid in existing_ids:
                continue
            results.append(property_serializer(prop))
            existing_ids.add(pid)
            if len(results) >= payload.limit:
                break

    return {
        "based_on": payload.property_id,
        "count": len(results),
        "results": results
    }


@router.post("/price-estimation")
async def price_estimation(
    payload: PriceEstimationRequest,
    current_user: dict = Depends(get_current_user)
):
    city_lower = payload.city.lower()
    base_price_per_sqft = CITY_PRICE_PER_SQFT.get(city_lower, 5000)

    if payload.property_type.lower() in ["villa", "house"]:
        base_price_per_sqft *= 1.3
    elif payload.property_type.lower() in ["plot", "land"]:
        base_price_per_sqft *= 0.6
    elif payload.property_type.lower() in ["office", "shop"]:
        base_price_per_sqft *= 1.5

    estimated = estimate_price(
        base_price_per_sqft=base_price_per_sqft,
        area=payload.area_sqft,
        bhk=payload.bhk,
        age=payload.property_age
    )

    low = round(estimated * 0.9, -3)
    high = round(estimated * 1.1, -3)

    return {
        "estimated_price": estimated,
        "range": {"min": low, "max": high},
        "currency": "INR",
        "price_per_sqft": round(base_price_per_sqft, 0),
        "inputs": {
            "property_type": payload.property_type,
            "city": payload.city,
            "locality": payload.locality,
            "area_sqft": payload.area_sqft,
            "bhk": payload.bhk,
            "property_age": payload.property_age
        }
    }