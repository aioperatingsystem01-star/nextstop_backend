from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from app.core.dependencies import get_current_user
from app.schemas.auth import UserProfileResponse
from app.schemas.safety import BlockResponse, ReportRequest, ReportResponse
from app.schemas.user import (
    FollowActionResponse,
    FollowersListResponse,
    UserRelationshipResponse,
    UserSearchResponse,
    UserSearchResult,
    UserUpdateProfileRequest,
)
from app.services.follow_service import follow_service
from app.services.storage_service import storage_service
from app.services.user_service import user_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authenticated user profile",
)
async def get_me(current_user: UserProfileResponse = Depends(get_current_user)) -> UserProfileResponse:
    """Returns current user's profile information."""
    return current_user


@router.put(
    "/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update authenticated user profile",
)
async def update_my_profile(
    data: UserUpdateProfileRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> UserProfileResponse:
    """Updates profile bio, website, full_name, or unique username."""
    return await user_service.update_profile(current_user.id, data)


@router.post(
    "/me/avatar",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload profile picture to Supabase",
)
async def upload_my_avatar(
    file: UploadFile = File(...),
    current_user: UserProfileResponse = Depends(get_current_user),
) -> UserProfileResponse:
    """Uploads avatar image to Supabase Storage and saves URL in MongoDB."""
    avatar_url = await storage_service.upload_avatar(current_user.id, file)
    return await user_service.update_avatar(current_user.id, avatar_url)


@router.get(
    "/search",
    response_model=UserSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search registered users in MongoDB",
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
    summary="Get user public profile with follow relationship",
)
async def get_user_profile_by_id(
    user_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> UserSearchResult:
    """Retrieves public user profile for the given user ID with follow status."""
    user = await user_service.get_user_by_id(user_id, current_user_id=current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user


@router.get(
    "/{user_id}/relationship",
    response_model=UserRelationshipResponse,
    status_code=status.HTTP_200_OK,
    summary="Check follow relationship",
)
async def get_relationship(
    user_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> UserRelationshipResponse:
    """Returns is_following, is_followed_by, and follow_status."""
    return await follow_service.get_relationship(current_user.id, user_id)


@router.post(
    "/{user_id}/follow",
    response_model=FollowActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Follow a user",
)
async def follow_user(
    user_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> FollowActionResponse:
    """Follows another user, updates counts atomically, and dispatches notification."""
    return await follow_service.follow_user(current_user.id, user_id)


@router.delete(
    "/{user_id}/follow",
    response_model=FollowActionResponse,
    status_code=status.HTTP_200_OK,
    summary="Unfollow a user",
)
async def unfollow_user(
    user_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> FollowActionResponse:
    """Unfollows a user and updates counts atomically."""
    return await follow_service.unfollow_user(current_user.id, user_id)


@router.get(
    "/{user_id}/followers",
    response_model=FollowersListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user followers list",
)
async def get_followers(
    user_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> FollowersListResponse:
    """Returns list of users following the target account."""
    return await follow_service.get_followers(user_id, current_user_id=current_user.id)


@router.get(
    "/{user_id}/following",
    response_model=FollowersListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user following list",
)
async def get_following(
    user_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> FollowersListResponse:
    """Returns list of users target account is following."""
    return await follow_service.get_following(user_id, current_user_id=current_user.id)


@router.post(
    "/{user_id}/block",
    response_model=BlockResponse,
    status_code=status.HTTP_200_OK,
    summary="Block a user",
)
async def block_user(
    user_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> BlockResponse:
    """Blocks a user and removes existing follow connections."""
    return await user_service.block_user(current_user.id, user_id)


@router.delete(
    "/{user_id}/block",
    response_model=BlockResponse,
    status_code=status.HTTP_200_OK,
    summary="Unblock a user",
)
async def unblock_user(
    user_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> BlockResponse:
    """Unblocks a user."""
    return await user_service.unblock_user(current_user.id, user_id)


@router.post(
    "/report",
    response_model=ReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Report inappropriate user or content",
)
async def report_target(
    data: ReportRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> ReportResponse:
    """Registers safety or content violation report."""
    return await user_service.create_report(
        reporter_id=current_user.id,
        target_id=data.target_id,
        target_type=data.target_type,
        reason=data.reason,
    )
