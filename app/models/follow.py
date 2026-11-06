from datetime import datetime, timezone
from pydantic import BaseModel, Field


class FollowModel(BaseModel):
    """Represents a follow relationship between two registered users in MongoDB."""
    id: str = Field(..., description="Unique UUID identifier for the follow relation")
    follower_user_id: str = Field(..., description="ID of the user who followed")
    following_user_id: str = Field(..., description="ID of the user being followed")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of follow action",
    )
