from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class UserModel(BaseModel):
    """User representation stored in MongoDB."""
    id: str = Field(..., description="Unique UUID identifier for the user")
    full_name: str = Field(..., description="User's full name")
    username: str = Field(..., description="Unique user handle (alphanumeric, lowercase)")
    email: str = Field(..., description="Unique email address (lowercase)")
    mobile_number: str = Field(..., description="User mobile contact number")
    hashed_password: str = Field(..., description="Argon2-hashed password")
    is_active: bool = Field(default=True, description="Account active status")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of user account creation",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of last update",
    )
