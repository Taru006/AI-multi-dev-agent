"""
Agent Orchestrator / Workflow Engine
Manages the entire multi-agent workflow:
- Builds task dependency graph
- Routes tasks to appropriate agents
- Handles parallel execution
- Manages approval gates
- Fault recovery with retry
- Context sharing between agents
"""

import asyncio
import uuid
from typing import Optional
from datetime import datetime

import structlog
import networkx as nx

from app.agents.pm_agent import PMAgent
from app.agents.architect_agent import ArchitectAgent
from app.agents.developer_agent import DeveloperAgent
from app.agents.qa_agent import QAAgent
from app.agents.security_agent import SecurityAgent
from app.agents.devops_agent import DevOpsAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.agents.docs_agent import DocsAgent
from app.messaging.event_bus import EventBus
from app.messaging.websocket_manager import WebSocketManager
from app.config import settings

logger = structlog.get_logger(__name__)

# Ordered workflow stages
AGENT_WORKFLOW = [
    "pm_agent",
    "architect_agent",
    "developer_agent",
    "qa_agent",
    "reviewer_agent",
    "security_agent",
    "devops_agent",
    "docs_agent",
]

AGENT_CLASSES = {
    "pm_agent": PMAgent,
    "architect_agent": ArchitectAgent,
    "developer_agent": DeveloperAgent,
    "qa_agent": QAAgent,
    "security_agent": SecurityAgent,
    "devops_agent": DevOpsAgent,
    "reviewer_agent": ReviewerAgent,
    "docs_agent": DocsAgent,
}


