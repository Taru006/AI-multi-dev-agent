"""
WebSocket Manager — manages active WebSocket connections
and broadcasts project events to subscribed clients.
"""

import json
from typing import Dict, Set
from fastapi import WebSocket
import structlog

logger = structlog.get_logger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections grouped by project_id.

    Each browser tab connects to /ws/{project_id} and receives
    real-time events as agents work on the project.
    """

    def __init__(self):
        # project_id -> set of active WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}
        self.log = logger.bind(component="WebSocketManager")

    async def connect(self, project_id: str, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        if project_id not in self._connections:
            self._connections[project_id] = set()
        self._connections[project_id].add(websocket)
        self.log.info("WebSocket connected", project_id=project_id,
                      total=len(self._connections[project_id]))

    def disconnect(self, project_id: str, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket."""
        if project_id in self._connections:
            self._connections[project_id].discard(websocket)
            if not self._connections[project_id]:
                del self._connections[project_id]
        self.log.info("WebSocket disconnected", project_id=project_id)

    async def broadcast_to_project(self, project_id: str, message: dict) -> None:
        """
        Send a JSON message to all connections subscribed to a project.
        Automatically removes stale/dead connections.
        """
        if project_id not in self._connections:
            return

        dead_connections = set()
        payload = json.dumps(message, default=str)

        for ws in self._connections[project_id].copy():
            try:
                await ws.send_text(payload)
            except Exception:
                dead_connections.add(ws)

        # Cleanup dead connections
        for ws in dead_connections:
            self._connections[project_id].discard(ws)

    async def send_personal_message(self, websocket: WebSocket, message: dict) -> None:
        """Send a message to a single WebSocket connection."""
        await websocket.send_text(json.dumps(message, default=str))

    def get_connection_count(self, project_id: str) -> int:
        """Return active connection count for a project."""
        return len(self._connections.get(project_id, set()))

    def get_all_projects(self) -> list:
        """Return list of projects with active connections."""
        return list(self._connections.keys())
