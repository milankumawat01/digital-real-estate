from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routes import (
    auth,
    properties,
    users,
    saved_searches,
    site_visits,
    offers,
    documents,
    verifications,
    bookings,
    payments,
    conversations,
    notifications,
)
from app.routes import (
    auth, properties, users, saved_searches, site_visits, offers,
    documents, verifications, bookings, payments, conversations,
    notifications, reviews
)
from app.routes import (
    auth, properties, users, saved_searches, site_visits, offers,
    documents, verifications, bookings, payments, conversations,
    notifications, reviews, ai
)
from app.routes import (
    auth, properties, users, saved_searches, site_visits, offers,
    documents, verifications, bookings, payments, conversations,
    notifications, reviews, ai, seller
)
from app.routes import (
    auth, properties, users, saved_searches, site_visits, offers,
    documents, verifications, bookings, payments, conversations,
    notifications, reviews, ai, seller, projects
)
from app.routes import (
    auth, properties, users, saved_searches, site_visits, offers,
    documents, verifications, bookings, payments, conversations,
    notifications, reviews, ai, seller, projects, agent
)

app = FastAPI(
    title="Real Estate Platform API",
    description="Digital Real Estate Buying Platform",
    version="1.0.0",
)

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
app.include_router(
    reviews.router,
    prefix="/api/properties",
    tags=["Reviews"]
)
app.include_router(
    ai.router,
    prefix="/api/ai",
    tags=["AI"]
)
app.include_router(
    seller.router,
    prefix="/api/seller",
    tags=["Seller"]
)
app.include_router(
    projects.router,
    prefix="/api/projects",
    tags=["Projects (Builder)"]
)
app.include_router(
    agent.router,
    prefix="/api/agent",
    tags=["Agent"]
)


@app.get("/")
def home():
    return {
        "success": True,
        "message": "Real Estate Platform API is running",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
