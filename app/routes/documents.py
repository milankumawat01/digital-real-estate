from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from bson import ObjectId
from datetime import datetime
import uuid
import os

from app.routes.auth import get_current_user, require_seller
from app.schemas.document import DocumentRequestCreate, DocumentStatusUpdate
from app.database import document_collection, property_collection

router = APIRouter()


DOCUMENT_DIR = "uploads/documents"
os.makedirs(DOCUMENT_DIR, exist_ok=True)


ALLOWED_DOC_TYPES = [
    "sale_deed", "ownership_proof", "noc", "tax_receipt",
    "building_plan", "rera_certificate", "encumbrance_certificate",
    "other"
]

MAX_DOC_SIZE = 10 * 1024 * 1024
ALLOWED_MIME = ["application/pdf", "image/jpeg", "image/png", "image/jpg"]


def document_serializer(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "property_id": doc.get("property_id"),
        "seller_id": doc.get("seller_id"),
        "document_type": doc.get("document_type"),
        "file_url": doc.get("file_url"),
        "filename": doc.get("filename"),
        "status": doc.get("status", "pending"),
        "reviewer_note": doc.get("reviewer_note"),
        "requests": doc.get("requests", []),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


@router.post("/properties/{property_id}/documents")
async def upload_property_document(
    property_id: str,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    current_user: dict = Depends(require_seller)
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
            detail="You can only upload documents for your own properties"
        )

    if document_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type. Allowed: {ALLOWED_DOC_TYPES}"
        )

    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {ALLOWED_MIME}"
        )

    contents = await file.read()
    if len(contents) > MAX_DOC_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max {MAX_DOC_SIZE // (1024 * 1024)} MB"
        )

    ext = os.path.splitext(file.filename)[1] or ".bin"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    property_doc_folder = os.path.join(DOCUMENT_DIR, property_id)
    os.makedirs(property_doc_folder, exist_ok=True)

    file_path = os.path.join(property_doc_folder, unique_name)
    with open(file_path, "wb") as f:
        f.write(contents)

    file_url = f"/uploads/documents/{property_id}/{unique_name}"

    now = datetime.utcnow()
    doc = {
        "property_id": property_id,
        "seller_id": str(current_user["_id"]),
        "document_type": document_type,
        "file_url": file_url,
        "filename": file.filename,
        "status": "pending",
        "requests": [],
        "created_at": now,
        "updated_at": now,
    }

    result = await document_collection.insert_one(doc)

    return {
        "document_id": str(result.inserted_id),
        "status": "pending"
    }


@router.get("/properties/{property_id}/documents")
async def list_property_documents(
    property_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        ObjectId(property_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid property ID format")

    role = current_user.get("role", "buyer")
    query = {"property_id": property_id}

    if role not in ["admin", "seller", "builder", "agent"]:
        query["status"] = "approved"

    results = []
    async for doc in document_collection.find(query).sort("created_at", -1):
        results.append(document_serializer(doc))

    return {
        "count": len(results),
        "results": results
    }


@router.get("/documents/{document_id}")
async def get_document_status(
    document_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(document_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid document ID format")

    doc = await document_collection.find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    user_id = str(current_user["_id"])
    role = current_user.get("role")
    is_owner = doc.get("seller_id") == user_id
    is_admin = role == "admin"

    if not (is_owner or is_admin):
        if doc.get("status") != "approved":
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to view this document"
            )

    return {
        "id": str(doc["_id"]),
        "status": doc.get("status")
    }


@router.post("/documents/{document_id}/request")
async def request_document(
    document_id: str,
    request_data: DocumentRequestCreate,
    current_user: dict = Depends(get_current_user)
):
    try:
        obj_id = ObjectId(document_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid document ID format")

    doc = await document_collection.find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    user_id = str(current_user["_id"])

    if doc.get("seller_id") == user_id:
        raise HTTPException(
            status_code=400,
            detail="You cannot request your own document"
        )

    now = datetime.utcnow()
    request_entry = {
        "buyer_id": user_id,
        "message": request_data.message,
        "at": now.isoformat()
    }

    await document_collection.update_one(
        {"_id": obj_id},
        {
            "$push": {"requests": request_entry},
            "$set": {"updated_at": now}
        }
    )

    return {"message": "Document request sent"}


@router.patch("/documents/{doc_id}")
async def review_document(
    doc_id: str,
    payload: DocumentStatusUpdate,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admin can review documents")

    try:
        obj_id = ObjectId(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid document ID format")

    doc = await document_collection.find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await document_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": payload.status,
            "reviewer_note": payload.reason,
            "reviewed_at": datetime.utcnow(),
            "reviewed_by": str(current_user["_id"]),
        }}
    )

    return {"id": doc_id, "status": payload.status}