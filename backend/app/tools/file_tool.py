"""
File Tool — manages the project workspace filesystem.
Each project gets an isolated directory under ARTIFACTS_DIR.
"""

import os
import aiofiles
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


class FileTool:
    """
    Safe file I/O tool for agents.
    All paths are sandboxed to the project's workspace directory.
    Path traversal attacks are prevented by resolving and checking the prefix.
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.workspace = os.path.join(settings.ARTIFACTS_DIR, project_id)
        os.makedirs(self.workspace, exist_ok=True)
        self.log = logger.bind(project_id=project_id)

    def _safe_path(self, relative_path: str) -> str:
        """
        Resolve a relative path within the workspace.
        Raises ValueError on path traversal attempts.
        """
        full_path = os.path.realpath(os.path.join(self.workspace, relative_path))
        if not full_path.startswith(os.path.realpath(self.workspace)):
            raise ValueError(f"Path traversal detected: {relative_path}")
        return full_path

    async def write_file(self, path: str, content: str) -> dict:
        """Write content to a file, creating parent directories as needed."""
        safe_path = self._safe_path(path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        async with aiofiles.open(safe_path, "w", encoding="utf-8") as f:
            await f.write(content)
        self.log.debug("File written", path=path, size=len(content))
        return {"success": True, "path": path, "size": len(content)}

    async def read_file(self, path: str) -> str:
        """Read file content."""
        safe_path = self._safe_path(path)
        if not os.path.exists(safe_path):
            return ""
        async with aiofiles.open(safe_path, "r", encoding="utf-8") as f:
            return await f.read()

    async def list_files(self, sub_path: str = "") -> list:
        """List all files in workspace (or sub-directory)."""
        base = self._safe_path(sub_path) if sub_path else self.workspace
        files = []
        for root, dirs, filenames in os.walk(base):
            # Skip hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for filename in filenames:
                full = os.path.join(root, filename)
                rel = os.path.relpath(full, self.workspace)
                files.append({
                    "path": rel,
                    "size": os.path.getsize(full),
                })
        return files

    async def delete_file(self, path: str) -> dict:
        """Delete a file from the workspace."""
        safe_path = self._safe_path(path)
        if os.path.exists(safe_path):
            os.remove(safe_path)
            return {"success": True}
        return {"success": False, "error": "File not found"}

    def get_workspace_path(self) -> str:
        """Return the absolute workspace path for this project."""
        return self.workspace
