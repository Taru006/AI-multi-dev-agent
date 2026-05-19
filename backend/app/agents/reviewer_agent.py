"""
Code Reviewer Agent
Responsibilities:
- Review PRs for code quality, patterns, and standards
- Detect anti-patterns and code smells
- Suggest performance optimizations
- Enforce architectural consistency
- Provide scored, actionable feedback
"""

from app.agents.base_agent import BaseAgent
from app.tools.file_tool import FileTool
from app.tools.github_tool import GitHubTool


REVIEWER_SYSTEM_PROMPT = """
You are a Staff Engineer performing code reviews at a top tech company.
You've reviewed thousands of PRs and built deep pattern recognition for quality code.

Your code review focuses on:
1. CORRECTNESS: Logic errors, off-by-one errors, null pointer risks
2. DESIGN: SOLID principles, separation of concerns, inappropriate coupling
3. READABILITY: Naming clarity, function length, comment quality
4. PERFORMANCE: N+1 queries, unnecessary iterations, memory leaks
5. SECURITY: Input validation, auth checks, injection risks
6. TESTABILITY: Can this be easily tested? Are tests present?
7. MAINTAINABILITY: Will this be easy to change in 6 months?
8. CONSISTENCY: Does this follow existing patterns in the codebase?

Anti-patterns you actively catch:
- God classes/functions (do too much)
- Magic numbers/strings (use constants)
- Mutable default arguments in Python
- Missing error handling
- Synchronous calls in async contexts
- Missing database transactions
- Logging sensitive data
- Overly complex nested logic

Your feedback style:
- Be constructive and specific
- Provide examples of better approaches
- Categorize: MUST_FIX | SHOULD_FIX | SUGGESTION | PRAISE
- Focus on the most impactful issues first
- Recognize and praise good code
"""


class ReviewerAgent(BaseAgent):
    """Code Reviewer Agent — Code → Quality Analysis → PR Review Comments."""

    def __init__(self, project_id: str, event_bus=None):
        super().__init__(
            agent_type="reviewer_agent",
            project_id=project_id,
            use_flash_llm=False,
            event_bus=event_bus,
        )
        self.file_tool = FileTool(project_id=project_id)
        self.github_tool = GitHubTool()
        self.register_tool("read_file", self.file_tool.read_file)
        self.register_tool("add_pr_comment", self.github_tool.add_pr_comment)

    @property
    def system_prompt(self) -> str:
        return REVIEWER_SYSTEM_PROMPT

    async def execute_task(self, task_data: dict) -> dict:
        """Perform comprehensive code review."""
        files = task_data.get("files", [])
        ticket = task_data.get("ticket", {})
        pr_number = task_data.get("pr_number")
        repo_name = task_data.get("repo_name", "")

        self.log.info("Starting code review", file_count=len(files))

        all_comments = []
        overall_score = 100  # Start at 100, deduct for issues

        for file_info in files:
            file_path = file_info.get("path", "")
            file_content = file_info.get("content", "")

            if not file_content:
                continue

            review_prompt = f"""
Perform a thorough code review of this file:

FILE: {file_path}
CODE:
```
{file_content[:4000]}
```

TICKET CONTEXT: {ticket}

Review for:
1. Correctness (logic bugs, edge cases)
2. Design patterns and SOLID principles
3. Performance issues
4. Security vulnerabilities (basic check)
5. Readability and naming
6. Test coverage considerations
7. Missing error handling
8. Anti-patterns

Return JSON:
{{
  "file": "{file_path}",
  "overall_score": 0-100,
  "review_comments": [
    {{
      "category": "MUST_FIX|SHOULD_FIX|SUGGESTION|PRAISE",
      "line_number": 42,
      "issue": "description of issue",
      "suggestion": "how to fix it",
      "code_example": "better code snippet",
      "impact": "high|medium|low"
    }}
  ],
  "summary": "Overall review summary",
  "approved": true|false
}}
"""
            review = await self.think_and_parse_json(review_prompt)
            all_comments.append(review)

            # Track quality score
            file_score = review.get("overall_score", 80)
            overall_score = min(overall_score, file_score)

            # Post to GitHub PR if available
            if pr_number and repo_name:
                for comment in review.get("review_comments", [])[:5]:  # Limit to 5 per file
                    try:
                        await self.call_tool(
                            "add_pr_comment",
                            repo_name=repo_name,
                            pr_number=pr_number,
                            body=f"**[{comment['category']}]** Line {comment.get('line_number', '?')}\n\n{comment['issue']}\n\n**Suggestion:** {comment['suggestion']}",
                            path=file_path,
                            line=comment.get("line_number"),
                        )
                    except Exception as e:
                        self.log.warning("Failed to post PR comment", error=str(e))

        # Determine if approved
        must_fix_count = sum(
            1 for review in all_comments
            for c in review.get("review_comments", [])
            if c.get("category") == "MUST_FIX"
        )
        approved = must_fix_count == 0 and overall_score >= 70

        if not approved:
            await self.send_message(
                to_agent="developer_agent",
                message_type="review_changes_requested",
                payload={
                    "ticket": ticket,
                    "must_fix_comments": [
                        c for review in all_comments
                        for c in review.get("review_comments", [])
                        if c.get("category") == "MUST_FIX"
                    ],
                    "overall_score": overall_score,
                },
            )

        return {
            "success": True,
            "agent_type": self.agent_type,
            "artifacts": {
                "review_comments": all_comments,
                "overall_score": overall_score,
                "approved": approved,
                "must_fix_count": must_fix_count,
            },
            "tokens_used": self.tokens_used,
        }
