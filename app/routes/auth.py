from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from bson import ObjectId
from datetime import datetime, timedelta

from app.utils.rate_limit import limiter
from app.schemas.auth import (
    UserRegister, UserLogin, UserResponse,
    ForgotPasswordRequest, VerifyResetTokenRequest, ResetPasswordRequest,
    SendOTPRequest, VerifyOTPRequest
)
from app.utils.password import hash_password, verify_password, generate_reset_token
from app.utils.jwt import create_access_token, verify_access_token
from app.utils.otp import create_otp, verify_otp_code
from app.database import user_collection

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


@router.post("/register", response_model=UserResponse)
async def register(user: UserRegister):
    existing = await user_collection.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_dict = user.dict()
    user_dict["password"] = hash_password(user.password)
    user_dict["status"] = "active"
    user_dict["is_verified"] = False
    user_dict["created_at"] = datetime.utcnow()

    result = await user_collection.insert_one(user_dict)

    return {
        "id": str(result.inserted_id),
        "name": user.name,
        "email": user.email,
        "role": user.role
    }


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    user = await user_collection.find_one({"email": form_data.username})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.get("status") in ["suspended", "banned"]:
        raise HTTPException(
            status_code=403,
            detail="Your account has been suspended. Contact support."
        )

    token = create_access_token({
        "sub": str(user["_id"]),
        "email": user["email"],
        "role": user["role"]
    })

    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user["_id"]),
            "name": user["name"],
            "email": user["email"],
            "role": user["role"]
        }
    }


async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        user = await user_collection.find_one({"_id": ObjectId(payload["sub"])})
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token subject")

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if user.get("status") in ["suspended", "banned"]:
        raise HTTPException(
            status_code=403,
            detail="Your account has been suspended."
        )

    return user


def require_seller(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["seller", "builder", "agent", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only sellers, builders, agents, or admins can perform this action"
        )
    return current_user


@router.post("/send-otp")
@limiter.limit("5/hour")
async def send_otp(request: Request, payload: SendOTPRequest):
    otp = await create_otp(payload.destination, payload.purpose)

    return {
        "message": "OTP sent",
        "expires_in": 300
    }


@router.post("/verify-otp")
async def verify_otp(payload: VerifyOTPRequest):
    is_valid = await verify_otp_code(
        payload.destination,
        payload.otp,
        payload.purpose
    )

    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    if payload.purpose == "registration":
        user = await user_collection.find_one({
            "$or": [
                {"email": payload.destination},
                {"mobile": payload.destination}
            ]
        })
        if user:
            await user_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"is_verified": True}}
            )

    return {
        "verified": True,
        "message": "OTP verified successfully"
    }


@router.post("/forgot-password")
@limiter.limit("3/hour")
async def forgot_password(request: Request, payload: ForgotPasswordRequest):
    user = await user_collection.find_one({"email": payload.email})

    if not user:
        return {
            "success": True,
            "message": "If this email is registered, a reset link has been sent."
        }

    token = generate_reset_token()
    expires_at = datetime.utcnow() + timedelta(minutes=15)

    await user_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "reset_token": token,
            "reset_token_expires": expires_at
        }}
    )

    return {
        "success": True,
        "message": "If this email is registered, a reset link has been sent."
    }


@router.post("/verify-reset-token")
async def verify_reset_token(payload: VerifyResetTokenRequest):
    user = await user_collection.find_one({"reset_token": payload.token})

    if not user:
        raise HTTPException(status_code=400, detail="Invalid token")

    if user.get("reset_token_expires") and user["reset_token_expires"] < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token has expired")

    return {
        "success": True,
        "message": "Token is valid",
        "email": user["email"]
    }


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    user = await user_collection.find_one({"reset_token": payload.token})

    if not user:
        raise HTTPException(status_code=400, detail="Invalid token")

    if user.get("reset_token_expires") and user["reset_token_expires"] < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token has expired")

    await user_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"password": hash_password(payload.new_password)},
            "$unset": {"reset_token": "", "reset_token_expires": ""}
        }
    )

    return {
        "success": True,
        "message": "Password reset successfully. You can now log in."
}
