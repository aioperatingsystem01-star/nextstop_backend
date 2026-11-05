from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.core.dependencies import get_current_user
from app.schemas.auth import UserProfileResponse
from app.schemas.user import UserSearchResponse, UserSearchResult
from app.services.user_service import user_service

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


@router.get(
    "/search",
    response_model=UserSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search registered users in MongoDB",
    description=(
        "Searches registered users by username or full name with case-insensitive partial matching. "
        "Excludes the currently authenticated user and strictly returns only public profile data."
    ),
)
async def search_users(
    q: str = Query(default="", max_length=100, description="Username or full name search query"),
    page: int = Query(default=1, ge=1, description="Page number for pagination"),
    limit: int = Query(default=20, ge=1, le=50, description="Maximum number of users to return"),
    current_user: UserProfileResponse = Depends(get_current_user),
) -> UserSearchResponse:
    """Performs real-time search across MongoDB users collection."""
    return await user_service.search_users(
        query=q,
        current_user_id=current_user.id,
        page=page,
        limit=limit,
    )


@router.get(
    "/{user_id}",
    response_model=UserSearchResult,
    status_code=status.HTTP_200_OK,
    summary="Get user public profile by ID",
    description="Retrieves public profile information for any registered user. Never exposes sensitive information.",
)
async def get_user_profile_by_id(
    user_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> UserSearchResult:
    """Retrieves public user profile for the given user ID."""
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user
