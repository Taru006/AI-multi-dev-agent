"""
Redis-backed Event Bus for inter-agent communication.
Supports pub/sub with typed message routing and async handlers.
"""

import asyncio
import json
from typing import Callable, Dict, List
import redis.asyncio as aioredis
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class EventBus:
    """
    Async Redis pub/sub event bus for agent-to-agent messaging.

    Each project gets its own channel namespace:
    channel: `project:{project_id}:events`
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.channel = f"project:{project_id}:events"
        self._handlers: Dict[str, List[Callable]] = {}
        self._redis: aioredis.Redis = aioredis.from_url(
            settings.REDIS_URL, encoding="utf-8", decode_responses=True
        )
        self._pubsub = None
        self._listener_task: asyncio.Task = None
        self.log = logger.bind(project_id=project_id)

    def on(self, event_type: str, handler: Callable) -> None:
        """Register an async handler for a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        self.log.debug("Handler registered", event_type=event_type)

    async def start_listening(self) -> None:
        """Begin listening for events on the Redis channel."""
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self.channel)
        self._listener_task = asyncio.create_task(self._listen_loop())
        self.log.info("Event bus listening", channel=self.channel)

    async def _listen_loop(self) -> None:
        """Background task: dispatch incoming messages to handlers."""
        async for message in self._pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                msg_data = json.loads(message["data"])
                event_type = msg_data.get("message_type", "")
                handlers = self._handlers.get(event_type, [])
                for handler in handlers:
                    # Create a simple object with .payload attribute
                    class Msg:
                        def __init__(self, d):
                            self.message_id = d.get("message_id")
                            self.from_agent = d.get("from_agent")
                            self.to_agent = d.get("to_agent")
                            self.project_id = d.get("project_id")
                            self.message_type = d.get("message_type")
                            self.payload = d.get("payload", {})
                            self.requires_approval = d.get("requires_approval", False)

                    await handler(Msg(msg_data))
            except Exception as exc:
                self.log.error("Event dispatch error", error=str(exc))

    async def publish(self, message) -> None:
        """Publish an AgentMessage to the event bus."""
        payload = message.to_json() if hasattr(message, "to_json") else json.dumps(message)
        await self._redis.publish(self.channel, payload)
        self.log.debug("Event published", message_type=getattr(message, "message_type", "unknown"))

    async def publish_raw(self, event_type: str, payload: dict) -> None:
        """Publish a raw event dict."""
        msg = {
            "message_type": event_type,
            "payload": payload,
            "project_id": self.project_id,
        }
        await self._redis.publish(self.channel, json.dumps(msg))

    async def stop(self) -> None:
        """Gracefully stop the event bus listener."""
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            await self._pubsub.unsubscribe(self.channel)
        await self._redis.aclose()
        self.log.info("Event bus stopped")
