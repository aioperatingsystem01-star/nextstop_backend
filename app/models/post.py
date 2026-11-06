from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class PostModel(BaseModel):
    """Represents a media post created by a registered user."""
    id: str = Field(..., description="Unique UUID identifier for the post")
    user_id: str = Field(..., description="Owner user ID")
    caption: str = Field(default="", description="Post text caption")
    hashtags: List[str] = Field(default_factory=list, description="Extracted or declared hashtags")
    media_urls: List[str] = Field(default_factory=list, description="Supabase storage URLs of post media")
    media_type: str = Field(default="image", description="Media type: image, video, carousel")
    likes_count: int = Field(default=0, description="Cached count of likes")
    comments_count: int = Field(default=0, description="Cached count of comments")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Post creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Post last modification timestamp",
    )


class LikeModel(BaseModel):
    """Represents a post like by a user."""
    id: str = Field(..., description="Unique UUID for the like")
    user_id: str = Field(..., description="Liker user ID")
    post_id: str = Field(..., description="Target post ID")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when liked",
    )


class CommentModel(BaseModel):
    """Represents a user comment on a post."""
    id: str = Field(..., description="Unique UUID for comment")
    post_id: str = Field(..., description="Target post ID")
    user_id: str = Field(..., description="Commenter user ID")
    text: str = Field(..., min_length=1, max_length=1000, description="Comment text")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Comment timestamp",
    )


class SavedPostModel(BaseModel):
    """Represents a saved/bookmarked post by a user."""
    id: str = Field(..., description="Unique UUID for saved post relation")
    user_id: str = Field(..., description="User ID who saved the post")
    post_id: str = Field(..., description="Target post ID")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when saved",
    )
