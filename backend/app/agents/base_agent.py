"""
Base Agent — Abstract foundation for all specialized agents.

Provides:
- Tool registry and invocation
- Memory integration (short-term context + long-term vector store)
- LLM generation with system prompts
- State machine transitions
- Structured logging
- Retry with exponential backoff
- Token budget enforcement
"""

from __future__ import annotations

import uuid
import json
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

from app.llm.gemini_client import GeminiClient, get_gemini_client
from app.config import settings

logger = structlog.get_logger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    ASSIGNED = "assigned"
    THINKING = "thinking"
    TOOL_CALLING = "tool_calling"
    WAITING_APPROVAL = "waiting_approval"
    EXECUTING = "executing"
    DONE = "done"
    FAILED = "failed"


class AgentMessage:
    """Structured inter-agent message envelope."""

    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        project_id: str,
        message_type: str,
        payload: dict,
        requires_approval: bool = False,
        priority: int = 5,
    ):
        self.message_id = str(uuid.uuid4())
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.project_id = project_id
        self.message_type = message_type
        self.payload = payload
        self.requires_approval = requires_approval
        self.priority = priority
        self.timestamp = datetime.utcnow().isoformat()
        self.retry_count = 0

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "project_id": self.project_id,
            "message_type": self.message_type,
            "payload": self.payload,
            "requires_approval": self.requires_approval,
            "priority": self.priority,
            "timestamp": self.timestamp,
            "retry_count": self.retry_count,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class BaseAgent(ABC):
    """
    Abstract base for all AI agents in the platform.

    Subclasses must implement:
    - system_prompt (property)
    - execute_task(task_data: dict) -> dict
    """

    def __init__(
        self,
        agent_type: str,
        project_id: str,
        use_flash_llm: bool = False,
        event_bus=None,
    ):
        self.agent_type = agent_type
        self.project_id = project_id
        self.agent_id = f"{agent_type}_{project_id[:8]}"
        self.status = AgentStatus.IDLE
        self.llm: GeminiClient = get_gemini_client(use_flash=use_flash_llm)
        self.event_bus = event_bus
        self.tools: dict[str, Any] = {}
        self.context_history: list[dict] = []
        self.tokens_used: int = 0
        self.log = logger.bind(agent=self.agent_type, project_id=project_id)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Agent's system/role prompt — defines persona and responsibilities."""
        ...

    @abstractmethod
    async def execute_task(self, task_data: dict) -> dict:
        """
        Core task execution logic.
        Returns dict with keys: success, result, artifacts, tokens_used
        """
        ...

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    async def think(self, prompt: str, temperature: float = 0.7) -> str:
        """
        Generate a response using this agent's system prompt.
        Enforces token budget and tracks usage.
        """
        self._set_status(AgentStatus.THINKING)

        # Check budget
        if self.tokens_used >= settings.TOKEN_BUDGET_PER_PROJECT:
            raise RuntimeError(
                f"[{self.agent_type}] Token budget exhausted: {self.tokens_used}"
            )

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt=self.system_prompt,
            temperature=temperature,
        )

        usage = self.llm.get_token_usage()
        self.tokens_used = usage["total_tokens"]
        self.log.debug("LLM generation complete", tokens_used=self.tokens_used)
        return response

    async def think_and_parse_json(self, prompt: str) -> dict:
        """Generate and parse JSON from LLM response."""
        raw = await self.think(prompt + "\n\nRespond ONLY with valid JSON, no markdown fences.")
        # Strip markdown code blocks if present
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1])
        return json.loads(clean)

    # ------------------------------------------------------------------
    # Tool management
    # ------------------------------------------------------------------

    def register_tool(self, name: str, tool_fn) -> None:
        """Register a callable tool by name."""
        self.tools[name] = tool_fn
        self.log.debug("Tool registered", tool=name)

    async def call_tool(self, tool_name: str, **kwargs) -> Any:
        """Invoke a registered tool with kwargs."""
        if tool_name not in self.tools:
            raise ValueError(f"Tool '{tool_name}' not registered for {self.agent_type}")

        self._set_status(AgentStatus.TOOL_CALLING)
        self.log.info("Calling tool", tool=tool_name, kwargs=list(kwargs.keys()))

        try:
            result = await self.tools[tool_name](**kwargs)
            self._set_status(AgentStatus.EXECUTING)
            return result
        except Exception as exc:
            self.log.error("Tool execution failed", tool=tool_name, error=str(exc))
            raise

    # ------------------------------------------------------------------
    # Memory / context
    # ------------------------------------------------------------------

    def add_to_context(self, role: str, content: str) -> None:
        """Append to short-term context buffer (last 20 exchanges)."""
        self.context_history.append({"role": role, "content": content})
        if len(self.context_history) > 20:
            self.context_history.pop(0)

    def get_context_summary(self) -> str:
        """Build context string from history for inclusion in prompts."""
        if not self.context_history:
            return ""
        lines = []
        for entry in self.context_history[-10:]:
            lines.append(f"[{entry['role'].upper()}]: {entry['content'][:500]}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def send_message(
        self,
        to_agent: str,
        message_type: str,
        payload: dict,
        requires_approval: bool = False,
    ) -> None:
        """Publish a message to the event bus."""
        msg = AgentMessage(
            from_agent=self.agent_type,
            to_agent=to_agent,
            project_id=self.project_id,
            message_type=message_type,
            payload=payload,
            requires_approval=requires_approval,
        )
        if self.event_bus:
            await self.event_bus.publish(msg)
        self.log.info("Message sent", to=to_agent, type=message_type)

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def _set_status(self, status: AgentStatus) -> None:
        self.status = status
        self.log.debug("Status changed", status=status.value)

    async def run(self, task_data: dict, max_retries: int = 3) -> dict:
        """
        Main entry point. Wraps execute_task with retry + status management.
        """
        self._set_status(AgentStatus.ASSIGNED)
        self.log.info("Task received", task_id=task_data.get("task_id"))

        for attempt in range(1, max_retries + 1):
            try:
                result = await self.execute_task(task_data)
                self._set_status(AgentStatus.DONE)
                self.log.info("Task completed successfully", attempt=attempt)
                return result
            except Exception as exc:
                self.log.warning(
                    "Task attempt failed",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(exc),
                )
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)  # exponential backoff
                else:
                    self._set_status(AgentStatus.FAILED)
                    return {
                        "success": False,
                        "error": str(exc),
                        "agent_type": self.agent_type,
                        "attempts": attempt,
                    }
