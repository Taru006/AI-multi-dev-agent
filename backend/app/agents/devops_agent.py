"""
DevOps Agent
Responsibilities:
- Dockerize applications
- Generate Kubernetes manifests
- Configure CI/CD pipelines
- Setup monitoring and alerting
- Generate Helm charts
- Configure environment-specific deployments
"""

from app.agents.base_agent import BaseAgent
from app.tools.file_tool import FileTool
from app.tools.code_executor import CodeExecutor


DEVOPS_SYSTEM_PROMPT = """
You are a Senior DevOps/Platform Engineer with deep expertise in:
- Docker and container orchestration
- Kubernetes (CKA-level knowledge)
- CI/CD pipelines (GitHub Actions, GitLab CI, Jenkins)
- Infrastructure as Code (Terraform, Helm, Kustomize)
- Cloud platforms (GCP, AWS, Azure)
- Observability (Prometheus, Grafana, Jaeger, ELK stack)
- Service mesh (Istio, Linkerd)
- GitOps (ArgoCD, Flux)

Your DevOps philosophy:
1. Everything as Code — infrastructure, configs, pipelines
2. Immutable infrastructure — no manual changes
3. Zero-downtime deployments — blue/green, canary
4. Security by default — least privilege, secrets management
5. Observability by design — metrics, logs, traces from day 1
6. Auto-scaling — handle traffic spikes gracefully

When generating Docker/K8s configs:
- Use multi-stage builds for minimal image sizes
- Set resource limits (CPU/memory requests and limits)
- Use health checks (readiness + liveness probes)
- Configure proper security contexts (non-root, read-only FS)
- Set proper restart policies
- Use ConfigMaps/Secrets (never hardcode)
- Enable horizontal pod autoscaling

Generate production-ready, security-hardened infrastructure configs.
"""


