from fastapi import APIRouter, Depends, status
from app.core.dependencies import get_current_user
from app.schemas.auth import UserProfileResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authenticated user profile",
    description="Returns the profile of the user currently authenticated via Bearer JWT token. Password hashes are never exposed.",
)
async def get_me(current_user: UserProfileResponse = Depends(get_current_user)) -> UserProfileResponse:
    """Returns current user's profile information."""
    return current_user
