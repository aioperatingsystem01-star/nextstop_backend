from typing import List, Optional
from pydantic import BaseModel, Field


class UserSearchResult(BaseModel):
    """Public user search result representation. Never exposes private data, passwords, or emails."""
    id: str = Field(..., description="Unique user identifier (UUID)")
    username: str = Field(..., description="Unique user handle")
    full_name: str = Field(..., description="User's full name")
    profile_picture: Optional[str] = Field(default="", description="Profile image URL")
    avatar_url: Optional[str] = Field(default="", description="Avatar image URL (alias)")
    bio: Optional[str] = Field(default="", description="User bio or description")
    is_verified: bool = Field(default=False, description="Verification badge status")
    followers_count: int = Field(default=0, description="Count of followers")
    following_count: int = Field(default=0, description="Count of following")


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
