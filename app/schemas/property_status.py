from enum import Enum


class PropertyStatus(str, Enum):
    PENDING = "pending"
    UNDER_VERIFICATION = "under_verification"
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    REJECTED = "rejected"