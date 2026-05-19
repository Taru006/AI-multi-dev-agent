"""
Security Engineer Agent
Responsibilities:
- OWASP Top 10 vulnerability detection
- Dependency vulnerability scanning
- Static Application Security Testing (SAST)
- Security best practices enforcement
- Generate security reports with remediation steps
"""

from app.agents.base_agent import BaseAgent
from app.tools.file_tool import FileTool
from app.tools.code_executor import CodeExecutor


SECURITY_SYSTEM_PROMPT = """
You are a Principal Application Security Engineer (AppSec) with deep expertise in:
- OWASP Top 10 vulnerabilities
- SANS Top 25 Most Dangerous Software Errors  
- CWE/CVE vulnerability databases
- Threat modeling (STRIDE methodology)
- Penetration testing
- Secure code review

Your security analysis covers:
1. INJECTION: SQL injection, command injection, LDAP injection, XPath injection
2. BROKEN AUTH: Weak passwords, session fixation, JWT vulnerabilities
3. SENSITIVE DATA: Unencrypted PII, weak crypto, cleartext secrets
4. XXE: XML External Entity attacks
5. BROKEN ACCESS CONTROL: IDOR, privilege escalation, missing authorization
6. SECURITY MISCONFIGURATION: Default credentials, verbose errors, open ports
7. XSS: Reflected, stored, DOM-based cross-site scripting
8. INSECURE DESERIALIZATION: Object injection, pickle exploits
9. COMPONENTS WITH VULNERABILITIES: Outdated dependencies, known CVEs
10. INSUFFICIENT LOGGING: Missing audit trails, blind to attacks

You think like an attacker to defend like a defender.
Always provide CVSS scores (0-10) and remediation priority.
Your reports are clear enough for developers to act on immediately.
"""


class SecurityAgent(BaseAgent):
    """Security Agent — Code → Vulnerability Analysis → Security Report."""

    def __init__(self, project_id: str, event_bus=None):
        super().__init__(
            agent_type="security_agent",
            project_id=project_id,
            use_flash_llm=False,
            event_bus=event_bus,
        )
        self.file_tool = FileTool(project_id=project_id)
        self.code_executor = CodeExecutor()
        self.register_tool("read_file", self.file_tool.read_file)
        self.register_tool("execute", self.code_executor.execute)

    @property
    def system_prompt(self) -> str:
        return SECURITY_SYSTEM_PROMPT

    async def execute_task(self, task_data: dict) -> dict:
        """Perform full security analysis on submitted code."""
        files = task_data.get("files", [])
        tech_stack = task_data.get("tech_stack", {})
        ticket = task_data.get("ticket", {})

        self.log.info("Starting security analysis", file_count=len(files))

        all_vulnerabilities = []
        security_reports = []

        for file_info in files:
            file_path = file_info.get("path", "")
            file_content = file_info.get("content", "")

            if not file_content or file_path.endswith((".md", ".txt", ".json", ".yaml", ".yml")):
                continue

            scan_prompt = f"""
Perform a comprehensive security code review on this file.

FILE: {file_path}
CODE:
```
{file_content[:4000]}
```

TECH STACK: {tech_stack}

Analyze for ALL of these:
1. Injection vulnerabilities (SQL, command, LDAP)
2. Authentication/authorization issues
3. Sensitive data exposure (secrets, PII, weak crypto)
4. Broken access control
5. Security misconfiguration
6. XSS vulnerabilities
7. Insecure deserialization
8. Hardcoded credentials or API keys
9. Insufficient input validation
10. Race conditions or TOCTOU vulnerabilities

Return JSON:
{{
  "file": "{file_path}",
  "vulnerabilities": [
    {{
      "id": "VULN-001",
      "type": "OWASP category",
      "severity": "critical|high|medium|low|info",
      "cvss_score": 0.0,
      "line_numbers": [10, 15],
      "description": "Detailed description",
      "vulnerable_code": "the problematic code snippet",
      "remediation": "How to fix it",
      "fixed_code": "The corrected code snippet",
      "cwe_id": "CWE-89"
    }}
  ],
  "security_score": 0-100,
  "summary": "Overall assessment"
}}
"""
            file_report = await self.think_and_parse_json(scan_prompt)
            security_reports.append(file_report)
            all_vulnerabilities.extend(file_report.get("vulnerabilities", []))

        # Dependency scan
        deps_prompt = f"""
Analyze the dependencies in this tech stack for known vulnerabilities:
TECH STACK: {tech_stack}

Identify:
1. Packages with known CVEs
2. Outdated versions
3. Packages with poor security track records
4. Transitive dependency risks

Return JSON: {{
  "vulnerable_packages": [{{"package": "name", "version": "x.y.z", "cve": "CVE-XXXX", "severity": "...", "upgrade_to": "..."}}],
  "recommendations": ["recommendation 1"]
}}
"""
        dep_scan = await self.think_and_parse_json(deps_prompt)

        # Generate overall security report
        critical_count = sum(1 for v in all_vulnerabilities if v.get("severity") == "critical")
        high_count = sum(1 for v in all_vulnerabilities if v.get("severity") == "high")

        # Notify DevOps if critical issues found
        if critical_count > 0:
            await self.send_message(
                to_agent="devops_agent",
                message_type="security_critical_found",
                payload={
                    "critical_count": critical_count,
                    "vulnerabilities": [v for v in all_vulnerabilities if v.get("severity") == "critical"],
                },
                requires_approval=True,
            )

        # Notify developer to fix issues
        if all_vulnerabilities:
            await self.send_message(
                to_agent="developer_agent",
                message_type="security_issues",
                payload={
                    "vulnerabilities": all_vulnerabilities,
                    "ticket": ticket,
                },
            )

        return {
            "success": True,
            "agent_type": self.agent_type,
            "artifacts": {
                "security_reports": security_reports,
                "dependency_scan": dep_scan,
                "summary": {
                    "total_vulnerabilities": len(all_vulnerabilities),
                    "critical": critical_count,
                    "high": high_count,
                    "medium": sum(1 for v in all_vulnerabilities if v.get("severity") == "medium"),
                    "low": sum(1 for v in all_vulnerabilities if v.get("severity") == "low"),
                },
            },
            "tokens_used": self.tokens_used,
        }

    async def generate_threat_model(self, architecture: str) -> dict:
        """STRIDE threat modeling for the system architecture."""
        prompt = f"""
Perform STRIDE threat modeling for this architecture:

{architecture[:3000]}

For each component, identify:
- Spoofing threats
- Tampering threats  
- Repudiation threats
- Information Disclosure threats
- Denial of Service threats
- Elevation of Privilege threats

Return JSON with threats, mitigations, and priority matrix.
"""
        return await self.think_and_parse_json(prompt)
