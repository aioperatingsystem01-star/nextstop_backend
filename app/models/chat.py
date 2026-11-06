from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ConversationModel(BaseModel):
    """Represents a 1-to-1 or group conversation in MongoDB."""
    id: str = Field(..., description="Unique UUID conversation identifier")
    participant_ids: List[str] = Field(..., description="IDs of participants")
    last_message: Optional[str] = Field(default="", description="Snippet of the latest message")
    last_message_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of the latest message",
    )
    last_sender_id: Optional[str] = Field(default="", description="ID of last sender")
    unread_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Map of user_id to their unread count in this conversation",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Conversation creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Conversation last active timestamp",
    )


class MessageModel(BaseModel):
    """Represents an individual chat message in MongoDB."""
    id: str = Field(..., description="Unique UUID message identifier")
    conversation_id: str = Field(..., description="Parent conversation identifier")
    sender_id: str = Field(..., description="Sender user ID")
    recipient_id: str = Field(..., description="Recipient user ID")
    text: str = Field(default="", description="Text message content")
    message_type: str = Field(default="text", description="text, image, video, audio")
    media_url: Optional[str] = Field(default="", description="Supabase storage URL for attachment")
    is_read: bool = Field(default=False, description="Whether message has been seen by recipient")
    read_at: Optional[datetime] = Field(default=None, description="Timestamp when read")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Message send timestamp",
    )
