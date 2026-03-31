"""Report agent — synthesizes results from all workstreams into a final report."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from code_reviewer.config import DEFAULT_MODEL
from code_reviewer.models.review import (
    ComplexityReviewResult,
    DocumentationReviewResult,
    FinalReport,
    SecurityReviewResult,
)
from code_reviewer.telemetry import get_tracer

tracer = get_tracer("code-reviewer.report")


@dataclass
class ReportDeps:
    """Dependencies for the report agent."""
    repo_url: str
    branch: str
    security: SecurityReviewResult
    complexity: ComplexityReviewResult
    documentation: DocumentationReviewResult


report_agent = Agent(
    deps_type=ReportDeps,
    output_type=FinalReport,
    instructions=(
        "You are a senior code review lead. Synthesize the security, complexity, "
        "and documentation review results into a comprehensive final report. "
        "Provide an overall summary highlighting the most important findings "
        "and an overall risk level. Count total findings across all workstreams. "
        "Always use the get_repo_info tool to populate the repo_url and branch fields."\
        "Provide the output in Markdown format."
    ),
)


@report_agent.tool
async def get_repo_info(ctx: RunContext[ReportDeps]) -> str:
    """Get the repository URL and branch being reviewed."""
    return f'{{"repo_url": "{ctx.deps.repo_url}", "branch": "{ctx.deps.branch}"}}'


@report_agent.tool
async def get_security_results(ctx: RunContext[ReportDeps]) -> str:
    """Get the security review results."""
    return ctx.deps.security.model_dump_json(indent=2)


@report_agent.tool
async def get_complexity_results(ctx: RunContext[ReportDeps]) -> str:
    """Get the complexity review results."""
    return ctx.deps.complexity.model_dump_json(indent=2)


@report_agent.tool
async def get_documentation_results(ctx: RunContext[ReportDeps]) -> str:
    """Get the documentation review results."""
    return ctx.deps.documentation.model_dump_json(indent=2)


async def run_report_generation(
    repo_url: str,
    branch: str,
    security: SecurityReviewResult,
    complexity: ComplexityReviewResult,
    documentation: DocumentationReviewResult,
) -> FinalReport:
    """Execute the report generation agent."""
    with tracer.start_as_current_span(
        "report_generation",
        attributes={"repo.url": repo_url, "repo.branch": branch},
    ):
        deps = ReportDeps(
            repo_url=repo_url,
            branch=branch,
            security=security,
            complexity=complexity,
            documentation=documentation,
        )
        result = await report_agent.run(
            "Generate a comprehensive final code review report. "
            "First, use get_repo_info to get the repo_url and branch. "
            "Then retrieve results from all three workstreams using the tools, "
            "and synthesize them into a FinalReport with an overall assessment.",
            deps=deps,
            model=DEFAULT_MODEL,
        )
        return result.output
