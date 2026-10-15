from datetime import datetime
from app.database import (
    user_collection,
    property_collection,
    booking_collection,
    payment_collection,
    audit_log_collection,
)


async def log_admin_action(admin_id: str, action: str, target: str = None, details: dict = None):
    doc = {
        "admin_id": admin_id,
        "action": action,
        "target": target,
        "details": details or {},
        "created_at": datetime.utcnow(),
    }
    await audit_log_collection.insert_one(doc)


async def get_platform_stats() -> dict:
    total_users = await user_collection.count_documents({})
    total_properties = await property_collection.count_documents({})
    total_bookings = await booking_collection.count_documents({})

    payments_total = 0
    async for p in payment_collection.find({"status": "paid"}):
        payments_total += p.get("amount", 0)

    return {
        "users": total_users,
        "properties": total_properties,
        "bookings": total_bookings,
        "payments_total": payments_total,
    }