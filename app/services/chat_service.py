from datetime import datetime, timezone
from typing import List, Optional
import uuid
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorCollection

from app.database.mongodb import (
    get_conversation_collection,
    get_message_collection,
    get_user_collection,
)
from app.models.chat import ConversationModel, MessageModel
from app.schemas.chat import (
    ConversationResponse,
    ConversationsListResponse,
    MarkReadResponse,
    MessageResponse,
    MessagesListResponse,
)
from app.schemas.user import UserSearchResult
from app.services.notification_service import notification_service
from app.services.websocket_manager import ws_manager


class ChatService:
    """Manages conversations, real-time message sending, history, and read receipts."""

    def __init__(self, conv_col: Optional[AsyncIOMotorCollection] = None):
        self._conv_col = conv_col

    @property
    def conv_col(self) -> AsyncIOMotorCollection:
        if self._conv_col is not None:
            return self._conv_col
        return get_conversation_collection()

    @property
    def msg_col(self) -> AsyncIOMotorCollection:
        return get_message_collection()

    async def get_or_create_conversation(self, user_a_id: str, user_b_id: str) -> str:
        """Finds existing 1-to-1 conversation or creates a new one."""
        if user_a_id == user_b_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot start conversation with yourself.",
            )

        existing = await self.conv_col.find_one({
            "participant_ids": {"$all": [user_a_id, user_b_id], "$size": 2}
        })
        if existing:
            return existing["id"]

        now = datetime.now(timezone.utc)
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        conv = ConversationModel(
            id=conv_id,
            participant_ids=[user_a_id, user_b_id],
            last_message="",
            last_message_at=now,
            last_sender_id="",
            unread_counts={user_a_id: 0, user_b_id: 0},
            created_at=now,
            updated_at=now,
        )

        await self.conv_col.insert_one(conv.model_dump())
        return conv_id

    async def get_user_conversations(self, user_id: str) -> ConversationsListResponse:
        """Retrieves user's conversations sorted by most recent activity."""
        cursor = self.conv_col.find({"participant_ids": user_id}).sort("updated_at", -1)
        conv_docs = await cursor.to_list(length=100)

        other_user_ids = []
        for c in conv_docs:
            p_ids = c.get("participant_ids", [])
            other = next((uid for uid in p_ids if uid != user_id), None)
            if other:
                other_user_ids.append(other)

        user_col = get_user_collection()
        other_user_docs = await user_col.find(
            {"id": {"$in": other_user_ids}},
            {"_id": 0, "id": 1, "username": 1, "full_name": 1, "profile_picture": 1, "avatar_url": 1, "is_verified": 1},
        ).to_list(length=len(other_user_ids))
        user_map = {}
        for u in other_user_docs:
            pic = u.get("profile_picture") or u.get("avatar_url") or ""
            user_map[u["id"]] = UserSearchResult(
                id=u["id"],
                username=u.get("username", ""),
                full_name=u.get("full_name", ""),
                profile_picture=pic,
                avatar_url=pic,
                is_verified=bool(u.get("is_verified", False)),
            )

        total_unread = 0
        conversations: List[ConversationResponse] = []
        for c in conv_docs:
            p_ids = c.get("participant_ids", [])
            other_id = next((uid for uid in p_ids if uid != user_id), None)
            participant = user_map.get(other_id)
            if not participant:
                continue

            unread = int(c.get("unread_counts", {}).get(user_id, 0))
            total_unread += unread
            is_online = ws_manager.is_user_online(other_id)

            conversations.append(
                ConversationResponse(
                    id=c["id"],
                    participant=participant,
                    last_message=c.get("last_message", ""),
                    last_message_at=c.get("last_message_at"),
                    unread_count=unread,
                    is_online=is_online,
                )
            )

        return ConversationsListResponse(
            success=True,
            conversations=conversations,
            total_unread=total_unread,
        )

    async def get_messages(
        self,
        conversation_id: str,
        user_id: str,
        limit: int = 50,
    ) -> MessagesListResponse:
        """Retrieves messages for a conversation ensuring user is a participant."""
        conv = await self.conv_col.find_one({"id": conversation_id})
        if not conv or user_id not in conv.get("participant_ids", []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this conversation.",
            )

        cursor = self.msg_col.find({"conversation_id": conversation_id}).sort("created_at", 1).limit(limit)
        docs = await cursor.to_list(length=limit)

        messages = [
            MessageResponse(
                id=d["id"],
                conversation_id=d["conversation_id"],
                sender_id=d["sender_id"],
                recipient_id=d["recipient_id"],
                text=d.get("text", ""),
                media_url=d.get("media_url", ""),
                message_type=d.get("message_type", "text"),
                is_read=bool(d.get("is_read", False)),
                read_at=d.get("read_at"),
                created_at=d.get("created_at", datetime.now(timezone.utc)),
            )
            for d in docs
        ]

        return MessagesListResponse(
            success=True,
            conversation_id=conversation_id,
            messages=messages,
            total=len(messages),
        )

    async def send_message(
        self,
        conversation_id: str,
        sender_id: str,
        text: str,
        media_url: Optional[str] = "",
        message_type: str = "text",
        recipient_id: Optional[str] = None,
    ) -> MessageResponse:
        """Saves message, updates conversation summary, and broadcasts over WebSocket."""
        conv = await self.conv_col.find_one({"id": conversation_id})
        if not conv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

        if sender_id not in conv.get("participant_ids", []):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot send message to this conversation.")

        if not recipient_id:
            recipient_id = next((uid for uid in conv["participant_ids"] if uid != sender_id), None)
            if not recipient_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No recipient found.")

        now = datetime.now(timezone.utc)
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        msg = MessageModel(
            id=msg_id,
            conversation_id=conversation_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            text=text.strip(),
            media_url=media_url or "",
            message_type=message_type,
            is_read=False,
            created_at=now,
        )

        await self.msg_col.insert_one(msg.model_dump())

        # Update conversation
        preview = text.strip() if text else ("[Attachment]" if media_url else "")
        unread_field = f"unread_counts.{recipient_id}"
        await self.conv_col.update_one(
            {"id": conversation_id},
            {
                "$set": {
                    "last_message": preview,
                    "last_message_at": now,
                    "last_sender_id": sender_id,
                    "updated_at": now,
                },
                "$inc": {unread_field: 1},
            },
        )

        msg_resp = MessageResponse(
            id=msg_id,
            conversation_id=conversation_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            text=msg.text,
            media_url=msg.media_url,
            message_type=msg.message_type,
            is_read=False,
            created_at=now,
        )

        # Real-time WebSocket delivery to recipient
        payload = {
            "event": "new_message",
            "message": msg_resp.model_dump(mode="json"),
        }
        await ws_manager.send_personal_message(recipient_id, payload)

        # Also send echo to sender's other devices
        await ws_manager.send_personal_message(sender_id, payload)

        # Notify recipient
        user_col = get_user_collection()
        sender = await user_col.find_one({"id": sender_id})
        sender_name = sender.get("full_name") or sender.get("username") if sender else "Someone"

        await notification_service.create_notification(
            recipient_id=recipient_id,
            actor_id=sender_id,
            type="new_message",
            title="New Message",
            body=f"{sender_name}: {preview[:50]}",
            entity_id=conversation_id,
        )

        return msg_resp

    async def mark_conversation_as_read(self, conversation_id: str, user_id: str) -> MarkReadResponse:
        """Marks all unread messages addressed to user_id as read."""
        now = datetime.now(timezone.utc)
        res = await self.msg_col.update_many(
            {"conversation_id": conversation_id, "recipient_id": user_id, "is_read": False},
            {"$set": {"is_read": True, "read_at": now}},
        )

        # Reset unread counter for user_id in conversation
        await self.conv_col.update_one(
            {"id": conversation_id},
            {"$set": {f"unread_counts.{user_id}": 0}},
        )

        conv = await self.conv_col.find_one({"id": conversation_id})
        if conv:
            other_id = next((uid for uid in conv.get("participant_ids", []) if uid != user_id), None)
            if other_id:
                # Send real-time read receipt to other participant
                await ws_manager.send_personal_message(
                    other_id,
                    {
                        "event": "read_receipt",
                        "conversation_id": conversation_id,
                        "reader_id": user_id,
                        "read_at": now.isoformat(),
                    },
                )

        return MarkReadResponse(
            success=True,
            conversation_id=conversation_id,
            marked_count=res.modified_count,
        )


chat_service = ChatService()
