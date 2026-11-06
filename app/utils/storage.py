import os
import uuid
import magic
from datetime import datetime
from fastapi import UploadFile

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
ALLOWED_VIDEO_TYPES = ["video/mp4", "video/webm", "video/quicktime"]

MAX_FILE_SIZE = 10 * 1024 * 1024

ALLOWED_MAGIC_IMAGE = ["image/jpeg", "image/png", "image/webp"]
ALLOWED_MAGIC_VIDEO = ["video/mp4", "video/webm", "video/quicktime"]


def sniff_file_type(file_bytes: bytes) -> str:
    try:
        mime = magic.from_buffer(file_bytes[:2048], mime=True)
        return mime or "application/octet-stream"
    except Exception:
        return "application/octet-stream"


async def save_media_file(file: UploadFile, property_id: str, media_type: str) -> dict:
    if media_type not in ["image", "video"]:
        raise ValueError("media_type must be 'image' or 'video'")

    if media_type == "image" and file.content_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError(f"Invalid image type: {file.content_type}")

    if media_type == "video" and file.content_type not in ALLOWED_VIDEO_TYPES:
        raise ValueError(f"Invalid video type: {file.content_type}")

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise ValueError(f"File too large. Max {MAX_FILE_SIZE // (1024 * 1024)} MB")

    sniffed_mime = sniff_file_type(contents)

    if media_type == "image" and sniffed_mime not in ALLOWED_MAGIC_IMAGE:
        raise ValueError(f"File content does not match image (detected: {sniffed_mime})")

    if media_type == "video" and sniffed_mime not in ALLOWED_MAGIC_VIDEO:
        raise ValueError(f"File content does not match video (detected: {sniffed_mime})")

    ext = os.path.splitext(file.filename)[1] or ".bin"
    unique_name = f"{uuid.uuid4().hex}{ext}"

    property_folder = os.path.join(UPLOAD_DIR, property_id)
    os.makedirs(property_folder, exist_ok=True)

    file_path = os.path.join(property_folder, unique_name)
    with open(file_path, "wb") as f:
        f.write(contents)

    public_url = f"/uploads/{property_id}/{unique_name}"

    return {
        "media_id": uuid.uuid4().hex,
        "url": public_url,
        "media_type": media_type,
        "filename": file.filename,
        "size": len(contents),
        "detected_mime": sniffed_mime,
        "uploaded_at": datetime.utcnow().isoformat()
    }


def delete_media_file(property_id: str, media_url: str) -> bool:
    try:
        filename = os.path.basename(media_url)
        file_path = os.path.join(UPLOAD_DIR, property_id, filename)

        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception:
        return False