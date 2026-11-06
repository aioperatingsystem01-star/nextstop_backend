import re
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class UserSearchResult(BaseModel):
    """Public user search result representation. Never exposes private data, passwords, or emails."""
    id: str = Field(..., description="Unique user identifier (UUID)")
    username: str = Field(..., description="Unique user handle")
    full_name: str = Field(..., description="User's full name")
    profile_picture: Optional[str] = Field(default="", description="Profile image URL")
    avatar_url: Optional[str] = Field(default="", description="Avatar image URL (alias)")
    bio: Optional[str] = Field(default="", description="User bio or description")
    website: Optional[str] = Field(default="", description="User website/portfolio URL")
    is_verified: bool = Field(default=False, description="Verification badge status")
    followers_count: int = Field(default=0, description="Count of followers")
    following_count: int = Field(default=0, description="Count of following")
    posts_count: int = Field(default=0, description="Count of posts")
    is_following: Optional[bool] = Field(default=False, description="Whether auth user follows this user")
    is_followed_by: Optional[bool] = Field(default=False, description="Whether this user follows auth user")
    follow_status: Optional[str] = Field(default="follow", description="follow, following, follow_back, self")


class PaginationMetadata(BaseModel):
    """Pagination details for search results."""
    page: int = Field(..., description="Current page number")
    limit: int = Field(..., description="Results per page limit")
    total: int = Field(..., description="Total matching documents in collection")
    has_more: bool = Field(..., description="Whether additional pages are available")


class UserSearchResponse(BaseModel):
    """Standardized search response matching Next Stop API conventions."""
    success: bool = Field(default=True, description="Request success indicator")
    users: List[UserSearchResult] = Field(default_factory=list, description="List of matching users")
    pagination: PaginationMetadata = Field(..., description="Pagination metadata")


class UserUpdateProfileRequest(BaseModel):
    """Schema for updating user profile fields."""
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    username: Optional[str] = Field(default=None, min_length=3, max_length=30)
    bio: Optional[str] = Field(default=None, max_length=300)
    website: Optional[str] = Field(default=None, max_length=150)
    profile_picture: Optional[str] = Field(default=None, max_length=1000)
    avatar_url: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip().lower()
        if not re.match(r"^[a-z0-9_.]+$", clean):
            raise ValueError("Username can only contain alphanumeric characters, underscores, and dots")
        if len(clean) < 3:
            raise ValueError("Username must be at least 3 characters long")
        return clean

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip()
        if len(clean) < 2:
            raise ValueError("Full Name must have at least 2 characters")
        return clean


class UserRelationshipResponse(BaseModel):
    """Relationship between authenticated user and another user."""
    target_user_id: str
    is_following: bool
    is_followed_by: bool
    follow_status: str  # "follow", "following", "follow_back", "self"


class FollowActionResponse(BaseModel):
    """Result of follow/unfollow action."""
    success: bool = True
    message: str
    follow_status: str
    target_followers_count: int
    user_following_count: int


class FollowersListResponse(BaseModel):
    """List of followers or following users."""
    success: bool = True
    users: List[UserSearchResult] = Field(default_factory=list)
    total: int = 0
