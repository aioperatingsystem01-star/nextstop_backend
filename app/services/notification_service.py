# ==============================================================================
# NEXT STOP BACKEND - NOTIFICATION SERVICE
# Updated: 2026-11-09 | 5-minute sliding window deduplication for likes & follows
# ==============================================================================
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import uuid
from motor.motor_asyncio import AsyncIOMotorCollection

from app.database.mongodb import get_notification_collection, get_user_collection
from app.models.notification import NotificationModel
from app.schemas.notification import NotificationResponse, NotificationListResponse
from app.schemas.user import UserSearchResult


class NotificationService:
    """Handles social and messaging notifications."""

    def __init__(self, collection: Optional[AsyncIOMotorCollection] = None):
        self._col = collection

    @property
    def col(self) -> AsyncIOMotorCollection:
        if self._col is not None:
            return self._col
        return get_notification_collection()

    async def create_notification(
        self,
        recipient_id: str,
        actor_id: str,
        type: str,
        title: str,
        body: str,
        entity_id: Optional[str] = "",
    ) -> Optional[NotificationModel]:
        """Creates a new notification if recipient != actor."""
        if recipient_id == actor_id:
            return None

        # Check for a duplicate unread notification within a 5-minute window.
        # This prevents spam (e.g., rapid multiple likes) while still sending
        # new notifications after the user has cleared / had time between actions.
        # For new_message type, we always notify (messages in same conv should alert).
        if type != "new_message":
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
            recent = await self.col.find_one({
                "recipient_id": recipient_id,
                "actor_id": actor_id,
                "type": type,
                "entity_id": entity_id,
                "is_read": False,
                "created_at": {"$gte": cutoff},
            })
            if recent:
                return None

        now = datetime.now(timezone.utc)
        notif = NotificationModel(
            id=f"notif_{uuid.uuid4().hex[:12]}",
            recipient_id=recipient_id,
            actor_id=actor_id,
            type=type,
            title=title,
            body=body,
            entity_id=entity_id or "",
            is_read=False,
            created_at=now,
        )

        await self.col.insert_one(notif.model_dump())
        return notif

    async def get_user_notifications(
        self,
        recipient_id: str,
        page: int = 1,
        limit: int = 30,
    ) -> NotificationListResponse:
        """Fetches notifications with hydrated actor profiles."""
        skip = (page - 1) * limit
        cursor = (
            self.col.find({"recipient_id": recipient_id})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)

        unread_count = await self.col.count_documents({
            "recipient_id": recipient_id,
            "is_read": False,
        })

        # Hydrate actors
        user_col = get_user_collection()
        actor_ids = list({d["actor_id"] for d in docs if d.get("actor_id")})
        actor_map = {}
        if actor_ids:
            actor_docs = await user_col.find(
                {"id": {"$in": actor_ids}},
                {"_id": 0, "id": 1, "username": 1, "full_name": 1, "profile_picture": 1, "avatar_url": 1, "is_verified": 1},
            ).to_list(length=len(actor_ids))
            for a in actor_docs:
                pic = a.get("profile_picture") or a.get("avatar_url") or ""
                actor_map[a["id"]] = UserSearchResult(
                    id=a["id"],
                    username=a.get("username", ""),
                    full_name=a.get("full_name", ""),
                    profile_picture=pic,
                    avatar_url=pic,
                    is_verified=bool(a.get("is_verified", False)),
                )

        results: List[NotificationResponse] = []
        for d in docs:
            actor = actor_map.get(d.get("actor_id"))
            results.append(
                NotificationResponse(
                    id=d["id"],
                    type=d["type"],
                    title=d["title"],
                    body=d["body"],
                    actor=actor,
                    entity_id=d.get("entity_id", ""),
                    is_read=bool(d.get("is_read", False)),
                    created_at=d.get("created_at", datetime.now(timezone.utc)),
                )
            )

        return NotificationListResponse(
            success=True,
            notifications=results,
            unread_count=unread_count,
        )

    async def mark_as_read(self, notification_id: str, recipient_id: str) -> bool:
        """Marks a single notification as read."""
        res = await self.col.update_one(
            {"id": notification_id, "recipient_id": recipient_id},
            {"$set": {"is_read": True}},
        )
        return res.modified_count > 0

    async def mark_all_read(self, recipient_id: str) -> int:
        """Marks all notifications for a user as read."""
        res = await self.col.update_many(
            {"recipient_id": recipient_id, "is_read": False},
            {"$set": {"is_read": True}},
        )
        return res.modified_count

    async def get_unread_count(self, recipient_id: str) -> int:
        """Returns total unread count."""
        return await self.col.count_documents({
            "recipient_id": recipient_id,
            "is_read": False,
        })


notification_service = NotificationService()
