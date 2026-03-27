"""Repository cloning and management."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from git import Repo

from code_reviewer.telemetry import get_tracer

tracer = get_tracer("code-reviewer.repo")


def clone_repo(repo_url: str, branch: str = "main") -> Path:
    """Clone a GitHub repository to a temporary directory.

    Returns the path to the cloned repository.
    """
    with tracer.start_as_current_span(
        "clone_repository",
        attributes={"repo.url": repo_url, "repo.branch": branch},
    ):
        clone_dir = Path(tempfile.mkdtemp(prefix="code-review-"))
        Repo.clone_from(repo_url, str(clone_dir), branch=branch)
        return clone_dir


def cleanup_repo(repo_path: Path) -> None:
    """Remove a cloned repository directory."""
    if repo_path.exists():
        shutil.rmtree(repo_path)
