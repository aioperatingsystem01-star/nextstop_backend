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
    profile_picture: Optional[str] = Field(default="", description="Profile image URL")
    avatar_url: Optional[str] = Field(default="", description="Avatar image URL")
    bio: Optional[str] = Field(default="", description="User bio or description")
    website: Optional[str] = Field(default="", description="User website or portfolio link")
    is_verified: bool = Field(default=False, description="Verification badge status")
    followers_count: int = Field(default=0, description="Follower count")
    following_count: int = Field(default=0, description="Following count")
    posts_count: int = Field(default=0, description="Total published posts count")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of user account creation",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of last update",
    )
