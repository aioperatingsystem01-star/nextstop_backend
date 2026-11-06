import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user
from app.core.security import decode_access_token
from app.schemas.auth import UserProfileResponse
from app.schemas.chat import (
    ChatMessageResponse,
    ConversationsListResponse,
    MarkReadResponse,
    MessagesListResponse,
    SendMessageRequest,
)
from app.services.chat_service import chat_service
from app.services.websocket_manager import ws_manager

logger = logging.getLogger("nextstop.chat_router")

router = APIRouter(tags=["Chat"])


class CreateConversationRequest(BaseModel):
    recipient_id: str = Field(..., description="ID of the user to start a conversation with")


@router.get(
    "/conversations",
    response_model=ConversationsListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user conversations",
)
async def get_conversations(
    current_user: UserProfileResponse = Depends(get_current_user),
) -> ConversationsListResponse:
    """Returns conversation inbox list with last message and unread counts."""
    return await chat_service.get_user_conversations(current_user.id)


@router.post(
    "/conversations",
    status_code=status.HTTP_200_OK,
    summary="Create or get conversation with user",
)
async def get_or_create_conversation(
    data: CreateConversationRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    """Finds or creates a 1-to-1 conversation with recipient."""
    conv_id = await chat_service.get_or_create_conversation(current_user.id, data.recipient_id)
    return {"conversation_id": conv_id}


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessagesListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get messages in conversation",
)
async def get_messages(
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    current_user: UserProfileResponse = Depends(get_current_user),
) -> MessagesListResponse:
    """Retrieves conversation message history."""
    return await chat_service.get_messages(conversation_id, current_user.id, limit=limit)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send message in conversation",
)
async def send_message(
    conversation_id: str,
    data: SendMessageRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> ChatMessageResponse:
    """Sends a new message and delivers it in real time."""
    return await chat_service.send_message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        text=data.text,
        media_url=data.media_url,
        message_type=data.message_type,
        recipient_id=data.recipient_id,
    )


@router.patch(
    "/conversations/{conversation_id}/read",
    response_model=MarkReadResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark conversation messages as read",
)
async def mark_read(
    conversation_id: str,
    current_user: UserProfileResponse = Depends(get_current_user),
) -> MarkReadResponse:
    """Marks unread messages as read and notifies sender via real-time receipt."""
    return await chat_service.mark_conversation_as_read(conversation_id, current_user.id)


@router.websocket("/ws/chat")
async def chat_websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
):
    """
    Authenticated real-time WebSocket connection for live messaging, typing indicators,
    read receipts, and online status.
    """
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception as e:
        logger.warning("WebSocket authentication failed: %s", e)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(user_id, websocket)

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                msg_json = json.loads(raw_data)
                action = msg_json.get("action")

                if action == "ping":
                    await websocket.send_text(json.dumps({"event": "pong"}))

                elif action == "send_message":
                    conv_id = msg_json.get("conversation_id")
                    text = msg_json.get("text", "")
                    media_url = msg_json.get("media_url", "")
                    message_type = msg_json.get("message_type", "text")
                    recipient_id = msg_json.get("recipient_id")

                    if conv_id and (text or media_url):
                        await chat_service.send_message(
                            conversation_id=conv_id,
                            sender_id=user_id,
                            text=text,
                            media_url=media_url,
                            message_type=message_type,
                            recipient_id=recipient_id,
                        )

                elif action == "typing":
                    recipient_id = msg_json.get("recipient_id")
                    conv_id = msg_json.get("conversation_id")
                    is_typing = bool(msg_json.get("is_typing", False))
                    if recipient_id:
                        await ws_manager.send_personal_message(
                            recipient_id,
                            {
                                "event": "typing",
                                "conversation_id": conv_id,
                                "sender_id": user_id,
                                "is_typing": is_typing,
                            },
                        )

                elif action == "read":
                    conv_id = msg_json.get("conversation_id")
                    if conv_id:
                        await chat_service.mark_conversation_as_read(conv_id, user_id)

            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)
    except Exception as e:
        logger.warning("WebSocket error for user %s: %s", user_id, e)
        ws_manager.disconnect(user_id, websocket)
