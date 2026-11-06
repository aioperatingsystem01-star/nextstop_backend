from pydantic import BaseModel, Field


class BlockResponse(BaseModel):
    """Result of blocking or unblocking an account."""
    success: bool = True
    blocked_user_id: str
    is_blocked: bool
    message: str


class ReportRequest(BaseModel):
    """Schema for reporting safety or violation issues."""
    target_id: str = Field(..., description="Target user ID or post ID")
    target_type: str = Field(default="user", description="user or post")
    reason: str = Field(..., min_length=3, max_length=500)


class ReportResponse(BaseModel):
    """Acknowledgment of report receipt."""
    success: bool = True
    report_id: str
    message: str = "Thank you. Your report has been securely registered."
