"""
QA / Test Engineer Agent
Responsibilities:
- Generate comprehensive test suites
- Detect bugs via static analysis
- Run automated tests in sandbox
- Report coverage and quality metrics
- Create test plans and regression suites
"""

from app.agents.base_agent import BaseAgent
from app.tools.code_executor import CodeExecutor
from app.tools.file_tool import FileTool


QA_SYSTEM_PROMPT = """
You are a Principal QA Engineer and Test Architect at a top tech company.
You ensure software quality through rigorous, systematic testing.

Your testing philosophy:
1. Test the behavior, not the implementation
2. Prioritize edge cases and failure modes
3. Think like an adversary — try to break the code
4. Tests should be fast, isolated, reliable, and meaningful

Testing strategies you employ:
- Unit tests (pure function behavior)
- Integration tests (component interaction)
- End-to-end tests (full user flows)
- Property-based testing (fuzzing)
- Contract testing (API compatibility)
- Performance/load testing scenarios
- Security-focused tests (auth bypass, injection attempts)

Tools you use:
- Python: pytest, pytest-asyncio, hypothesis, coverage
- JavaScript: Jest, Playwright, Cypress
- API: pytest + httpx, Postman collections
- Performance: locust scripts

When generating test cases:
- Cover: happy path, edge cases, error conditions, concurrent access
- Use meaningful test names that describe behavior: test_user_cannot_login_with_wrong_password
- Ensure tests are deterministic (no random data without seeding)
- Mock external services properly
"""


class QAAgent(BaseAgent):
    """QA Agent — Code → Comprehensive Tests → Bug Reports."""

    def __init__(self, project_id: str, event_bus=None):
        super().__init__(
            agent_type="qa_agent",
            project_id=project_id,
            use_flash_llm=False,
            event_bus=event_bus,
        )
        self.code_executor = CodeExecutor()
        self.file_tool = FileTool(project_id=project_id)

        self.register_tool("run_tests", self.code_executor.run_tests)
        self.register_tool("read_file", self.file_tool.read_file)
        self.register_tool("write_file", self.file_tool.write_file)

    @property
    def system_prompt(self) -> str:
        return QA_SYSTEM_PROMPT

    async def execute_task(self, task_data: dict) -> dict:
        """Generate and run tests for implemented code."""
        ticket = task_data.get("ticket", {})
        files = task_data.get("files", [])
        tech_stack = task_data.get("tech_stack", {})

        self.log.info("Running QA process", ticket=ticket.get("title", "")[:50])

        # Step 1: Generate comprehensive test plan
        test_plan_prompt = f"""
Create a comprehensive test plan for:

TICKET: {ticket}
FILES IMPLEMENTED: {[f.get("path") for f in files]}
TECH STACK: {tech_stack}

Return JSON:
{{
  "test_plan": {{
    "scope": "what is being tested",
    "strategy": "unit|integration|e2e mix",
    "risk_areas": ["high-risk areas to focus on"]
  }},
  "test_cases": [
    {{
      "name": "test_something_specific",
      "type": "unit|integration|e2e",
      "scenario": "Given X, When Y, Then Z",
      "inputs": {{}},
      "expected_output": "description",
      "priority": "high|medium|low"
    }}
  ]
}}
"""
        test_plan = await self.think_and_parse_json(test_plan_prompt)

        # Step 2: Generate test code
        all_test_code = []
        for file_info in files:
            file_path = file_info.get("path", "")
            file_content = file_info.get("content", "")

            test_prompt = f"""
Write a comprehensive pytest test suite for this file.

FILE: {file_path}
CODE:
```
{file_content[:3000]}
```

TEST PLAN: {test_plan}

Requirements:
- Use pytest and pytest-asyncio for async code
- Mock all external dependencies (DB, APIs, Redis) properly
- Test cases from the test plan above
- Use fixtures for setup/teardown
- Include parametrize decorators for multiple scenarios
- Measure and assert specific behaviors, not implementation details
- 80%+ code coverage target

Output ONLY the test code.
"""
            test_code = await self.think(test_prompt, temperature=0.2)
            test_file_path = f"tests/test_{file_path.replace('/', '_').replace('.py', '')}.py"

            await self.call_tool("write_file", path=test_file_path, content=test_code)
            all_test_code.append({"path": test_file_path, "content": test_code})

        # Step 3: Try running tests in sandbox
        test_results = {"status": "not_run", "details": "Sandbox execution skipped"}
        try:
            test_results = await self.call_tool(
                "run_tests",
                test_paths=[t["path"] for t in all_test_code],
            )
        except Exception as e:
            self.log.warning("Test execution failed", error=str(e))
            test_results = {"status": "execution_error", "error": str(e)}

        # Step 4: Analyze results and detect bugs
        if test_results.get("status") == "failed":
            bug_prompt = f"""
Analyze these test failures and identify bugs:

TEST RESULTS: {test_results}
CODE FILES: {[f.get("path") for f in files]}

For each failure, provide:
1. Root cause
2. Severity (critical/high/medium/low)
3. Suggested fix
4. Regression risk

Return JSON: {{"bugs": [{{"id": "BUG-001", "title": "...", "severity": "...", "root_cause": "...", "suggested_fix": "..."}}]}}
"""
            bug_report = await self.think_and_parse_json(bug_prompt)

            await self.send_message(
                to_agent="developer_agent",
                message_type="bug_report",
                payload={"bugs": bug_report.get("bugs", []), "ticket": ticket},
            )
        else:
            bug_report = {"bugs": []}

        # Step 5: Notify Security Agent
        await self.send_message(
            to_agent="security_agent",
            message_type="ready_for_security_scan",
            payload={"files": files, "ticket": ticket},
        )

        return {
            "success": True,
            "agent_type": self.agent_type,
            "artifacts": {
                "test_plan": test_plan,
                "test_files": all_test_code,
                "test_results": test_results,
                "bug_report": bug_report,
            },
            "tokens_used": self.tokens_used,
        }

    async def generate_load_test(self, api_endpoints: list) -> str:
        """Generate a Locust load test script."""
        prompt = f"""
Write a Locust load test script for these API endpoints:
{api_endpoints}

Include:
- Realistic user flows
- Think time between requests
- Proper authentication headers
- Multiple user scenarios

Output only the Python Locust script.
"""
        return await self.think(prompt, temperature=0.2)
