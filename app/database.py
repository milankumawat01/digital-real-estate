import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME", "real_estate")

if not MONGODB_URL:
    raise ValueError("MONGODB_URL is not set in .env")

client = AsyncIOMotorClient(MONGODB_URL)
database = client[DATABASE_NAME]


property_collection = database.get_collection("properties")
user_collection = database.get_collection("users")
saved_search_collection = database.get_collection("saved_searches")
site_visit_collection = database.get_collection("site_visits")
project_collection = database.get_collection("projects")
tower_collection = database.get_collection("towers")
floor_collection = database.get_collection("floors")
unit_collection = database.get_collection("units")

print(f"MongoDB connected successfully! Database: {DATABASE_NAME}")
offer_collection = database.get_collection("offers")
document_collection = database.get_collection("documents")
verification_collection = database.get_collection("verifications")
booking_collection = database.get_collection("bookings")
payment_collection = database.get_collection("payments")
conversation_collection = database.get_collection("conversations")
message_collection = database.get_collection("messages")
notification_collection = database.get_collection("notifications")
review_collection = database.get_collection("reviews")