"""
Docker Sandbox Code Executor
Runs untrusted code in isolated Docker containers with:
- Resource limits (CPU, memory)
- Timeout protection
- No network access
- Ephemeral filesystem
- seccomp security profiles
"""

import asyncio
import json
import os
import tempfile
import uuid
from typing import Optional

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class ExecutionResult:
    def __init__(self, stdout: str, stderr: str, exit_code: int, timed_out: bool = False):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.timed_out = timed_out
        self.success = exit_code == 0 and not timed_out

    def to_dict(self) -> dict:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "success": self.success,
        }


class CodeExecutor:
    """
    Docker-based sandboxed code executor.

    Each execution:
    1. Creates a temp directory with the code
    2. Spins up a Docker container with resource limits
    3. Runs the code with timeout
    4. Returns stdout/stderr/exit_code
    5. Cleans up container and files
    """

    LANGUAGE_CONFIGS = {
        "python": {
            "image": "python:3.12-slim",
            "command": ["python", "-u", "main.py"],
            "file_ext": ".py",
            "file_name": "main.py",
        },
        "javascript": {
            "image": "node:20-slim",
            "command": ["node", "main.js"],
            "file_ext": ".js",
            "file_name": "main.js",
        },
        "typescript": {
            "image": "node:20-slim",
            "command": ["npx", "ts-node", "main.ts"],
            "file_ext": ".ts",
            "file_name": "main.ts",
        },
        "bash": {
            "image": "bash:5-alpine",
            "command": ["bash", "main.sh"],
            "file_ext": ".sh",
            "file_name": "main.sh",
        },
    }

    def __init__(self):
        self.timeout = settings.SANDBOX_TIMEOUT
        self.memory_limit = settings.SANDBOX_MEMORY_LIMIT
        self.log = logger.bind(component="CodeExecutor")

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: Optional[int] = None,
        env_vars: Optional[dict] = None,
    ) -> ExecutionResult:
        """
        Execute code in a Docker sandbox.

        Args:
            code: Source code to execute
            language: Programming language
            timeout: Override default timeout (seconds)
            env_vars: Environment variables to pass (must be safe)

        Returns:
            ExecutionResult with stdout, stderr, exit_code
        """
        config = self.LANGUAGE_CONFIGS.get(language)
        if not config:
            return ExecutionResult("", f"Unsupported language: {language}", 1)

        exec_timeout = timeout or self.timeout
        container_id = f"sandbox-{uuid.uuid4().hex[:8]}"

        # Create temp dir for code files
        with tempfile.TemporaryDirectory() as tmp_dir:
            code_file = os.path.join(tmp_dir, config["file_name"])
            with open(code_file, "w", encoding="utf-8") as f:
                f.write(code)

            # Build Docker run command
            docker_cmd = [
                "docker", "run",
                "--name", container_id,
                "--rm",  # Auto-remove after exit
                "--network", "none",  # No network access
                "--memory", self.memory_limit,
                "--memory-swap", self.memory_limit,  # Disable swap
                "--cpus", "0.5",
                "--pids-limit", "50",  # Limit processes
                "--read-only",  # Read-only root filesystem
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
                "--security-opt", "no-new-privileges",
                "-v", f"{tmp_dir}:/workspace:ro",
                "-w", "/workspace",
            ]

            # Add safe env vars
            if env_vars:
                for key, value in env_vars.items():
                    # Only allow alphanumeric keys to prevent injection
                    if key.isidentifier():
                        docker_cmd.extend(["-e", f"{key}={value}"])

            docker_cmd.append(config["image"])
            docker_cmd.extend(config["command"])

            self.log.info("Executing in sandbox",
                          language=language,
                          container=container_id,
                          timeout=exec_timeout)

            try:
                proc = await asyncio.create_subprocess_exec(
                    *docker_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=exec_timeout,
                )
                return ExecutionResult(
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    exit_code=proc.returncode or 0,
                )

            except asyncio.TimeoutError:
                self.log.warning("Sandbox execution timed out", container=container_id)
                # Force kill container
                try:
                    await asyncio.create_subprocess_exec("docker", "kill", container_id)
                except Exception:
                    pass
                return ExecutionResult("", "Execution timed out", -1, timed_out=True)

            except Exception as exc:
                self.log.error("Sandbox execution error", error=str(exc))
                return ExecutionResult("", str(exc), -1)

    async def run_tests(self, test_paths: list, project_dir: str = "/workspace") -> dict:
        """
        Run pytest for a list of test files in the sandbox.

        Returns:
            dict with status, passed, failed, coverage
        """
        test_files_str = " ".join(test_paths)
        pytest_code = f"""
import subprocess, json, sys
result = subprocess.run(
    ["pytest", {test_paths!r}, "-v", "--tb=short", "--json-report", "--json-report-file=/tmp/report.json"],
    capture_output=True, text=True
)
print(result.stdout)
print(result.stderr, file=sys.stderr)
sys.exit(result.returncode)
"""
        exec_result = await self.execute(code=pytest_code, language="python")
        return {
            "status": "passed" if exec_result.success else "failed",
            "stdout": exec_result.stdout,
            "stderr": exec_result.stderr,
            "exit_code": exec_result.exit_code,
        }
