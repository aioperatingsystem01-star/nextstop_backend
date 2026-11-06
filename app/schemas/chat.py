from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.user import UserSearchResult


class SendMessageRequest(BaseModel):
    """Schema for sending a direct message."""
    recipient_id: Optional[str] = Field(default=None, description="Recipient user ID when initiating new chat")
    text: str = Field(default="", max_length=5000)
    media_url: Optional[str] = Field(default="", description="Supabase storage URL for attachment")
    message_type: str = Field(default="text", description="text, image, video")


class MessageResponse(BaseModel):
    """Message item returned in conversation history."""
    id: str
    conversation_id: str
    sender_id: str
    recipient_id: str
    text: str = ""
    media_url: Optional[str] = ""
    message_type: str = "text"
    is_read: bool = False
    read_at: Optional[datetime] = None
    created_at: datetime


# Alias for distinct naming
ChatMessageResponse = MessageResponse


class ConversationResponse(BaseModel):
    """Conversation summary item for the inbox list."""
    id: str
    participant: UserSearchResult
    last_message: str = ""
    last_message_at: Optional[datetime] = None
    unread_count: int = 0
    is_online: bool = False


class ConversationsListResponse(BaseModel):
    """List of user conversations with total unread count."""
    success: bool = True
    conversations: List[ConversationResponse] = Field(default_factory=list)
    total_unread: int = 0


class MessagesListResponse(BaseModel):
    """Message history for a conversation."""
    success: bool = True
    conversation_id: str
    messages: List[MessageResponse] = Field(default_factory=list)
    total: int = 0


class MarkReadResponse(BaseModel):
    """Result of marking messages read."""
    success: bool = True
    conversation_id: str
    marked_count: int = 0
