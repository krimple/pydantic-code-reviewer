"""Orchestration pipeline — runs review workstreams and generates final report."""

from __future__ import annotations

import asyncio

from code_reviewer.agents.complexity import run_complexity_review
from code_reviewer.agents.documentation import run_documentation_review
from code_reviewer.agents.report import run_report_generation
from code_reviewer.agents.security import run_security_review
from code_reviewer.models.review import FinalReport, ReviewRequest
from code_reviewer.repo import cleanup_repo, clone_repo
from code_reviewer.telemetry import agent_status_logging_enabled, get_tracer, log_prompts_enabled

tracer = get_tracer("code-reviewer.pipeline")


def _log_status(span, status: str) -> None:
    """Log agent status as a span event if enabled."""
    if agent_status_logging_enabled():
        span.add_event("agent.status", {"status": status})


async def run_review_pipeline(request: ReviewRequest) -> FinalReport:
    """Run the full code review pipeline.

    1. Clone the repository
    2. Run three review workstreams in parallel
    3. Generate a final report from the combined results
    4. Clean up the cloned repository
    """
    with tracer.start_as_current_span(
        "review_pipeline",
        attributes={
            "repo.url": request.repo_url,
            "repo.branch": request.branch,
        },
    ) as span:
        if log_prompts_enabled():
            span.add_event("user.prompt", {"repo_url": request.repo_url, "branch": request.branch})

        # Step 1: Clone
        _log_status(span, "cloning")
        repo_path = clone_repo(request.repo_url, request.branch)
        span.set_attribute("repo.local_path", str(repo_path))

        try:
            # Step 2: Run all three workstreams in parallel
            _log_status(span, "reviewing")
            with tracer.start_as_current_span("parallel_reviews"):
                security_result, complexity_result, docs_result = await asyncio.gather(
                    run_security_review(repo_path),
                    run_complexity_review(repo_path),
                    run_documentation_review(repo_path),
                )

            # Step 3: Generate final report
            _log_status(span, "generating_report")
            report = await run_report_generation(
                repo_url=request.repo_url,
                branch=request.branch,
                security=security_result,
                complexity=complexity_result,
                documentation=docs_result,
            )

            span.set_attribute("report.total_findings", report.total_findings)
            span.set_attribute("report.risk_level", report.overall_risk_level.value)

            return report

        finally:
            # Step 4: Cleanup
            cleanup_repo(repo_path)
