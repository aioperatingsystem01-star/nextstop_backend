from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class NotificationModel(BaseModel):
    """Represents a social notification stored in MongoDB."""
    id: str = Field(..., description="Unique UUID notification identifier")
    recipient_id: str = Field(..., description="Target user receiving notification")
    actor_id: str = Field(..., description="User performing the action")
    type: str = Field(
        ...,
        description="Type: new_follower, follow_back, post_like, post_comment, new_message, message_request",
    )
    title: str = Field(..., description="Notification title")
    body: str = Field(..., description="Notification body preview")
    entity_id: Optional[str] = Field(default="", description="Target post_id, conversation_id, etc.")
    is_read: bool = Field(default=False, description="Whether notification was opened")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Notification creation timestamp",
    )
