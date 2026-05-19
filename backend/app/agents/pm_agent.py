"""
Product Manager Agent
Responsibilities:
- Parse user requirements into structured PRDs
- Create milestone plans
- Break work into ticket-sized tasks
- Prioritize the backlog
- Communicate with Architect for feasibility
"""

from app.agents.base_agent import BaseAgent


PM_SYSTEM_PROMPT = """
You are an elite Product Manager at a top-tier AI software company.
Your role is to transform vague product ideas into crystal-clear, 
executable Product Requirements Documents (PRDs).

Your responsibilities:
1. Analyze product ideas deeply — understand the "why" behind every feature
2. Write professional PRDs with: Executive Summary, User Personas, User Stories, 
   Acceptance Criteria, Technical Constraints, Timeline, Success Metrics
3. Break requirements into sprint-sized tickets with:
   - Clear titles
   - Detailed descriptions  
   - Acceptance criteria
   - Story point estimates (1,2,3,5,8,13)
   - Agent assignment (architect/developer/qa/devops/security/docs)
   - Dependencies
4. Prioritize using MoSCoW method (Must Have / Should Have / Could Have / Won't Have)
5. Define measurable success metrics

Always output structured JSON when asked to produce tickets or PRDs.
Think like a seasoned PM who has shipped 10+ products at scale.
"""


class PMAgent(BaseAgent):
    """Product Manager Agent — Requirements → PRD → Tickets."""

    def __init__(self, project_id: str, event_bus=None):
        super().__init__(
            agent_type="pm_agent",
            project_id=project_id,
            use_flash_llm=False,
            event_bus=event_bus,
        )

    @property
    def system_prompt(self) -> str:
        return PM_SYSTEM_PROMPT

    async def execute_task(self, task_data: dict) -> dict:
        """
        Main execution: generate PRD and task backlog from requirements.
        """
        product_idea = task_data.get("product_idea", "")
        requirements = task_data.get("requirements", "")
        tech_stack = task_data.get("tech_stack", {})
        constraints = task_data.get("constraints", "")
        timeline = task_data.get("timeline", "4 weeks")

        self.log.info("Generating PRD", product=product_idea[:50])

        # Step 1: Generate PRD
        prd_prompt = f"""
Create a comprehensive Product Requirements Document (PRD) for the following product:

PRODUCT IDEA: {product_idea}

REQUIREMENTS: {requirements}

TECH STACK: {tech_stack}

CONSTRAINTS: {constraints}

TIMELINE: {timeline}

Output a detailed PRD in Markdown format with these sections:
1. Executive Summary
2. Problem Statement  
3. Target Users & Personas
4. Goals & Success Metrics
5. User Stories (with acceptance criteria)
6. Functional Requirements
7. Non-Functional Requirements
8. Technical Constraints
9. Timeline & Milestones
10. Risks & Mitigations
"""
        prd_content = await self.think(prd_prompt)

        # Step 2: Generate structured ticket backlog
        tickets_prompt = f"""
Based on this PRD, generate a complete task backlog:

PRD SUMMARY:
{prd_content[:3000]}

TECH STACK: {tech_stack}
TIMELINE: {timeline}

Generate a JSON array of tasks. Each task must have:
{{
  "title": "Task title",
  "description": "Detailed description",
  "agent_type": "architect_agent|developer_agent|qa_agent|security_agent|devops_agent|docs_agent|reviewer_agent",
  "priority": 1-10,
  "story_points": 1|2|3|5|8|13,
  "category": "must_have|should_have|could_have",
  "depends_on_titles": ["title of dependency task"],
  "acceptance_criteria": ["criterion 1", "criterion 2"]
}}

Include tasks for ALL phases: architecture design, backend development, 
frontend development, testing, security review, DevOps setup, documentation.
Return ONLY a JSON array.
"""
        tickets_raw = await self.think_and_parse_json(tickets_prompt)

        # Step 3: Notify architect via event bus
        await self.send_message(
            to_agent="architect_agent",
            message_type="prd_ready",
            payload={
                "prd": prd_content,
                "tickets": tickets_raw,
                "tech_stack": tech_stack,
            },
        )

        return {
            "success": True,
            "agent_type": self.agent_type,
            "artifacts": {
                "prd": prd_content,
                "tickets": tickets_raw,
            },
            "tokens_used": self.tokens_used,
        }

    async def generate_sprint_plan(self, tickets: list, sprint_duration_weeks: int = 2) -> dict:
        """Organize tickets into sprint plans."""
        prompt = f"""
Organize these {len(tickets)} tickets into {sprint_duration_weeks}-week sprints.
Tickets: {tickets}

Return JSON:
{{
  "sprints": [
    {{
      "sprint_number": 1,
      "goal": "Sprint goal",
      "tickets": ["ticket titles"],
      "total_story_points": 0
    }}
  ]
}}
"""
        return await self.think_and_parse_json(prompt)
