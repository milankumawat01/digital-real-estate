import random
from datetime import datetime, timedelta
from app.database import database

otp_collection = database.get_collection("otp_tokens")

OTP_EXPIRY_MINUTES = 5


def generate_otp() -> str:
    return str(random.randint(100000, 999999))


async def create_otp(destination: str, purpose: str) -> str:
    otp = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    await otp_collection.delete_many({
        "destination": destination,
        "purpose": purpose
    })

    await otp_collection.insert_one({
        "destination": destination,
        "otp": otp,
        "purpose": purpose,
        "expires_at": expires_at,
        "verified": False,
        "created_at": datetime.utcnow()
    })

    return otp


async def verify_otp_code(destination: str, otp: str, purpose: str) -> bool:
    record = await otp_collection.find_one({
        "destination": destination,
        "otp": otp,
        "purpose": purpose
    })

    if not record:
        return False

    if record["expires_at"] < datetime.utcnow():
        await otp_collection.delete_one({"_id": record["_id"]})
        return False

    await otp_collection.delete_one({"_id": record["_id"]})

    return True