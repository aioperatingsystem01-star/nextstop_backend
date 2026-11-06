from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.user import UserSearchResult


class NotificationResponse(BaseModel):
    """Notification item details."""
    id: str
    type: str  # new_follower, follow_back, post_like, post_comment, new_message
    title: str
    body: str
    actor: Optional[UserSearchResult] = None
    entity_id: Optional[str] = ""
    is_read: bool = False
    created_at: datetime


class NotificationListResponse(BaseModel):
    """List of notifications with unread counter."""
    success: bool = True
    notifications: List[NotificationResponse] = Field(default_factory=list)
    unread_count: int = 0


class UnreadCountResponse(BaseModel):
    """Count of unread notifications."""
    unread_count: int = 0
