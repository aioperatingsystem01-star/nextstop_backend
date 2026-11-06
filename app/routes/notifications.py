from fastapi import APIRouter, Depends, Query, status
from app.core.dependencies import get_current_user
from app.schemas.auth import UserProfileResponse
from app.schemas.notification import (
    NotificationListResponse,
    UnreadCountResponse,
)
from app.services.notification_service import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user notifications",
)
async def get_notifications(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=50),
    current_user: UserProfileResponse = Depends(get_current_user),
) -> NotificationListResponse:
    """Returns list of notifications with unread counter."""
    return await notification_service.get_user_notifications(
        recipient_id=current_user.id,
        page=page,
        limit=limit,
    )


@router.patch(
    "/{notification_id}/read",
    status_code=status.HTTP_200_OK,
    summary="Mark notification as read",
)
async def mark_notification_read(
    notification_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    """Marks single notification as read."""
    success = await notification_service.mark_as_read(notification_id, current_user.id)
    return {"success": success}


@router.patch(
    "/read-all",
    status_code=status.HTTP_200_OK,
    summary="Mark all notifications as read",
)
async def mark_all_notifications_read(
    current_user: UserProfileResponse = Depends(get_current_user),
):
    """Marks all user notifications as read."""
    count = await notification_service.mark_all_read(current_user.id)
    return {"success": True, "marked_count": count}


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    status_code=status.HTTP_200_OK,
    summary="Get count of unread notifications",
)
async def get_unread_count(
    current_user: UserProfileResponse = Depends(get_current_user),
) -> UnreadCountResponse:
    """Returns unread notification badge count."""
    count = await notification_service.get_unread_count(current_user.id)
    return UnreadCountResponse(unread_count=count)
