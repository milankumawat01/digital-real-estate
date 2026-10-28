from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.utils.rate_limit import limiter
from app.routes import (
    auth, properties, users, saved_searches, site_visits, offers,
    documents, verifications, bookings, payments, conversations,
    notifications, reviews, ai, seller, projects, agent, admin
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database import (
        property_collection,
        user_collection,
        offer_collection,
        floor_collection,
        unit_collection,
    )

    await property_collection.create_index([("location", "2dsphere")])
    await user_collection.create_index("email", unique=True)
    await user_collection.create_index("mobile", unique=True)
    await offer_collection.create_index(
        [("property_id", 1), ("buyer_id", 1)],
        unique=True,
        partialFilterExpression={"status": {"$in": ["pending", "countered", "accepted"]}}
    )
    await floor_collection.create_index(
        [("tower_id", 1), ("floor_number", 1)],
        unique=True
    )
    await unit_collection.create_index(
        [("floor_id", 1), ("unit_number", 1)],
        unique=True
    )

    yield


app = FastAPI(
    title="Real Estate Platform API",
    description="Digital Real Estate Buying Platform",
    version="1.0.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(properties.router, prefix="/api/properties", tags=["Properties"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(saved_searches.router, prefix="/api/saved-searches", tags=["Saved Searches"])
app.include_router(site_visits.router, prefix="/api/site-visits", tags=["Site Visits"])
app.include_router(offers.router, prefix="/api/offers", tags=["Offers"])
app.include_router(documents.router, prefix="/api", tags=["Documents"])
app.include_router(verifications.router, prefix="/api/verifications", tags=["Verifications"])
app.include_router(bookings.router, prefix="/api/bookings", tags=["Bookings"])
app.include_router(payments.router, prefix="/api/payments", tags=["Payments"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["Chat"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(reviews.router, prefix="/api/properties", tags=["Reviews"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
app.include_router(seller.router, prefix="/api/seller", tags=["Seller"])
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(projects.router, prefix="/api", tags=["Builder Hierarchy"])
app.include_router(agent.router, prefix="/api/agent", tags=["Agent"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])


@app.get("/")
def home():
    return {"success": True, "message": "Real Estate Platform API is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}

