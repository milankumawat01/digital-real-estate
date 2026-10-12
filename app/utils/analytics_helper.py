from app.database import (
    property_collection,
    offer_collection,
    site_visit_collection,
    booking_collection,
    conversation_collection,
    message_collection,
)


async def get_seller_analytics(seller_id: str) -> dict:
    total_properties = await property_collection.count_documents({
        "seller_id": seller_id
    })

    available_properties = await property_collection.count_documents({
        "seller_id": seller_id,
        "status": "AVAILABLE"
    })

    sold_properties = await property_collection.count_documents({
        "seller_id": seller_id,
        "status": "SOLD"
    })

    total_offers = await offer_collection.count_documents({
        "seller_id": seller_id
    })

    pending_offers = await offer_collection.count_documents({
        "seller_id": seller_id,
        "status": "pending"
    })

    accepted_offers = await offer_collection.count_documents({
        "seller_id": seller_id,
        "status": "accepted"
    })

    total_site_visits = await site_visit_collection.count_documents({
        "seller_id": seller_id
    })

    pending_site_visits = await site_visit_collection.count_documents({
        "seller_id": seller_id,
        "status": "pending"
    })

    total_bookings = await booking_collection.count_documents({
        "seller_id": seller_id
    })

    confirmed_bookings = await booking_collection.count_documents({
        "seller_id": seller_id,
        "status": "confirmed"
    })

    conversation_ids = []
    async for conv in conversation_collection.find({
        "participants": seller_id
    }):
        conversation_ids.append(str(conv["_id"]))

    total_messages_received = 0
    if conversation_ids:
        total_messages_received = await message_collection.count_documents({
            "conversation_id": {"$in": conversation_ids},
            "sender_id": {"$ne": seller_id}
        })

    views_estimate = total_properties * 50 + total_site_visits * 10 + total_offers * 5

    return {
        "properties": {
            "total": total_properties,
            "available": available_properties,
            "sold": sold_properties,
        },
        "inquiries": {
            "total_offers": total_offers,
            "pending_offers": pending_offers,
            "accepted_offers": accepted_offers,
            "total_site_visits": total_site_visits,
            "pending_site_visits": pending_site_visits,
            "total_messages": total_messages_received,
        },
        "bookings": {
            "total": total_bookings,
            "confirmed": confirmed_bookings,
        },
        "views": views_estimate,
        "inquiries_count": total_offers + total_site_visits + total_messages_received,
        "site_visits_count": total_site_visits,
        "offers_count": total_offers,
        "bookings_count": total_bookings,
    }