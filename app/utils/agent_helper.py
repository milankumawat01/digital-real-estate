from app.database import lead_collection, commission_collection


def lead_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "agent_id": doc.get("agent_id"),
        "name": doc.get("name"),
        "mobile": doc.get("mobile"),
        "email": doc.get("email"),
        "property_id": doc.get("property_id"),
        "status": doc.get("status", "new"),
        "notes": doc.get("notes"),
        "source": doc.get("source"),
        "next_follow_up": doc.get("next_follow_up"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


def commission_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "agent_id": doc.get("agent_id"),
        "booking_id": doc.get("booking_id"),
        "property_id": doc.get("property_id"),
        "deal_amount": doc.get("deal_amount", 0),
        "commission_percent": doc.get("commission_percent", 0),
        "commission_amount": doc.get("commission_amount", 0),
        "status": doc.get("status", "pending"),
        "paid_at": doc.get("paid_at").isoformat() if doc.get("paid_at") else None,
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
    }