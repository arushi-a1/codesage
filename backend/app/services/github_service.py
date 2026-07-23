"""GitHub interactions: cloning repositories for indexing and fetching PR
diffs for review. Uses GitPython for cloning (shallow clone for speed) and
httpx against the REST API for PR metadata/diffs.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional

import git
import httpx

from app.core.config import get_settings

settings = get_settings()

GITHUB_URL_RE = re.compile(
    r"github\.com[/:]([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$"
)


class GitHubError(Exception):
    pass


def parse_repo_full_name(github_url: str) -> str:
    match = GITHUB_URL_RE.search(github_url.strip())
    if not match:
        raise GitHubError(f"Could not parse a GitHub owner/repo from: {github_url}")
    owner, repo = match.groups()
    return f"{owner}/{repo}"


def clone_repository(github_url: str, dest_dir: str, branch: Optional[str] = None) -> str:
    """Shallow-clones the repo into dest_dir. Returns the local path.
    Overwrites any existing clone at that path (used for re-index)."""
    dest = Path(dest_dir)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    clone_url = github_url
    if settings.github_token and "github.com" in github_url:
        clone_url = github_url.replace(
            "https://github.com", f"https://x-access-token:{settings.github_token}@github.com"
        )

    kwargs = {"depth": 1}
    if branch:
        kwargs["branch"] = branch

    try:
        git.Repo.clone_from(clone_url, dest, **kwargs)
    except git.exc.GitCommandError as exc:
        raise GitHubError(f"git clone failed: {exc}") from exc

    return str(dest)


def iter_source_files(local_path: str, max_file_size_kb: int):
    """Yields (relative_path, absolute_path) for files worth indexing,
    skipping VCS metadata, dependency directories, and binaries."""
    ignored_dirs = {
        ".git", "node_modules", "venv", ".venv", "__pycache__", "dist",
        "build", "target", ".next", "vendor", "coverage", ".mypy_cache",
        ".pytest_cache", "site-packages",
    }
    root = Path(local_path)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignored_dirs for part in path.parts):
            continue
        try:
            if path.stat().st_size > max_file_size_kb * 1024:
                continue
        except OSError:
            continue
        yield str(path.relative_to(root)), str(path)


class GitHubAPIClient:
    """Thin wrapper over the REST API for PR review support."""

    def __init__(self, token: str = ""):
        self.token = token or settings.github_token
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._client = httpx.AsyncClient(base_url="https://api.github.com", headers=headers, timeout=30.0)

    async def get_pull_request(self, full_name: str, pr_number: int) -> dict:
        resp = await self._client.get(f"/repos/{full_name}/pulls/{pr_number}")
        resp.raise_for_status()
        return resp.json()

    async def get_pull_request_diff(self, full_name: str, pr_number: int) -> str:
        headers = {"Accept": "application/vnd.github.diff"}
        resp = await self._client.get(
            f"/repos/{full_name}/pulls/{pr_number}", headers=headers
        )
        resp.raise_for_status()
        return resp.text

    async def get_pull_request_files(self, full_name: str, pr_number: int) -> list[dict]:
        resp = await self._client.get(f"/repos/{full_name}/pulls/{pr_number}/files")
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()
