from datetime import datetime, timezone
from pydantic import BaseModel, Field


class BlockModel(BaseModel):
    """Represents a block relationship in MongoDB."""
    id: str = Field(..., description="Unique UUID identifier")
    blocker_id: str = Field(..., description="User who initiated block")
    blocked_id: str = Field(..., description="Blocked user")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Block creation timestamp",
    )


class ReportModel(BaseModel):
    """Represents a safety or abuse report in MongoDB."""
    id: str = Field(..., description="Unique UUID identifier")
    reporter_id: str = Field(..., description="Reporting user")
    target_id: str = Field(..., description="Target user ID or post ID")
    target_type: str = Field(..., description="user or post")
    reason: str = Field(..., min_length=3, max_length=500, description="Reason for reporting")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Report timestamp",
    )