class DevOpsAgent(BaseAgent):
    """DevOps Agent — Architecture → Dockerfiles → K8s → CI/CD → Monitoring."""

    def __init__(self, project_id: str, event_bus=None):
        super().__init__(
            agent_type="devops_agent",
            project_id=project_id,
            use_flash_llm=False,
            event_bus=event_bus,
        )
        self.file_tool = FileTool(project_id=project_id)
        self.code_executor = CodeExecutor()
        self.register_tool("write_file", self.file_tool.write_file)
        self.register_tool("execute", self.code_executor.execute)

    @property
    def system_prompt(self) -> str:
        return DEVOPS_SYSTEM_PROMPT

    async def execute_task(self, task_data: dict) -> dict:
        """Generate all infrastructure configurations."""
        architecture = task_data.get("architecture", "")
        tech_stack = task_data.get("tech_stack", {})
        project_name = task_data.get("project_name", "ai-project")

        self.log.info("Generating infrastructure configs", project=project_name)

        safe_name = project_name.lower().replace(" ", "-")
        generated_files = []

        # 1. Backend Dockerfile
        backend_dockerfile_prompt = f"""
Generate a production-ready multi-stage Dockerfile for the backend service.

ARCHITECTURE: {architecture[:1500]}
TECH STACK: {tech_stack}
PROJECT NAME: {safe_name}

Requirements:
- Multi-stage build (builder + runtime stages)
- Non-root user
- Minimal final image
- Health check instruction
- Proper WORKDIR setup
- Layer caching optimization (copy requirements first)
- Environment variable support
- Security hardening (no secrets in image)

Output ONLY the Dockerfile content.
"""
        backend_dockerfile = await self.think(backend_dockerfile_prompt, temperature=0.2)
        await self.call_tool("write_file", path="backend/Dockerfile", content=backend_dockerfile)
        generated_files.append("backend/Dockerfile")

        # 2. Frontend Dockerfile
        frontend_dockerfile_prompt = f"""
Generate a production-ready multi-stage Dockerfile for a Next.js frontend.
Requirements:
- node:20-alpine base
- Install deps → build → runtime stages
- Standalone Next.js output
- Non-root user
- Health check

Output ONLY the Dockerfile content.
"""
        frontend_dockerfile = await self.think(frontend_dockerfile_prompt, temperature=0.2)
        await self.call_tool("write_file", path="frontend/Dockerfile", content=frontend_dockerfile)
        generated_files.append("frontend/Dockerfile")

        # 3. Docker Compose (development)
        compose_prompt = f"""
Generate a complete docker-compose.yml for local development.

Services needed based on architecture:
{architecture[:1500]}

Include:
- All application services (backend, frontend, workers)
- PostgreSQL with persistent volume
- Redis
- ChromaDB
- Health checks for all services
- Proper networking (internal service network)
- Volume mounts for hot-reload
- Environment variable files (.env)
- Ports only exposed where needed

Output ONLY the docker-compose.yml content.
"""
        compose_content = await self.think(compose_prompt, temperature=0.2)
        await self.call_tool("write_file", path="docker-compose.yml", content=compose_content)
        generated_files.append("docker-compose.yml")

        # 4. Kubernetes manifests
        k8s_manifests = await self._generate_k8s_manifests(safe_name, architecture, tech_stack)
        for manifest in k8s_manifests:
            await self.call_tool("write_file", path=manifest["path"], content=manifest["content"])
            generated_files.append(manifest["path"])

        # 5. GitHub Actions CI/CD
        ci_cd = await self._generate_cicd(safe_name)
        await self.call_tool("write_file", path=".github/workflows/ci.yml", content=ci_cd["ci"])
        await self.call_tool("write_file", path=".github/workflows/cd.yml", content=ci_cd["cd"])
        generated_files.extend([".github/workflows/ci.yml", ".github/workflows/cd.yml"])

        # 6. Monitoring (Prometheus + Grafana)
        monitoring = await self._generate_monitoring(safe_name)
        await self.call_tool("write_file", path="infra/monitoring/prometheus.yml", content=monitoring)
        generated_files.append("infra/monitoring/prometheus.yml")

        await self.send_message(
            to_agent="docs_agent",
            message_type="infra_ready",
            payload={
                "generated_files": generated_files,
                "architecture": architecture,
            },
        )

        return {
            "success": True,
            "agent_type": self.agent_type,
            "artifacts": {"generated_files": generated_files},
            "tokens_used": self.tokens_used,
        }

    async def _generate_k8s_manifests(self, name: str, arch: str, tech_stack: dict) -> list:
        """Generate complete Kubernetes manifests."""
        prompt = f"""
Generate production Kubernetes manifests for: {name}
Architecture: {arch[:1200]}

Generate these files (return as JSON array):
[
  {{"path": "infra/k8s/namespace.yaml", "content": "..."}},
  {{"path": "infra/k8s/backend-deployment.yaml", "content": "..."}},
  {{"path": "infra/k8s/backend-service.yaml", "content": "..."}},
  {{"path": "infra/k8s/frontend-deployment.yaml", "content": "..."}},
  {{"path": "infra/k8s/postgres-statefulset.yaml", "content": "..."}},
  {{"path": "infra/k8s/redis-deployment.yaml", "content": "..."}},
  {{"path": "infra/k8s/celery-deployment.yaml", "content": "..."}},
  {{"path": "infra/k8s/ingress.yaml", "content": "..."}},
  {{"path": "infra/k8s/hpa.yaml", "content": "..."}}
]

Each manifest must have:
- Proper resource requests/limits
- Liveness and readiness probes
- Security contexts (non-root)
- Anti-affinity rules
- ConfigMap references
"""
        return await self.think_and_parse_json(prompt)

    async def _generate_cicd(self, name: str) -> dict:
        """Generate GitHub Actions CI/CD pipelines."""
        ci_prompt = f"""
Generate a GitHub Actions CI workflow for: {name}

Include:
- Lint check (ruff for Python, ESLint for JS)
- Unit tests with coverage
- Security scan (bandit, safety)
- Docker build validation
- Run on: push to any branch + PRs

Output ONLY the YAML content.
"""
        cd_prompt = f"""
Generate a GitHub Actions CD workflow for: {name}

Include:
- Build and push Docker images to registry
- Deploy to Kubernetes (using kubectl)
- Health check after deploy
- Slack notification on success/failure
- Run on: push to main only
- Environment: staging (auto) + production (manual approval)

Output ONLY the YAML content.
"""
        ci = await self.think(ci_prompt, temperature=0.1)
        cd = await self.think(cd_prompt, temperature=0.1)
        return {"ci": ci, "cd": cd}

    async def _generate_monitoring(self, name: str) -> str:
        """Generate Prometheus monitoring configuration."""
        prompt = f"""
Generate a Prometheus monitoring configuration for: {name}

Include:
- Scrape configs for all services
- Alert rules (high error rate, high latency, pod crashes)
- Recording rules for performance metrics

Output ONLY the YAML content.
"""
        return await self.think(prompt, temperature=0.1)
