import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import subprocess

app = FastAPI(title="Sandbox RPC Runner")

class CommandRequest(BaseModel):
    command: str
    cwd: str = "/workspace"
    timeout: int = 60

class CommandResponse(BaseModel):
    stdout: str
    stderr: str
    returncode: int

@app.post("/execute", response_model=CommandResponse)
async def execute_command(req: CommandRequest):
    """Executes a command safely inside the sandbox."""
    if not os.path.exists(req.cwd):
        try:
            os.makedirs(req.cwd, exist_ok=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to create directory: {e}")

    try:
        # We use asyncio.create_subprocess_shell for async non-blocking execution
        process = await asyncio.create_subprocess_shell(
            req.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=req.cwd
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=req.timeout)
            return CommandResponse(
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                returncode=process.returncode or 0
            )
        except asyncio.TimeoutError:
            process.kill()
            return CommandResponse(
                stdout="",
                stderr=f"Command timed out after {req.timeout} seconds",
                returncode=-1
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}
