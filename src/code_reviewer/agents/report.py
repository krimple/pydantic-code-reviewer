"""Report agent — synthesizes results from all workstreams into a final report."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext

from code_reviewer.config import DEFAULT_MODEL
from code_reviewer.agent_context import current_agent_id, current_agent_name
from code_reviewer.models.review import (
    ComplexityReviewResult,
    DocumentationReviewResult,
    FinalReport,
    SecurityReviewResult,
)
from code_reviewer.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("code-reviewer.report")


@dataclass
class ReportDeps:
    """Dependencies for the report agent."""

    repo_url: str
    branch: str
    security: SecurityReviewResult
    complexity: ComplexityReviewResult
    documentation: DocumentationReviewResult
    languages: list[str] = field(default_factory=list)


report_agent = Agent(
    name="report_agent",
    deps_type=ReportDeps,
    output_type=FinalReport,
    instructions=(
        "You are a senior code review lead. Synthesize the security, complexity, "
        "and documentation review results into a comprehensive final report. "
        "Provide an overall summary highlighting the most important findings "
        "and an overall risk level. Count total findings across all workstreams. "
        "Always use the get_repo_info tool to populate the repo_url and branch fields."
        "Provide the output in Markdown format."
    ),
)


@report_agent.tool
async def get_repo_info(ctx: RunContext[ReportDeps]) -> str:
    """Get the repository URL, branch, and detected languages."""
    languages = ", ".join(ctx.deps.languages) if ctx.deps.languages else "unknown"
    return (
        f'{{"repo_url": "{ctx.deps.repo_url}", '
        f'"branch": "{ctx.deps.branch}", '
        f'"languages": "{languages}"}}'
    )


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
    languages: list[str] | None = None,
) -> FinalReport:
    """Execute the report generation agent."""
    with tracer.start_as_current_span(
        "report_generation",
        attributes={
            "repo.url": repo_url,
            "repo.branch": branch,
        },
    ):
        logger.info("Starting report generation agent")
        current_agent_id.set("report_agent")
        current_agent_name.set("report_agent")
        deps = ReportDeps(
            repo_url=repo_url,
            branch=branch,
            security=security,
            complexity=complexity,
            documentation=documentation,
            languages=languages or [],
        )
        lang_list = ", ".join(deps.languages) if deps.languages else "unknown"
        prompt = (
            f"Generate a comprehensive final code review report for this {lang_list} repository. "
            "First, use get_repo_info to get the repo_url, branch, and detected languages. "
            "Then retrieve results from all three workstreams using the tools, "
            "and synthesize them into a FinalReport with an overall assessment."
        )

        result = await report_agent.run(prompt, deps=deps, model=DEFAULT_MODEL)
        logger.info("Report generation agent complete")
        return result.output


def _format_report_markdown(report: FinalReport) -> str:
    """Format a FinalReport as Markdown for telemetry output."""
    lines: list[str] = [
        f"# Code Review Report: {report.repo_url}",
        f"**Branch:** {report.branch}",
        f"**Overall Risk Level:** {report.overall_risk_level.value.upper()}",
        f"**Total Findings:** {report.total_findings}",
        "",
        "## Overall Summary",
        report.overall_summary or "_No summary provided._",
        "",
    ]

    for section_title, section in [
        ("Security", report.security),
        ("Complexity", report.complexity),
        ("Documentation", report.documentation),
    ]:
        lines.append(f"## {section_title}")
        lines.append(section.summary or "_No summary._")
        if section.findings:
            lines.append("")
            for f in section.findings:
                loc = ""
                if f.file_path:
                    loc = f" (`{f.file_path}"
                    loc += f":{f.line_number}`)" if f.line_number else "`)"
                lines.append(f"- **[{f.severity.value.upper()}]** {f.title}{loc}")
                lines.append(f"  {f.description}")
                if f.recommendation:
                    lines.append(f"  *Recommendation:* {f.recommendation}")
        lines.append("")

    return "\n".join(lines)
