from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId
from datetime import date

from app.database import property_collection, user_collection, property_view_collection
from app.routes.auth import get_current_user, require_seller
from app.utils.storage import save_media_file, delete_media_file
from app.schemas.property import MediaResponse, ComparePropertiesRequest
from app.schemas.property_status import PropertyStatus

router = APIRouter()


class LocationModel(BaseModel):
    type: str = "Point"
    coordinates: List[float]


class PropertyCreate(BaseModel):
    title: str
    description: str
    property_type: str
    city: str
    locality: str
    address: str
    price: float
    area: float
    bedrooms: int
    bathrooms: int
    floor: int
    total_floors: int
    furnishing: str
    parking: str
    amenities: List[str]
    images: List[str]
    videos: List[str]
    virtual_tour_url: str
    seller_id: str
    status: str
    location: LocationModel = None


class PropertyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    property_type: Optional[str] = None
    city: Optional[str] = None
    locality: Optional[str] = None
    address: Optional[str] = None
    price: Optional[float] = None
    area: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    furnishing: Optional[str] = None
    parking: Optional[str] = None
    amenities: Optional[List[str]] = None
    images: Optional[List[str]] = None
    videos: Optional[List[str]] = None
    virtual_tour_url: Optional[str] = None


def property_serializer(property) -> dict:
    media_list = property.get("media", [])
    return {
        "id": str(property["_id"]),
        "title": property["title"],
        "description": property["description"],
        "property_type": property["property_type"],
        "city": property["city"],
        "locality": property["locality"],
        "address": property["address"],
        "price": property["price"],
        "area": property["area"],
        "bedrooms": property["bedrooms"],
        "bathrooms": property["bathrooms"],
        "floor": property["floor"],
        "total_floors": property["total_floors"],
        "furnishing": property["furnishing"],
        "parking": property["parking"],
        "amenities": property["amenities"],
        "images": property["images"],
        "videos": property["videos"],
        "virtual_tour_url": property["virtual_tour_url"],
        "seller_id": property["seller_id"],
        "status": property["status"],
        "media": media_list,
        "media_urls": [m["url"] for m in media_list if m.get("url")],
    }


@router.get("/")
async def get_properties(
    city: str = None,
    locality: str = None,
    property_type: str = None,
    status: str = None,
    min_price: float = None,
    max_price: float = None,
    min_area: float = None,
    max_area: float = None,
    bedrooms: int = None,
    bathrooms: int = None,
    furnishing: str = None,
    min_floor: int = None,
    max_floor: int = None,
    search: str = None,
    amenities: str = None,
    seller_id: str = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = 1,
    limit: int = 10,
):
    query = {}

    if city:
        query["city"] = {"$regex": city, "$options": "i"}

    if locality:
        query["locality"] = {"$regex": locality, "$options": "i"}

    if property_type:
        query["property_type"] = {"$regex": property_type, "$options": "i"}

    if status:
        query["status"] = status.lower()

    if furnishing:
        query["furnishing"] = {"$regex": furnishing, "$options": "i"}

    if seller_id:
        query["seller_id"] = seller_id

    if min_price is not None or max_price is not None:
        query["price"] = {}
        if min_price is not None:
            query["price"]["$gte"] = min_price
        if max_price is not None:
            query["price"]["$lte"] = max_price

    if min_area is not None or max_area is not None:
        query["area"] = {}
        if min_area is not None:
            query["area"]["$gte"] = min_area
        if max_area is not None:
            query["area"]["$lte"] = max_area

    if bedrooms is not None:
        query["bedrooms"] = bedrooms

    if bathrooms is not None:
        query["bathrooms"] = bathrooms

    if min_floor is not None or max_floor is not None:
        query["floor"] = {}
        if min_floor is not None:
            query["floor"]["$gte"] = min_floor
        if max_floor is not None:
            query["floor"]["$lte"] = max_floor

    if amenities:
        amenity_list = [a.strip() for a in amenities.split(",")]
        query["amenities"] = {"$all": amenity_list}

    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"locality": {"$regex": search, "$options": "i"}},
            {"address": {"$regex": search, "$options": "i"}},
        ]

    valid_sort_fields = ["price", "area", "created_at", "bedrooms", "bathrooms"]
    if sort_by not in valid_sort_fields:
        sort_by = "created_at"

    sort_direction = -1 if sort_order.lower() == "desc" else 1

    skip = (page - 1) * limit

    total = await property_collection.count_documents(query)

    cursor = property_collection.find(query).sort(sort_by, sort_direction).skip(skip).limit(limit)

    results = []
    async for prop in cursor:
        results.append(property_serializer(prop))

    return {
        "count": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit,
        "results": results,
    }


