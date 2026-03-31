"""Complexity review agent — checks cyclomatic complexity, repeated code, dead code."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from code_reviewer.config import DEFAULT_MODEL
from code_reviewer.agent_context import current_agent_id, current_agent_name, current_agent_name
from code_reviewer.languages import get_source_files
from code_reviewer.models.review import ComplexityReviewResult
from code_reviewer.telemetry import get_tracer
from code_reviewer.tool_config import (
    COMPLEXITY_TOOLS,
    DEAD_CODE_TOOLS,
    run_tools_for_languages,
)

logger = logging.getLogger(__name__)
tracer = get_tracer("code-reviewer.complexity")


@dataclass
class ComplexityDeps:
    """Dependencies for the complexity review agent."""

    repo_path: Path
    languages: list[str]


complexity_agent = Agent(
    name="complexity_agent",
    deps_type=ComplexityDeps,
    output_type=ComplexityReviewResult,
    instructions=(
        "You are a code quality reviewer. Analyze the tool outputs from "
        "cyclomatic complexity analysis and dead code detection for all detected languages. "
        "If any tool output is prefixed with [TOOL_UNAVAILABLE], perform that analysis "
        "yourself using the provided source code. "
        "Also review source code for repeated/duplicated patterns. "
        "Summarize findings into a structured ComplexityReviewResult. "
        "Flag functions with complexity > 10 as HIGH, > 20 as CRITICAL."
    ),
)


@complexity_agent.tool
async def run_complexity_analysis(ctx: RunContext[ComplexityDeps]) -> str:
    """Run cyclomatic complexity analysis for all detected languages."""
    source_content = _read_source_preview(ctx.deps.repo_path, ctx.deps.languages)
    return await run_tools_for_languages(
        COMPLEXITY_TOOLS,
        ctx.deps.languages,
        ctx.deps.repo_path,
        fallback_context=source_content,
    )


@complexity_agent.tool
async def run_dead_code_detection(ctx: RunContext[ComplexityDeps]) -> str:
    """Run dead code detection for all detected languages."""
    source_content = _read_source_preview(ctx.deps.repo_path, ctx.deps.languages)
    return await run_tools_for_languages(
        DEAD_CODE_TOOLS,
        ctx.deps.languages,
        ctx.deps.repo_path,
        fallback_context=source_content,
    )


@complexity_agent.tool
async def read_source_for_duplication(ctx: RunContext[ComplexityDeps]) -> str:
    """Read source files to check for repeated code patterns."""
    with tracer.start_as_current_span("read_source_for_duplication"):
        return _read_source_preview(ctx.deps.repo_path, ctx.deps.languages)


async def run_complexity_review(repo_path: Path, languages: list[str]) -> ComplexityReviewResult:
    """Execute the complexity review agent."""
    with tracer.start_as_current_span(
        "complexity_review",
        attributes={"repo.path": str(repo_path), "repo.languages": ",".join(languages)},
    ):
        logger.info("Starting complexity review agent for languages: %s", ", ".join(languages))
        current_agent_id.set("complexity_agent")
        current_agent_name.set("complexity_agent")
        deps = ComplexityDeps(repo_path=repo_path, languages=languages)
        lang_list = ", ".join(languages)
        result = await complexity_agent.run(
            f"Analyze this {lang_list} repository for code complexity issues. "
            "Run the complexity analysis and dead code detection tools, "
            "then review source code for duplicated patterns.",
            deps=deps,
            model=DEFAULT_MODEL,
        )
        logger.info("Complexity review agent complete")
        return result.output


def _read_source_preview(repo_path: Path, languages: list[str]) -> str:
    """Read a preview of source files for LLM analysis."""
    files = get_source_files(repo_path, languages, limit=20)
    contents: list[str] = []
    for f in files:
        try:
            text = f.read_text(errors="ignore")[:5000]
            rel = f.relative_to(repo_path)
            contents.append(f"--- {rel} ---\n{text}")
        except Exception:
            continue
    return "\n\n".join(contents) if contents else "No source files found."
