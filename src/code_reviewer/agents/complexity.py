"""Complexity review agent — checks cyclomatic complexity, repeated code, dead code."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from code_reviewer.config import DEFAULT_MODEL
from code_reviewer.file_utils import cap_tool_output, get_source_summary, read_file_content
from code_reviewer.models.review import ComplexityReviewResult
from code_reviewer.telemetry import get_tracer

tracer = get_tracer("code-reviewer.complexity")


@dataclass
class ComplexityDeps:
    """Dependencies for the complexity review agent."""
    repo_path: Path


complexity_agent = Agent(
    deps_type=ComplexityDeps,
    output_type=ComplexityReviewResult,
    instructions=(
        "You are a code quality reviewer. Analyze the tool outputs from radon "
        "(cyclomatic complexity) and vulture (dead code detection). "
        "Also review the source summary for repeated/duplicated patterns, "
        "then use read_specific_file to inspect files that look complex or problematic. "
        "Summarize findings into a structured ComplexityReviewResult. "
        "Flag functions with complexity > 10 as HIGH, > 20 as CRITICAL."
    ),
)


@complexity_agent.tool
async def run_complexity_analysis(ctx: RunContext[ComplexityDeps]) -> str:
    """Run radon cyclomatic complexity analysis."""
    with tracer.start_as_current_span(
        "run_radon",
        attributes={"repo.path": str(ctx.deps.repo_path)},
    ):
        try:
            result = subprocess.run(
                ["radon", "cc", str(ctx.deps.repo_path), "-s", "-j"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout or result.stderr or "No complexity data."
            return cap_tool_output(output)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return f"Radon error: {e}"


@complexity_agent.tool
async def run_dead_code_detection(ctx: RunContext[ComplexityDeps]) -> str:
    """Run vulture to find dead/unused code."""
    with tracer.start_as_current_span(
        "run_vulture",
        attributes={"repo.path": str(ctx.deps.repo_path)},
    ):
        try:
            result = subprocess.run(
                ["vulture", str(ctx.deps.repo_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout or result.stderr or "No dead code found."
            return cap_tool_output(output)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return f"Vulture error: {e}"


@complexity_agent.tool
async def read_source_summary(ctx: RunContext[ComplexityDeps]) -> str:
    """Get a summary of all source files with their function/class signatures.
    Use read_specific_file to drill into any file that needs closer inspection."""
    with tracer.start_as_current_span("read_source_summary"):
        return get_source_summary(ctx.deps.repo_path)


@complexity_agent.tool
async def read_specific_file(ctx: RunContext[ComplexityDeps], file_path: str) -> str:
    """Read the full content of a specific source file by its relative path.
    Use this to inspect files that appear complex or duplicated."""
    with tracer.start_as_current_span("read_specific_file"):
        return read_file_content(ctx.deps.repo_path, file_path)


async def run_complexity_review(repo_path: Path) -> ComplexityReviewResult:
    """Execute the complexity review agent."""
    with tracer.start_as_current_span(
        "complexity_review",
        attributes={"repo.path": str(repo_path)},
    ):
        deps = ComplexityDeps(repo_path=repo_path)
        result = await complexity_agent.run(
            "Analyze this repository for code complexity issues. "
            "Run the complexity analysis and dead code detection tools. "
            "Then review the source summary and use read_specific_file "
            "to inspect files that look complex or duplicated.",
            deps=deps,
            model=DEFAULT_MODEL,
        )
        return result.output