@router.get("/search")
async def search_properties(
    city: str = None,
    locality: str = None,
    property_type: str = None,
    status: str = None,
    min_price: float = None,
    max_price: float = None,
    min_area: float = None,
    max_area: float = None,
    bedrooms: int = None,
    bathrooms: int = None,
    furnishing: str = None,
    min_floor: int = None,
    max_floor: int = None,
    search: str = None,
    amenities: str = None,
    seller_id: str = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = 1,
    limit: int = 10,
):
    return await get_properties(
        city=city,
        locality=locality,
        property_type=property_type,
        status=status,
        min_price=min_price,
        max_price=max_price,
        min_area=min_area,
        max_area=max_area,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        furnishing=furnishing,
        min_floor=min_floor,
        max_floor=max_floor,
        search=search,
        amenities=amenities,
        seller_id=seller_id,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        limit=limit,
    )


@router.get("/nearby")
async def get_nearby_properties(
    latitude: float,
    longitude: float,
    radius_km: float = 5.0,
    limit: int = 20,
):
    radius_meters = radius_km * 1000

    query = {
        "location": {
            "$near": {
                "$geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                },
                "$maxDistance": radius_meters,
            }
        }
    }

    results = []
    cursor = property_collection.find(query).limit(limit)

    async for prop in cursor:
        item = property_serializer(prop)
        if "location" in prop:
            item["location"] = prop["location"]
        results.append(item)

    return {
        "count": len(results),
        "center": {"latitude": latitude, "longitude": longitude},
        "radius_km": radius_km,
        "results": results,
    }


@router.post("/compare")
async def compare_properties(
    request: ComparePropertiesRequest,
    current_user: dict = Depends(get_current_user)
):
    if len(request.property_ids) < 2 or len(request.property_ids) > 3:
        raise HTTPException(
            status_code=400,
            detail="You can compare between 2 and 3 properties only",
        )

    unique_ids = list(set(request.property_ids))
    if len(unique_ids) != len(request.property_ids):
        raise HTTPException(status_code=400, detail="Duplicate property IDs found")

    object_ids = []
    for pid in request.property_ids:
        try:
            object_ids.append(ObjectId(pid))
        except Exception:
            raise HTTPException(
                status_code=400, detail=f"Invalid property ID format: {pid}"
            )

    properties = []
    async for prop in property_collection.find({"_id": {"$in": object_ids}}):
        properties.append(property_serializer(prop))

    if len(properties) != len(request.property_ids):
        raise HTTPException(status_code=404, detail="One or more properties not found")

    id_to_prop = {prop["id"]: prop for prop in properties}
    ordered_properties = [
        id_to_prop[pid] for pid in request.property_ids if pid in id_to_prop
    ]

    return {"count": len(ordered_properties), "properties": ordered_properties}


