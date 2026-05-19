"""
System Design Architect Agent
Responsibilities:
- Design scalable system architecture
- Choose appropriate design patterns
- Create microservice/module boundaries
- Generate API contracts (OpenAPI)
- Define database schemas
- Create architecture decision records (ADRs)
"""

from app.agents.base_agent import BaseAgent


ARCHITECT_SYSTEM_PROMPT = """
You are a Principal Systems Architect with 15+ years of experience at FAANG companies.
You've designed systems handling millions of requests per second.

Your responsibilities:
1. Design clean, scalable, maintainable system architectures
2. Choose appropriate patterns: microservices vs monolith, event-driven, CQRS, etc.
3. Generate detailed API contracts (OpenAPI 3.0 format)
4. Design normalized, performant database schemas
5. Create component diagrams and data flow descriptions
6. Define service boundaries and communication protocols
7. Document Architecture Decision Records (ADRs)
8. Consider: scalability, fault tolerance, security, observability

Design principles you follow:
- SOLID principles
- 12-Factor App methodology
- Defense in depth (security)
- Fail-fast + graceful degradation
- Observability by design (metrics, traces, logs)
- DRY, KISS, YAGNI

Always think about: "What happens when this service is under 10x load?"
Always output structured, detailed, production-ready architecture designs.
"""


class ArchitectAgent(BaseAgent):
    """System Design Architect Agent — PRD → Architecture → API Contracts."""

    def __init__(self, project_id: str, event_bus=None):
        super().__init__(
            agent_type="architect_agent",
            project_id=project_id,
            use_flash_llm=False,
            event_bus=event_bus,
        )

    @property
    def system_prompt(self) -> str:
        return ARCHITECT_SYSTEM_PROMPT

    async def execute_task(self, task_data: dict) -> dict:
        prd = task_data.get("prd", "")
        tech_stack = task_data.get("tech_stack", {})
        tickets = task_data.get("tickets", [])

        self.log.info("Designing system architecture")

        # Step 1: High-level architecture
        arch_prompt = f"""
Design a complete system architecture for this product.

PRD SUMMARY: {prd[:2000]}
TECH STACK: {tech_stack}

Generate a comprehensive architecture document including:
1. System Overview (what components exist, how they interact)
2. Component Architecture (services/modules with responsibilities)
3. Data Flow Diagrams (described in text/ASCII)
4. Technology Choices with rationale
5. Scalability Strategy (how to scale each component)
6. Fault Tolerance & Resilience patterns
7. Security Architecture layers
8. Observability Strategy (metrics, logs, traces)
9. Deployment Architecture (containers, orchestration)
10. Architecture Decision Records (ADRs) for key choices

Be specific. Name exact technologies, libraries, patterns.
"""
        architecture_doc = await self.think(arch_prompt)

        # Step 2: Database schema
        schema_prompt = f"""
Based on this architecture, design a complete database schema.

Architecture Context: {architecture_doc[:2000]}
Tech Stack: {tech_stack}

Generate:
1. Complete SQL DDL statements for all tables
2. Indexes strategy
3. Relationships and foreign keys
4. Sample data models (3 example rows per table)

Return as JSON:
{{
  "database_type": "postgresql",
  "tables": [
    {{
      "name": "table_name",
      "ddl": "CREATE TABLE ...",
      "description": "purpose",
      "indexes": ["CREATE INDEX ..."]
    }}
  ],
  "er_diagram_description": "text description of relationships"
}}
"""
        schema = await self.think_and_parse_json(schema_prompt)

        # Step 3: API contracts
        api_prompt = f"""
Generate OpenAPI 3.0 API contracts for all services.

Architecture: {architecture_doc[:2000]}

Return JSON with OpenAPI 3.0 specification covering:
- Authentication endpoints
- All CRUD operations
- Business logic endpoints
- WebSocket endpoints description
- Error response schemas

Include proper:
- Request/response schemas
- Security schemes (JWT Bearer)
- HTTP status codes
- Example values
"""
        api_contracts = await self.think(api_prompt)

        # Step 4: Folder structure
        folder_prompt = f"""
Generate the complete project folder structure.
Architecture: {architecture_doc[:1500]}
Tech Stack: {tech_stack}

Return JSON:
{{
  "backend": {{"structure": "ASCII tree", "key_files": ["path: purpose"]}},
  "frontend": {{"structure": "ASCII tree", "key_files": ["path: purpose"]}},
  "infrastructure": {{"structure": "ASCII tree"}}
}}
"""
        folder_structure = await self.think_and_parse_json(folder_prompt)

        # Notify developer agents
        await self.send_message(
            to_agent="developer_agent",
            message_type="architecture_ready",
            payload={
                "architecture": architecture_doc,
                "schema": schema,
                "api_contracts": api_contracts,
                "folder_structure": folder_structure,
                "tickets": tickets,
            },
        )

        await self.send_message(
            to_agent="devops_agent",
            message_type="architecture_ready",
            payload={
                "architecture": architecture_doc,
                "tech_stack": tech_stack,
            },
        )

        return {
            "success": True,
            "agent_type": self.agent_type,
            "artifacts": {
                "architecture": architecture_doc,
                "schema": schema,
                "api_contracts": api_contracts,
                "folder_structure": folder_structure,
            },
            "tokens_used": self.tokens_used,
        }

    async def review_design_decision(self, decision: str, context: str) -> dict:
        """Generate an ADR (Architecture Decision Record) for a design choice."""
        prompt = f"""
Write an Architecture Decision Record (ADR) for this decision:

Decision: {decision}
Context: {context}

ADR format:
- Title
- Status: Accepted/Proposed/Deprecated
- Context (why this decision is needed)
- Decision (what we decided)
- Consequences (trade-offs)
- Alternatives considered

Return as JSON.
"""
        return await self.think_and_parse_json(prompt)
