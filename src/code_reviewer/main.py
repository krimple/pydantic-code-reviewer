"""Main entry point for the code reviewer application."""

from __future__ import annotations

from dotenv import load_dotenv

import asyncio
import json
import logging
import os
import sys


from opentelemetry._logs import get_logger_provider

from code_reviewer.models.review import ReviewRequest
from code_reviewer.pipeline import run_review_pipeline
from code_reviewer.telemetry import setup_telemetry


async def async_main(repo_url: str, branch: str = "main") -> None:
    """Run the code review pipeline and print the report."""
    load_dotenv()
    log_level = os.getenv("LOGLEVEL", "WARNING").upper()
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, log_level))
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(console)
    provider = setup_telemetry()

    try:
        request = ReviewRequest(repo_url=repo_url, branch=branch)
        report = await run_review_pipeline(request)
        print(json.dumps(report.model_dump(), indent=2))
    finally:
        provider.shutdown()
        get_logger_provider().shutdown()


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: code-reviewer <github-repo-url> [branch]")
        print("Example: code-reviewer https://github.com/user/repo main")
        sys.exit(1)

    repo_url = sys.argv[1]
    branch = sys.argv[2] if len(sys.argv) > 2 else "main"

    asyncio.run(async_main(repo_url, branch))


if __name__ == "__main__":
    main()
