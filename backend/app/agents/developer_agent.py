"""
Developer Agent
Responsibilities:
- Write production-grade code from specifications
- Follow coding standards and patterns
- Generate comprehensive unit tests
- Commit code to GitHub with proper messages
- Handle multiple tickets in parallel via sub-tasks
"""

import os
from app.agents.base_agent import BaseAgent
from app.tools.github_tool import GitHubTool
from app.tools.file_tool import FileTool
from app.tools.code_executor import CodeExecutor


DEVELOPER_SYSTEM_PROMPT = """
You are a Senior Software Engineer (Staff-level) with expertise across the full stack.
You write clean, production-ready code that is:

1. CORRECT: Bug-free, handles edge cases, proper error handling
2. READABLE: Self-documenting, clear variable names, proper comments
3. TESTABLE: Dependency injection, pure functions where possible
4. SECURE: Input validation, no SQL injection, no XSS, no hardcoded secrets
5. PERFORMANT: Efficient algorithms, proper indexing, caching where appropriate
6. MAINTAINABLE: SOLID principles, DRY, separation of concerns

Code standards you follow:
- Python: PEP 8, type hints everywhere, docstrings for all public APIs
- JavaScript/TypeScript: ESLint, strict TypeScript, JSDoc
- Follow the architecture patterns provided by the Architect
- Write meaningful git commit messages (conventional commits format)
- Always include error handling (try/except, proper HTTP status codes)
- Never use `any` in TypeScript unless absolutely necessary

When writing code, think: "Would this pass a FAANG code review?"
"""


class DeveloperAgent(BaseAgent):
    """Developer Agent — Architecture → Production Code → GitHub Commits."""

    def __init__(self, project_id: str, event_bus=None):
        super().__init__(
            agent_type="developer_agent",
            project_id=project_id,
            use_flash_llm=False,
            event_bus=event_bus,
        )
        self.github_tool = GitHubTool()
        self.file_tool = FileTool(project_id=project_id)
        self.code_executor = CodeExecutor()

        # Register tools
        self.register_tool("write_file", self.file_tool.write_file)
        self.register_tool("read_file", self.file_tool.read_file)
        self.register_tool("list_files", self.file_tool.list_files)
        self.register_tool("create_github_commit", self.github_tool.create_commit)
        self.register_tool("create_branch", self.github_tool.create_branch)
        self.register_tool("create_pr", self.github_tool.create_pull_request)
        self.register_tool("execute_code", self.code_executor.execute)

    @property
    def system_prompt(self) -> str:
        return DEVELOPER_SYSTEM_PROMPT

    async def execute_task(self, task_data: dict) -> dict:
        """Generate code for a ticket and commit to GitHub."""
        ticket = task_data.get("ticket", {})
        architecture = task_data.get("architecture", "")
        tech_stack = task_data.get("tech_stack", {})
        repo_name = task_data.get("repo_name", "")
        branch = task_data.get("branch", "main")

        self.log.info("Implementing ticket", title=ticket.get("title", "")[:50])

        # Step 1: Generate implementation plan
        plan_prompt = f"""
Implement this ticket:

TICKET: {ticket}
ARCHITECTURE CONTEXT: {architecture[:2000]}
TECH STACK: {tech_stack}

First, create an implementation plan:
1. What files need to be created/modified?
2. What are the key design decisions?
3. What are the dependencies?
4. What tests need to be written?

Return JSON:
{{
  "files_to_create": [
    {{"path": "relative/path/file.py", "purpose": "What this file does"}}
  ],
  "implementation_order": ["file1", "file2"],
  "key_decisions": ["decision 1"],
  "test_files": ["test_file_paths"]
}}
"""
        plan = await self.think_and_parse_json(plan_prompt)

        # Step 2: Generate code for each file
        generated_files = []
        for file_info in plan.get("files_to_create", []):
            file_path = file_info["file_path"] if "file_path" in file_info else file_info.get("path", "")
            file_purpose = file_info.get("purpose", "")

            code_prompt = f"""
Write the complete, production-ready code for this file:

FILE PATH: {file_path}
PURPOSE: {file_purpose}
TICKET: {ticket}
ARCHITECTURE: {architecture[:1500]}
TECH STACK: {tech_stack}

Requirements:
- Complete implementation (no TODOs, no placeholders)
- Proper error handling
- Type hints (if Python)
- Comprehensive docstrings/comments
- Follow the architecture patterns exactly
- Include all necessary imports

Output ONLY the raw code, no explanations.
"""
            code_content = await self.think(code_prompt, temperature=0.3)

            # Write file to project workspace
            await self.call_tool(
                "write_file",
                path=file_path,
                content=code_content,
            )

            generated_files.append({"path": file_path, "content": code_content})
            self.log.info("File generated", path=file_path)

        # Step 3: Generate unit tests
        test_prompt = f"""
Write comprehensive unit tests for the implemented code.

IMPLEMENTED FILES: {[f["path"] for f in generated_files]}
TICKET: {ticket}
TECH STACK: {tech_stack}

Write tests that cover:
- Happy path (normal operation)
- Edge cases (empty input, boundary values)
- Error cases (invalid input, external service failures)
- Integration scenarios

Use appropriate testing framework for the tech stack.
Output ONLY the test code.
"""
        test_code = await self.think(test_prompt, temperature=0.2)

        test_path = f"tests/test_{ticket.get('title', 'feature').lower().replace(' ', '_')[:40]}.py"
        await self.call_tool("write_file", path=test_path, content=test_code)

        # Step 4: Create GitHub commit
        if repo_name:
            commit_files = {f["path"]: f["content"] for f in generated_files}
            commit_files[test_path] = test_code

            commit_msg = (
                f"feat({ticket.get('agent_type', 'dev')}): {ticket.get('title', 'implement feature')[:72]}\n\n"
                f"Implements ticket as per architecture spec.\n"
                f"- Generated by DeveloperAgent\n"
                f"- {len(generated_files)} files modified"
            )

            try:
                await self.call_tool(
                    "create_github_commit",
                    repo_name=repo_name,
                    branch=branch,
                    files=commit_files,
                    message=commit_msg,
                )
                self.log.info("GitHub commit created", repo=repo_name, branch=branch)
            except Exception as e:
                self.log.warning("GitHub commit failed (non-critical)", error=str(e))

        # Step 5: Notify QA and Reviewer
        await self.send_message(
            to_agent="qa_agent",
            message_type="code_ready_for_testing",
            payload={
                "ticket": ticket,
                "files": generated_files,
                "test_file": test_path,
            },
        )

        await self.send_message(
            to_agent="reviewer_agent",
            message_type="code_ready_for_review",
            payload={
                "ticket": ticket,
                "files": generated_files,
            },
        )

        return {
            "success": True,
            "agent_type": self.agent_type,
            "artifacts": {
                "generated_files": generated_files,
                "test_file": test_path,
                "implementation_plan": plan,
            },
            "tokens_used": self.tokens_used,
        }

    async def fix_bug(self, bug_report: dict, code_context: str) -> dict:
        """Fix a reported bug with targeted code changes."""
        prompt = f"""
Fix this bug:
BUG REPORT: {bug_report}
CODE CONTEXT: {code_context[:3000]}

Provide:
1. Root cause analysis
2. Minimal fix (changed lines only)
3. Regression test to prevent recurrence

Return JSON with: root_cause, fix_diff, regression_test
"""
        return await self.think_and_parse_json(prompt)
