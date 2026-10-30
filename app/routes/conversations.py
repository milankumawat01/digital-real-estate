from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from bson import ObjectId
from datetime import datetime
import os
import uuid

from app.routes.auth import get_current_user
from app.schemas.conversation import ConversationCreate, MessageCreate
from app.database import (
    conversation_collection, message_collection, user_collection, property_collection
)
from app.utils.notification_helper import create_notification

router = APIRouter()

ATTACHMENT_DIR = "uploads/attachments"
os.makedirs(ATTACHMENT_DIR, exist_ok=True)
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024


def conversation_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "property_id": doc.get("property_id"),
        "participants": doc.get("participants", []),
        "last_message": doc.get("last_message"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


def message_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "conversation_id": doc.get("conversation_id"),
        "sender_id": doc.get("sender_id"),
        "message": doc.get("message"),
        "message_type": doc.get("message_type", "text"),
        "attachment_url": doc.get("attachment_url"),
        "property_id": doc.get("property_id"),
        "offer_id": doc.get("offer_id"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
    }


@router.post("/")
async def create_or_get_conversation(
    payload: ConversationCreate,
    current_user: dict = Depends(get_current_user)
):
    user_id = str(current_user["_id"])

    if payload.participant_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot chat with yourself")

    try:
        other = await user_collection.find_one({"_id": ObjectId(payload.participant_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid participant ID")

    if not other:
        raise HTTPException(status_code=404, detail="Participant not found")

    try:
        prop_obj_id = ObjectId(payload.property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID")

    prop = await property_collection.find_one({"_id": prop_obj_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    seller_id = prop.get("seller_id")

    valid_pair = (
        (user_id == seller_id and payload.participant_id != seller_id) or
        (payload.participant_id == seller_id and user_id != seller_id)
    )

    if not valid_pair:
        raise HTTPException(
            status_code=400,
            detail="Conversation must be between a buyer and the property's seller"
        )

    existing = await conversation_collection.find_one({
        "property_id": payload.property_id,
        "participants": {"$all": [user_id, payload.participant_id]}
    })

    if existing:
        return {"conversation_id": str(existing["_id"])}

    now = datetime.utcnow()
    doc = {
        "property_id": payload.property_id,
        "participants": [user_id, payload.participant_id],
        "last_message": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await conversation_collection.insert_one(doc)

    return {"conversation_id": str(result.inserted_id)}


@router.get("/")
async def list_conversations(
    current_user: dict = Depends(get_current_user)
):
    user_id = str(current_user["_id"])

    results = []
    async for doc in conversation_collection.find(
        {"participants": user_id}
    ).sort("updated_at", -1):
        results.append(conversation_serializer(doc))

    return {"count": len(results), "results": results}


@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(conversation_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid conversation ID format")

    conv = await conversation_collection.find_one({"_id": obj_id})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_id = str(current_user["_id"])
    if user_id not in conv.get("participants", []) and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not a participant")

    results = []
    async for msg in message_collection.find(
        {"conversation_id": conversation_id}
    ).sort("created_at", 1):
        results.append(message_serializer(msg))

    return {"count": len(results), "results": results}


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    payload: MessageCreate,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(conversation_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid conversation ID format")

    conv = await conversation_collection.find_one({"_id": obj_id})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_id = str(current_user["_id"])
    if user_id not in conv.get("participants", []):
        raise HTTPException(status_code=403, detail="Not a participant")

    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if payload.message_type == "system":
        raise HTTPException(
            status_code=403,
            detail="Users cannot send system messages"
        )

    now = datetime.utcnow()
    msg_doc = {
        "conversation_id": conversation_id,
        "sender_id": user_id,
        "message": payload.message.strip(),
        "message_type": payload.message_type,
        "property_id": payload.property_id,
        "offer_id": payload.offer_id,
        "created_at": now,
    }
    result = await message_collection.insert_one(msg_doc)

    await conversation_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "last_message": payload.message.strip()[:100],
            "updated_at": now
        }}
    )

    other_participants = [p for p in conv.get("participants", []) if p != user_id]
    for pid in other_participants:
        await create_notification(
            user_id=pid,
            title=f"New message from {current_user.get('name', 'User')}",
            body=payload.message.strip()[:100],
            notif_type="new_message",
            reference_id=conversation_id,
            reference_type="conversation",
        )

    return {
        "id": str(result.inserted_id),
        "message": payload.message.strip()
    }


@router.post("/{conversation_id}/attachments")
async def send_attachment(
    conversation_id: str,
    file: UploadFile = File(...),
    message_type: str = Form("attachment"),
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(conversation_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid conversation ID format")

    conv = await conversation_collection.find_one({"_id": obj_id})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_id = str(current_user["_id"])
    if user_id not in conv.get("participants", []):
        raise HTTPException(status_code=403, detail="Not a participant")

    contents = await file.read()
    if len(contents) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    ext = os.path.splitext(file.filename)[1] or ".bin"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    conv_folder = os.path.join(ATTACHMENT_DIR, conversation_id)
    os.makedirs(conv_folder, exist_ok=True)

    file_path = os.path.join(conv_folder, unique_name)
    with open(file_path, "wb") as f:
        f.write(contents)

    attachment_url = f"/uploads/attachments/{conversation_id}/{unique_name}"

    now = datetime.utcnow()
    msg_doc = {
        "conversation_id": conversation_id,
        "sender_id": user_id,
        "message": file.filename,
        "message_type": message_type,
        "attachment_url": attachment_url,
        "created_at": now,
    }
    result = await message_collection.insert_one(msg_doc)

    await conversation_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "last_message": f"[{message_type}] {file.filename}",
            "updated_at": now
        }}
    )

    return {
        "message_id": str(result.inserted_id),
        "attachment_url": attachment_url
    }