@router.get("/{property_id}")
async def get_property(property_id: str):
    try:
        obj_id = ObjectId(property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    prop = await property_collection.find_one({"_id": obj_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    today = date.today().isoformat()
    await property_view_collection.update_one(
        {"property_id": property_id, "date": today},
        {"$inc": {"views": 1}},
        upsert=True,
    )

    return {"success": True, "property": property_serializer(prop)}


@router.post("/")
async def create_property(
    property_data: PropertyCreate,
    current_user: dict = Depends(require_seller),
):
    data = property_data.dict()
    data["seller_id"] = str(current_user["_id"])
    data["status"] = PropertyStatus.PENDING.value

    result = await property_collection.insert_one(data)

    return {
        "success": True,
        "message": "Property created successfully",
        "property_id": str(result.inserted_id),
    }


@router.patch("/{property_id}")
async def update_property(
    property_id: str,
    property_data: PropertyUpdate,
    current_user: dict = Depends(require_seller),
):
    try:
        obj_id = ObjectId(property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    existing = await property_collection.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Property not found")

    if existing["seller_id"] != str(current_user["_id"]) and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="You can only edit your own properties"
        )

    update_fields = property_data.dict(exclude_unset=True)

    await property_collection.update_one(
        {"_id": obj_id},
        {"$set": update_fields}
    )

    return {"success": True, "message": "Property updated successfully"}


@router.delete("/{property_id}")
async def delete_property(
    property_id: str,
    current_user: dict = Depends(require_seller),
):
    try:
        obj_id = ObjectId(property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    existing = await property_collection.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Property not found")

    if existing["seller_id"] != str(current_user["_id"]) and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own properties"
        )

    await property_collection.delete_one({"_id": obj_id})

    return {"success": True, "message": "Property deleted successfully"}


@router.post("/{property_id}/assign-agent")
async def assign_agent(
    property_id: str,
    payload: dict,
    current_user: dict = Depends(require_seller),
):
    try:
        obj_id = ObjectId(property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    prop = await property_collection.find_one({"_id": obj_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    if prop.get("seller_id") != str(current_user["_id"]) and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your property")

    agent_id = payload.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")

    try:
        agent = await user_collection.find_one({"_id": ObjectId(agent_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid agent ID")

    if not agent or agent.get("role") != "agent":
        raise HTTPException(status_code=400, detail="User is not an agent")

    await property_collection.update_one(
        {"_id": obj_id},
        {"$set": {"assigned_agent_id": agent_id}}
    )

    return {"id": property_id, "assigned_agent_id": agent_id}


@router.post("/{property_id}/media", response_model=MediaResponse)
async def upload_property_media(
    property_id: str,
    file: UploadFile = File(...),
    media_type: str = Form("image"),
    current_user: dict = Depends(require_seller),
):
    try:
        obj_id = ObjectId(property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    prop = await property_collection.find_one({"_id": obj_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    if prop.get("seller_id") != str(current_user["_id"]):
        raise HTTPException(
            status_code=403,
            detail="You can only upload media for your own properties",
        )

    try:
        result = await save_media_file(file, property_id, media_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await property_collection.update_one(
        {"_id": obj_id}, {"$push": {"media": result}}
    )

    return {
        "media_id": result["media_id"],
        "url": result["url"],
        "media_type": result["media_type"],
        "filename": result["filename"],
    }


@router.delete("/{property_id}/media/{media_id}")
async def delete_property_media(
    property_id: str,
    media_id: str,
    current_user: dict = Depends(require_seller),
):
    try:
        obj_id = ObjectId(property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    prop = await property_collection.find_one({"_id": obj_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    if prop.get("seller_id") != str(current_user["_id"]):
        raise HTTPException(
            status_code=403,
            detail="You can only delete media from your own properties",
        )

    media_list = prop.get("media", [])
    media_item = next((m for m in media_list if m["media_id"] == media_id), None)

    if not media_item:
        raise HTTPException(status_code=404, detail="Media not found")

    delete_media_file(property_id, media_item["url"])

    await property_collection.update_one(
        {"_id": obj_id}, {"$pull": {"media": {"media_id": media_id}}}
    )

    return {"message": "Media deleted"}
