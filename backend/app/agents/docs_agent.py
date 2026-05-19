"""
Documentation Agent
Responsibilities:
- Generate comprehensive README files
- Create API documentation (OpenAPI/Swagger)
- Write architecture documentation with diagrams
- Create developer onboarding guides
- Generate changelog and release notes
"""

from app.agents.base_agent import BaseAgent
from app.tools.file_tool import FileTool


DOCS_SYSTEM_PROMPT = """
You are a Senior Technical Writer and Documentation Engineer.
You create documentation that developers actually want to read.

Your documentation principles:
1. Clear and concise — no fluff, maximum signal
2. Practical — lead with examples, not theory
3. Complete — cover all edge cases and gotchas
4. Up-to-date — documentation as code, versioned with the codebase
5. Structured — logical hierarchy, easy to navigate

Documentation you produce:
- README.md: Project overview, quick start (< 5 minutes to get running)
- ARCHITECTURE.md: System design, component relationships, data flow
- API.md: All endpoints with request/response examples
- CONTRIBUTING.md: Setup, coding standards, PR process
- DEPLOYMENT.md: Step-by-step production deployment
- CHANGELOG.md: Versioned change history

Technical writing standards:
- Use active voice
- Lead with the most important information
- Include code examples that actually run
- Use diagrams when they clarify complexity
- Keep sentences short and scannable

Your README structure:
1. One-liner description
2. Key features list
3. Architecture diagram
4. Prerequisites
5. Quick Start (< 10 commands to run locally)
6. Configuration reference
7. API overview
8. Development guide
9. Deployment guide
10. Contributing
11. License
"""


class DocsAgent(BaseAgent):
    """Documentation Agent — Code + Architecture → Comprehensive Docs."""

    def __init__(self, project_id: str, event_bus=None):
        super().__init__(
            agent_type="docs_agent",
            project_id=project_id,
            use_flash_llm=False,
            event_bus=event_bus,
        )
        self.file_tool = FileTool(project_id=project_id)
        self.register_tool("write_file", self.file_tool.write_file)

    @property
    def system_prompt(self) -> str:
        return DOCS_SYSTEM_PROMPT

    async def execute_task(self, task_data: dict) -> dict:
        """Generate complete project documentation."""
        architecture = task_data.get("architecture", "")
        prd = task_data.get("prd", "")
        tech_stack = task_data.get("tech_stack", {})
        project_name = task_data.get("project_name", "project")
        api_contracts = task_data.get("api_contracts", "")
        generated_files = task_data.get("generated_files", [])

        self.log.info("Generating documentation", project=project_name)

        docs_generated = []

        # 1. README.md
        readme_prompt = f"""
Write a world-class README.md for this project.

PROJECT NAME: {project_name}
TECH STACK: {tech_stack}
ARCHITECTURE SUMMARY: {architecture[:2000]}
PRD SUMMARY: {prd[:1000]}

Make it:
- Professional and engaging (like top GitHub projects)
- Include badges (build status, license, version)
- Clear quick start guide
- Feature highlights with emojis
- Architecture overview
- Complete setup instructions
- Docker setup instructions
- Environment variables table
- API overview
- Contributing guide link

Output ONLY the markdown content.
"""
        readme = await self.think(readme_prompt)
        await self.call_tool("write_file", path="README.md", content=readme)
        docs_generated.append("README.md")

        # 2. ARCHITECTURE.md
        arch_prompt = f"""
Write a detailed ARCHITECTURE.md document.

ARCHITECTURE: {architecture[:3000]}
TECH STACK: {tech_stack}

Include:
- System overview
- Component diagram (ASCII art)
- Data flow description
- Technology choices with rationale
- Scalability notes
- Deployment architecture

Output ONLY markdown.
"""
        arch_doc = await self.think(arch_prompt)
        await self.call_tool("write_file", path="docs/ARCHITECTURE.md", content=arch_doc)
        docs_generated.append("docs/ARCHITECTURE.md")

        # 3. API Documentation
        api_prompt = f"""
Write comprehensive API documentation in Markdown.

API CONTRACTS: {api_contracts[:3000]}
TECH STACK: {tech_stack}

Format each endpoint as:
## Endpoint Name
**Method:** POST
**Path:** /api/v1/endpoint
**Auth:** JWT Bearer

**Request Body:**
```json
{{...}}
```

**Success Response (200):**
```json
{{...}}
```

**Error Responses:**
- 400: Bad request
- 401: Unauthorized

Include authentication guide at the top.
Output ONLY markdown.
"""
        api_doc = await self.think(api_prompt)
        await self.call_tool("write_file", path="docs/API.md", content=api_doc)
        docs_generated.append("docs/API.md")

        # 4. DEPLOYMENT.md
        deploy_prompt = f"""
Write a production deployment guide.

TECH STACK: {tech_stack}
ARCHITECTURE: {architecture[:1500]}

Include:
1. Prerequisites (tools to install)
2. Environment setup
3. Database initialization
4. Docker Compose deployment (local/staging)
5. Kubernetes deployment (production)
6. SSL/TLS setup
7. Monitoring setup
8. Backup strategy
9. Rollback procedure
10. Troubleshooting guide

Be very specific with exact commands.
Output ONLY markdown.
"""
        deploy_doc = await self.think(deploy_prompt)
        await self.call_tool("write_file", path="docs/DEPLOYMENT.md", content=deploy_doc)
        docs_generated.append("docs/DEPLOYMENT.md")

        # 5. CONTRIBUTING.md
        contrib_prompt = f"""
Write a CONTRIBUTING.md for: {project_name}
Tech Stack: {tech_stack}

Include:
- Development environment setup
- Code style guide
- Testing requirements (coverage %)
- PR process and review checklist
- Conventional commit message format
- Issue reporting template
- Code of conduct

Output ONLY markdown.
"""
        contrib_doc = await self.think(contrib_prompt)
        await self.call_tool("write_file", path="CONTRIBUTING.md", content=contrib_doc)
        docs_generated.append("CONTRIBUTING.md")

        return {
            "success": True,
            "agent_type": self.agent_type,
            "artifacts": {"generated_docs": docs_generated},
            "tokens_used": self.tokens_used,
        }
