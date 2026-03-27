"""Complexity review agent — checks cyclomatic complexity, repeated code, dead code."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from code_reviewer.config import DEFAULT_MODEL
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
        "Also review source code for repeated/duplicated patterns. "
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
            return result.stdout or result.stderr or "No complexity data."
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
            return result.stdout or result.stderr or "No dead code found."
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return f"Vulture error: {e}"


@complexity_agent.tool
async def read_source_for_duplication(ctx: RunContext[ComplexityDeps]) -> str:
    """Read Python source files to check for repeated code patterns."""
    with tracer.start_as_current_span("read_source_for_duplication"):
        py_files = list(ctx.deps.repo_path.rglob("*.py"))[:20]
        contents = []
        for f in py_files:
            try:
                text = f.read_text(errors="ignore")[:5000]
                rel = f.relative_to(ctx.deps.repo_path)
                contents.append(f"--- {rel} ---\n{text}")
            except Exception:
                continue
        return "\n\n".join(contents) if contents else "No Python files found."


async def run_complexity_review(repo_path: Path) -> ComplexityReviewResult:
    """Execute the complexity review agent."""
    with tracer.start_as_current_span(
        "complexity_review",
        attributes={"repo.path": str(repo_path)},
    ):
        deps = ComplexityDeps(repo_path=repo_path)
        result = await complexity_agent.run(
            "Analyze this repository for code complexity issues. "
            "Run the complexity analysis and dead code detection tools, "
            "then review source code for duplicated patterns.",
            deps=deps,
            model=DEFAULT_MODEL,
        )
        return result.output
