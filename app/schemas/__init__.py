"""Pydantic schemas for authentication, users, posts, chat, and notifications."""

from app.schemas.auth import (
    SignUpRequest,
    LoginRequest,
    UserProfileResponse,
    TokenResponse,
    RefreshTokenRequest,
    MessageResponse,
)
from app.schemas.user import (
    UserSearchResult,
    PaginationMetadata,
    UserSearchResponse,
    UserUpdateProfileRequest,
    UserRelationshipResponse,
    FollowActionResponse,
    FollowersListResponse,
)
from app.schemas.post import (
    PostCreateRequest,
    PostResponse,
    PostsListResponse,
    CommentCreateRequest,
    CommentResponse,
    LikeToggleResponse,
    SaveToggleResponse,
)
from app.schemas.chat import (
    SendMessageRequest,
    MessageResponse as ChatMessageResponse,
    ConversationResponse,
    ConversationsListResponse,
    MessagesListResponse,
    MarkReadResponse,
)
from app.schemas.notification import (
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
)
from app.schemas.safety import (
    BlockResponse,
    ReportRequest,
    ReportResponse,
)

__all__ = [
    "SignUpRequest",
    "LoginRequest",
    "UserProfileResponse",
    "TokenResponse",
    "RefreshTokenRequest",
    "MessageResponse",
    "UserSearchResult",
    "PaginationMetadata",
    "UserSearchResponse",
    "UserUpdateProfileRequest",
    "UserRelationshipResponse",
    "FollowActionResponse",
    "FollowersListResponse",
    "PostCreateRequest",
    "PostResponse",
    "PostsListResponse",
    "CommentCreateRequest",
    "CommentResponse",
    "LikeToggleResponse",
    "SaveToggleResponse",
    "SendMessageRequest",
    "ChatMessageResponse",
    "ConversationResponse",
    "ConversationsListResponse",
    "MessagesListResponse",
    "MarkReadResponse",
    "NotificationResponse",
    "NotificationListResponse",
    "UnreadCountResponse",
    "BlockResponse",
    "ReportRequest",
    "ReportResponse",
]
