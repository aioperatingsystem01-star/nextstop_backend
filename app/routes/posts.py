# ==============================================================================
# NEXT STOP BACKEND - POSTS & MEDIA ROUTES
# Updated: 2026-11-09 | Route ordering fix (/saved/me before /{post_id}), get_post
# ==============================================================================
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from app.core.dependencies import get_current_user
from app.schemas.auth import UserProfileResponse
from app.schemas.post import (
    CommentCreateRequest,
    CommentResponse,
    LikeToggleResponse,
    PostCreateRequest,
    PostResponse,
    PostsListResponse,
    SaveToggleResponse,
)
from app.services.post_service import post_service
from app.services.storage_service import storage_service

router = APIRouter(prefix="/posts", tags=["Posts"])


@router.post(
    "/upload-media",
    status_code=status.HTTP_200_OK,
    summary="Upload media to Supabase Storage",
)
async def upload_post_media(
    file: UploadFile = File(...),
    current_user: UserProfileResponse = Depends(get_current_user),
):
    """Uploads photo or video directly to Supabase bucket nextstop-media."""
    media_url, media_type = await storage_service.upload_post_media(current_user.id, file)
    return {"media_url": media_url, "media_type": media_type}


@router.post(
    "",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publish a new photo/video post",
)
async def create_post(
    data: PostCreateRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> PostResponse:
    """Creates a new post and publishes to MongoDB Atlas."""
    return await post_service.create_post(
        user_id=current_user.id,
        caption=data.caption,
        hashtags=data.hashtags,
        media_url=data.media_url,
        media_type=data.media_type,
    )


@router.get(
    "/explore",
    response_model=PostsListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get public discovery explore feed",
)
async def get_explore_feed(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: UserProfileResponse = Depends(get_current_user),
) -> PostsListResponse:
    """Returns explore feed with public posts discoverable across the platform."""
    return await post_service.get_explore_feed(
        current_user_id=current_user.id,
        page=page,
        limit=limit,
    )


@router.get(
    "/feed",
    response_model=PostsListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get following feed",
)
async def get_following_feed(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: UserProfileResponse = Depends(get_current_user),
) -> PostsListResponse:
    """Returns posts from followed users and the creator's own posts."""
    return await post_service.get_following_feed(
        current_user_id=current_user.id,
        page=page,
        limit=limit,
    )


@router.get(
    "/user/{user_id}",
    response_model=PostsListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user posts for profile",
)
async def get_user_posts(
    user_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=60),
    current_user: UserProfileResponse = Depends(get_current_user),
) -> PostsListResponse:
    """Returns posts created by target user for Profile Content Tabs."""
    return await post_service.get_user_posts(
        target_user_id=user_id,
        current_user_id=current_user.id,
        page=page,
        limit=limit,
    )


# IMPORTANT: /saved/me MUST be declared BEFORE /{post_id} to prevent FastAPI
# from matching the literal string "saved" as a post_id path parameter.
@router.get(
    "/saved/me",
    response_model=PostsListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authenticated user's saved posts",
)
async def get_my_saved_posts(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=60),
    current_user: UserProfileResponse = Depends(get_current_user),
) -> PostsListResponse:
    """Returns posts saved by the user for the Profile Saved tab."""
    return await post_service.get_saved_posts(current_user.id, page=page, limit=limit)


@router.get(
    "/{post_id}",
    response_model=PostResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single post by ID",
)
async def get_post(
    post_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> PostResponse:
    """Returns full post detail with like/save status for authenticated user."""
    return await post_service.get_post_by_id(post_id, current_user_id=current_user.id)


@router.delete(
    "/{post_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete post",
)
async def delete_post(
    post_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    """Deletes own post and decrements posts_count atomically."""
    await post_service.delete_post(post_id, current_user.id)
    return {"success": True, "message": "Post deleted successfully."}


@router.post(
    "/{post_id}/like",
    response_model=LikeToggleResponse,
    status_code=status.HTTP_200_OK,
    summary="Like or unlike post",
)
async def toggle_like(
    post_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> LikeToggleResponse:
    """Toggles like state and updates counts."""
    return await post_service.toggle_like(post_id, current_user.id)


@router.post(
    "/{post_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add comment to post",
)
async def add_comment(
    post_id: str,
    data: CommentCreateRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> CommentResponse:
    """Adds comment and sends notification to creator."""
    return await post_service.add_comment(post_id, current_user.id, data.text)


@router.get(
    "/{post_id}/comments",
    response_model=List[CommentResponse],
    status_code=status.HTTP_200_OK,
    summary="Get comments for a post",
)
async def get_comments(
    post_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> List[CommentResponse]:
    """Returns comment thread for post."""
    return await post_service.get_comments(post_id)


@router.post(
    "/{post_id}/save",
    response_model=SaveToggleResponse,
    status_code=status.HTTP_200_OK,
    summary="Save or unsave post",
)
async def toggle_save(
    post_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> SaveToggleResponse:
    """Toggles saved state for post."""
    return await post_service.toggle_save(post_id, current_user.id)
