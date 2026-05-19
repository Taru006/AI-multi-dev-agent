"""
GitHub Integration Tool
Handles: repo creation, branch management, commits, PRs, issues, code reviews.
"""

import base64
from typing import Optional
import structlog
from github import Github, GithubException
from github.Repository import Repository

from app.config import settings

logger = structlog.get_logger(__name__)


class GitHubTool:
    """
    GitHub API wrapper for agent-driven repository operations.
    Requires GITHUB_TOKEN env variable.
    """

    def __init__(self):
        if settings.GITHUB_TOKEN:
            self._gh = Github(settings.GITHUB_TOKEN)
            self._user = self._gh.get_user()
        else:
            self._gh = None
            self._user = None
        self.log = logger.bind(component="GitHubTool")

    def _get_repo(self, repo_name: str) -> Repository:
        """Get repository object."""
        if not self._gh:
            raise RuntimeError("GitHub token not configured")
        return self._gh.get_repo(repo_name)

    async def create_repository(
        self,
        name: str,
        description: str = "",
        private: bool = True,
    ) -> dict:
        """Create a new GitHub repository."""
        if not self._user:
            return {"error": "GitHub not configured", "url": ""}
        try:
            repo = self._user.create_repo(
                name=name,
                description=description,
                private=private,
                auto_init=True,
            )
            self.log.info("Repo created", url=repo.html_url)
            return {"url": repo.html_url, "name": repo.full_name, "success": True}
        except GithubException as e:
            self.log.error("Repo creation failed", error=str(e))
            return {"error": str(e), "success": False}

    async def create_branch(
        self,
        repo_name: str,
        branch_name: str,
        from_branch: str = "main",
    ) -> dict:
        """Create a new branch from base."""
        try:
            repo = self._get_repo(repo_name)
            source = repo.get_branch(from_branch)
            repo.create_git_ref(f"refs/heads/{branch_name}", source.commit.sha)
            self.log.info("Branch created", branch=branch_name)
            return {"success": True, "branch": branch_name}
        except GithubException as e:
            return {"success": False, "error": str(e)}

    async def create_commit(
        self,
        repo_name: str,
        branch: str,
        files: dict,  # {path: content}
        message: str,
    ) -> dict:
        """
        Create or update multiple files in a single commit.

        Args:
            repo_name: Full repo name (owner/repo)
            branch: Target branch
            files: Dict mapping file paths to content
            message: Commit message
        """
        try:
            repo = self._get_repo(repo_name)
            results = []

            for file_path, content in files.items():
                try:
                    # Try to get existing file (for update)
                    existing = repo.get_contents(file_path, ref=branch)
                    repo.update_file(
                        file_path,
                        message,
                        content,
                        existing.sha,
                        branch=branch,
                    )
                except GithubException:
                    # File doesn't exist — create it
                    repo.create_file(file_path, message, content, branch=branch)
                results.append(file_path)

            self.log.info("Commit created", files=len(results), branch=branch)
            return {"success": True, "files_committed": results, "branch": branch}

        except GithubException as e:
            self.log.error("Commit failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def create_pull_request(
        self,
        repo_name: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        draft: bool = False,
    ) -> dict:
        """Create a pull request."""
        try:
            repo = self._get_repo(repo_name)
            pr = repo.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base_branch,
                draft=draft,
            )
            self.log.info("PR created", number=pr.number, url=pr.html_url)
            return {"success": True, "pr_number": pr.number, "url": pr.html_url}
        except GithubException as e:
            return {"success": False, "error": str(e)}

    async def add_pr_comment(
        self,
        repo_name: str,
        pr_number: int,
        body: str,
        path: Optional[str] = None,
        line: Optional[int] = None,
    ) -> dict:
        """Add a review comment to a PR."""
        try:
            repo = self._get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(body)
            return {"success": True}
        except GithubException as e:
            return {"success": False, "error": str(e)}

    async def create_issue(
        self,
        repo_name: str,
        title: str,
        body: str,
        labels: list = None,
    ) -> dict:
        """Create a GitHub issue."""
        try:
            repo = self._get_repo(repo_name)
            issue = repo.create_issue(
                title=title,
                body=body,
                labels=labels or [],
            )
            return {"success": True, "issue_number": issue.number, "url": issue.html_url}
        except GithubException as e:
            return {"success": False, "error": str(e)}
