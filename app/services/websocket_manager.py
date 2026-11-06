import json
import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger("nextstop.websocket")


class WebSocketManager:
    """Manages active WebSocket connections for real-time chat, typing, and notifications."""

    def __init__(self):
        # Maps user_id -> List of active WebSocket sessions (supports multiple devices/tabs)
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        """Accepts and registers a new WebSocket connection."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info("User %s connected over WebSocket. Total sessions: %d", user_id, len(self.active_connections[user_id]))

    def disconnect(self, user_id: str, websocket: WebSocket):
        """Removes a disconnected WebSocket session."""
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info("User %s disconnected from WebSocket.", user_id)

    def is_user_online(self, user_id: str) -> bool:
        """Checks if a user has at least one active connection."""
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0

    async def send_personal_message(self, user_id: str, payload: dict):
        """Sends a JSON payload to all active sockets belonging to user_id."""
        if user_id in self.active_connections:
            data = json.dumps(payload, default=str)
            dead_sockets = []
            for ws in list(self.active_connections[user_id]):
                try:
                    await ws.send_text(data)
                except Exception as e:
                    logger.warning("Failed to send message to user %s: %s", user_id, e)
                    dead_sockets.append(ws)

            for dead in dead_sockets:
                self.disconnect(user_id, dead)

    async def broadcast_to_users(self, user_ids: List[str], payload: dict):
        """Broadcasts payload to a list of users."""
        for uid in user_ids:
            await self.send_personal_message(uid, payload)


ws_manager = WebSocketManager()
