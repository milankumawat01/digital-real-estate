from app.database import (
    project_collection,
    tower_collection,
    floor_collection,
    unit_collection,
    booking_collection,
)


def project_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name"),
        "city": doc.get("city"),
        "locality": doc.get("locality"),
        "address": doc.get("address"),
        "description": doc.get("description"),
        "status": doc.get("status", "planning"),
        "construction_progress": doc.get("construction_progress", 0),
        "rera_number": doc.get("rera_number"),
        "possession_date": doc.get("possession_date"),
        "builder_id": doc.get("builder_id"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


def tower_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "project_id": doc.get("project_id"),
        "name": doc.get("name"),
        "total_floors": doc.get("total_floors"),
        "builder_id": doc.get("builder_id"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
    }


def floor_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "tower_id": doc.get("tower_id"),
        "project_id": doc.get("project_id"),
        "floor_number": doc.get("floor_number"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
    }


def unit_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "floor_id": doc.get("floor_id"),
        "tower_id": doc.get("tower_id"),
        "project_id": doc.get("project_id"),
        "unit_number": doc.get("unit_number"),
        "bhk": doc.get("bhk"),
        "area_sqft": doc.get("area_sqft"),
        "price": doc.get("price"),
        "status": doc.get("status", "available"),
        "facing": doc.get("facing"),
        "parking": doc.get("parking", 0),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
    }


async def get_project_analytics(project_id: str) -> dict:
    total_units = await unit_collection.count_documents({"project_id": project_id})

    available_units = await unit_collection.count_documents({
        "project_id": project_id,
        "status": "available"
    })

    reserved_units = await unit_collection.count_documents({
        "project_id": project_id,
        "status": "reserved"
    })

    sold_units = await unit_collection.count_documents({
        "project_id": project_id,
        "status": "sold"
    })

    total_towers = await tower_collection.count_documents({"project_id": project_id})

    total_floors = await floor_collection.count_documents({"project_id": project_id})

    bookings = await booking_collection.count_documents({"project_id": project_id})

    revenue = 0
    async for unit in unit_collection.find({
        "project_id": project_id,
        "status": "sold"
    }):
        revenue += unit.get("price", 0)

    return {
        "total_units": total_units,
        "available_units": available_units,
        "reserved_units": reserved_units,
        "sold_units": sold_units,
        "total_towers": total_towers,
        "total_floors": total_floors,
        "bookings": bookings,
        "sales": sold_units,
        "revenue": revenue,
    }