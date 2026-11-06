from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class PostCreateRequest(BaseModel):
    """Schema for publishing a new post."""
    caption: str = Field(default="", max_length=2200)
    hashtags: List[str] = Field(default_factory=list)
    media_url: str = Field(..., description="Supabase storage URL for media")
    media_type: str = Field(default="image", description="image or video")


class PostResponse(BaseModel):
    """Complete post representation returned to Flutter."""
    id: str
    user_id: str
    username: str
    full_name: str
    user_avatar: Optional[str] = ""
    caption: str = ""
    hashtags: List[str] = Field(default_factory=list)
    media_urls: List[str] = Field(default_factory=list)
    media_type: str = "image"
    likes_count: int = 0
    comments_count: int = 0
    is_liked: bool = False
    is_saved: bool = False
    created_at: datetime


class PostsListResponse(BaseModel):
    """List of posts with pagination."""
    success: bool = True
    posts: List[PostResponse] = Field(default_factory=list)
    total: int = 0
    has_more: bool = False


class CommentCreateRequest(BaseModel):
    """Schema for adding a comment to a post."""
    text: str = Field(..., min_length=1, max_length=1000)


class CommentResponse(BaseModel):
    """Comment details with author profile."""
    id: str
    post_id: str
    user_id: str
    username: str
    full_name: str
    user_avatar: Optional[str] = ""
    text: str
    created_at: datetime


class LikeToggleResponse(BaseModel):
    """Result of like/unlike action."""
    success: bool = True
    post_id: str
    is_liked: bool
    likes_count: int


class SaveToggleResponse(BaseModel):
    """Result of saving/unsaving post."""
    success: bool = True
    post_id: str
    is_saved: bool