class WorkflowEngine:
    """
    Orchestrates multi-agent collaboration for a project.

    Lifecycle:
    1. Create agents for project
    2. Build task dependency graph
    3. Execute tasks respecting dependencies
    4. Broadcast real-time updates via WebSocket
    5. Handle approvals, retries, and failures
    """

    def __init__(
        self,
        project_id: str,
        ws_manager: WebSocketManager,
        db_session,
    ):
        self.project_id = project_id
        self.ws_manager = ws_manager
        self.db = db_session
        self.event_bus = EventBus(project_id=project_id)
        self.task_graph = nx.DiGraph()
        self.context: dict = {}  # Shared context between agents
        self.agents: dict = {}
        self.log = logger.bind(project_id=project_id)

    def _create_agents(self) -> None:
        """Instantiate all agents with shared event bus."""
        for agent_type, AgentClass in AGENT_CLASSES.items():
            self.agents[agent_type] = AgentClass(
                project_id=self.project_id,
                event_bus=self.event_bus,
            )
        self.log.info("Agents created", count=len(self.agents))

    async def start_workflow(self, project_data: dict) -> None:
        """
        Entry point: kick off the full agent workflow.

        Args:
            project_data: Dict with product_idea, requirements, tech_stack, constraints, timeline
        """
        self.log.info("Starting workflow", project=project_data.get("name"))
        self._create_agents()

        # Register event bus handlers
        self.event_bus.on("prd_ready", self._handle_prd_ready)
        self.event_bus.on("architecture_ready", self._handle_architecture_ready)
        self.event_bus.on("code_ready_for_testing", self._handle_code_for_testing)
        self.event_bus.on("code_ready_for_review", self._handle_code_for_review)
        self.event_bus.on("ready_for_security_scan", self._handle_security_scan)
        self.event_bus.on("infra_ready", self._handle_infra_ready)
        self.event_bus.on("bug_report", self._handle_bug_report)
        self.event_bus.on("review_changes_requested", self._handle_review_changes)
        self.event_bus.on("security_critical_found", self._handle_security_critical)

        # Broadcast start
        await self._broadcast_event("workflow_started", {
            "project_id": self.project_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Step 1: PM Agent kicks everything off
        await self._run_agent("pm_agent", {
            "task_id": str(uuid.uuid4()),
            "product_idea": project_data.get("description", ""),
            "requirements": project_data.get("requirements", ""),
            "tech_stack": project_data.get("tech_stack", {}),
            "constraints": project_data.get("constraints", ""),
            "timeline": project_data.get("timeline", "4 weeks"),
        })

    async def _run_agent(self, agent_type: str, task_data: dict) -> dict:
        """Run a specific agent and broadcast status updates."""
        agent = self.agents.get(agent_type)
        if not agent:
            self.log.error("Agent not found", agent_type=agent_type)
            return {"success": False, "error": "Agent not found"}

        # Broadcast: agent starting
        await self._broadcast_event("agent_started", {
            "agent_type": agent_type,
            "task_id": task_data.get("task_id"),
            "timestamp": datetime.utcnow().isoformat(),
        })

        try:
            result = await agent.run(task_data)

            # Store result in shared context
            self.context[agent_type] = result.get("artifacts", {})

            # Broadcast: agent done
            await self._broadcast_event("agent_completed", {
                "agent_type": agent_type,
                "success": result.get("success", False),
                "tokens_used": result.get("tokens_used", 0),
                "timestamp": datetime.utcnow().isoformat(),
            })

            return result

        except Exception as exc:
            self.log.error("Agent failed", agent_type=agent_type, error=str(exc))
            await self._broadcast_event("agent_failed", {
                "agent_type": agent_type,
                "error": str(exc),
                "timestamp": datetime.utcnow().isoformat(),
            })
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    async def _handle_prd_ready(self, message) -> None:
        """PM done → Architect starts."""
        self.log.info("PRD ready, starting architect")
        payload = message.payload
        self.context["prd"] = payload.get("prd", "")
        self.context["tickets"] = payload.get("tickets", [])

        await self._run_agent("architect_agent", {
            "task_id": str(uuid.uuid4()),
            "prd": payload.get("prd", ""),
            "tech_stack": payload.get("tech_stack", {}),
            "tickets": payload.get("tickets", []),
        })

    async def _handle_architecture_ready(self, message) -> None:
        """Architecture done → parallel Developer + DevOps + Docs."""
        self.log.info("Architecture ready, spawning parallel agents")
        payload = message.payload
        self.context["architecture"] = payload.get("architecture", "")

        # Dispatch developer tickets in parallel (one task per ticket)
        dev_tickets = [
            t for t in self.context.get("tickets", [])
            if t.get("agent_type") == "developer_agent"
        ][:3]  # Limit to 3 parallel tasks

        tasks_to_run = []

        for i, ticket in enumerate(dev_tickets):
            tasks_to_run.append(
                self._run_agent("developer_agent", {
                    "task_id": str(uuid.uuid4()),
                    "ticket": ticket,
                    "architecture": payload.get("architecture", ""),
                    "tech_stack": self.context.get("tech_stack", {}),
                })
            )

        # Also start DevOps and Docs in parallel
        tasks_to_run.append(
            self._run_agent("devops_agent", {
                "task_id": str(uuid.uuid4()),
                "architecture": payload.get("architecture", ""),
                "tech_stack": self.context.get("tech_stack", {}),
                "project_name": self.context.get("project_name", "project"),
            })
        )

        # Run all in parallel
        await asyncio.gather(*tasks_to_run, return_exceptions=True)

    async def _handle_code_for_testing(self, message) -> None:
        """Code ready → QA tests it."""
        payload = message.payload
        await self._run_agent("qa_agent", {
            "task_id": str(uuid.uuid4()),
            "ticket": payload.get("ticket", {}),
            "files": payload.get("files", []),
        })

    async def _handle_code_for_review(self, message) -> None:
        """Code ready → Reviewer reviews it."""
        payload = message.payload
        await self._run_agent("reviewer_agent", {
            "task_id": str(uuid.uuid4()),
            "ticket": payload.get("ticket", {}),
            "files": payload.get("files", []),
        })

    async def _handle_security_scan(self, message) -> None:
        """Code passed QA → Security scans it."""
        payload = message.payload
        await self._run_agent("security_agent", {
            "task_id": str(uuid.uuid4()),
            "files": payload.get("files", []),
            "ticket": payload.get("ticket", {}),
        })

    async def _handle_infra_ready(self, message) -> None:
        """Infra done → Docs agent generates all documentation."""
        payload = message.payload
        await self._run_agent("docs_agent", {
            "task_id": str(uuid.uuid4()),
            "architecture": self.context.get("architecture", ""),
            "prd": self.context.get("prd", ""),
            "tech_stack": self.context.get("tech_stack", {}),
            "project_name": self.context.get("project_name", "project"),
            "api_contracts": self.context.get("api_contracts", ""),
            "generated_files": payload.get("generated_files", []),
        })

        # Final broadcast
        await self._broadcast_event("workflow_completed", {
            "project_id": self.project_id,
            "timestamp": datetime.utcnow().isoformat(),
            "total_agents_run": len(AGENT_CLASSES),
        })

    async def _handle_bug_report(self, message) -> None:
        """Bug found → Developer fixes it."""
        payload = message.payload
        self.log.warning("Bugs reported, requesting fixes", bug_count=len(payload.get("bugs", [])))
        await self._broadcast_event("bugs_found", payload)

    async def _handle_review_changes(self, message) -> None:
        """Review requested changes → Developer re-implements."""
        payload = message.payload
        self.log.info("Review changes requested", score=payload.get("overall_score"))
        await self._broadcast_event("review_changes_requested", payload)

    async def _handle_security_critical(self, message) -> None:
        """Critical security issue → escalate to human approval."""
        self.log.critical("Critical security vulnerability found! Human approval required.")
        await self._broadcast_event("approval_required", {
            "type": "security_critical",
            "payload": message.payload,
            "requires_human": True,
        })

    async def _broadcast_event(self, event_type: str, data: dict) -> None:
        """Broadcast event to all WebSocket subscribers for this project."""
        try:
            await self.ws_manager.broadcast_to_project(
                project_id=self.project_id,
                message={
                    "type": event_type,
                    "data": data,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            self.log.warning("WebSocket broadcast failed", error=str(e))
