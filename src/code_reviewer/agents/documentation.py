"""Documentation review agent — checks for docs existence and relevance."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from code_reviewer.config import DEFAULT_MODEL
from code_reviewer.agent_context import current_agent_id, current_agent_name
from code_reviewer.languages import get_source_files
from code_reviewer.models.review import DocumentationReviewResult
from code_reviewer.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("code-reviewer.documentation")

# Patterns to extract from source code per language
STRUCTURE_PATTERNS: dict[str, tuple[str, ...]] = {
    "python": ("class ", "def ", "async def "),
    "javascript": ("class ", "function ", "export ", "export default ", "module.exports"),
    "go": ("func ", "type ", "package "),
}


@dataclass
class DocsDeps:
    """Dependencies for the documentation review agent."""

    repo_path: Path
    languages: list[str]


documentation_agent = Agent(
    name="documentation_agent",
    deps_type=DocsDeps,
    output_type=DocumentationReviewResult,
    instructions=(
        "You are a documentation reviewer. Analyze the repository's documentation "
        "for completeness and relevance. Check if README, API docs, and contributing "
        "guides exist. Compare documentation against the actual source code to assess "
        "whether the docs accurately describe the current codebase. "
        "Score documentation coverage (0.0-1.0) and relevance (0.0-1.0)."
    ),
)


@documentation_agent.tool
async def find_documentation_files(ctx: RunContext[DocsDeps]) -> str:
    """Find all documentation files in the repository."""
    with tracer.start_as_current_span("find_docs"):
        doc_patterns = [
            "README*", "readme*", "CONTRIBUTING*", "contributing*",
            "CHANGELOG*", "changelog*", "docs/**/*", "doc/**/*",
            "*.md", "*.rst", "*.txt",
        ]
        found = []
        for pattern in doc_patterns:
            for f in ctx.deps.repo_path.rglob(pattern):
                if f.is_file():
                    rel = f.relative_to(ctx.deps.repo_path)
                    found.append(str(rel))

        # Deduplicate
        found = sorted(set(found))
        return "\n".join(found) if found else "No documentation files found."


@documentation_agent.tool
async def read_documentation(ctx: RunContext[DocsDeps]) -> str:
    """Read the content of documentation files."""
    with tracer.start_as_current_span("read_docs"):
        doc_extensions = {".md", ".rst", ".txt"}
        doc_files = []
        for f in ctx.deps.repo_path.rglob("*"):
            if f.is_file() and f.suffix in doc_extensions:
                doc_files.append(f)

        doc_files = doc_files[:15]  # Limit
        contents = []
        for f in doc_files:
            try:
                text = f.read_text(errors="ignore")[:8000]
                rel = f.relative_to(ctx.deps.repo_path)
                contents.append(f"--- {rel} ---\n{text}")
            except Exception:
                continue
        return "\n\n".join(contents) if contents else "No documentation content found."


@documentation_agent.tool
async def read_source_structure(ctx: RunContext[DocsDeps]) -> str:
    """Read source code structure to compare against documentation."""
    with tracer.start_as_current_span("read_source_structure"):
        files = get_source_files(ctx.deps.repo_path, ctx.deps.languages, limit=30)
        structure = []

        # Build combined patterns for all detected languages
        patterns: tuple[str, ...] = ()
        for lang in ctx.deps.languages:
            patterns = patterns + STRUCTURE_PATTERNS.get(lang, ())

        for f in files:
            rel = f.relative_to(ctx.deps.repo_path)
            try:
                text = f.read_text(errors="ignore")
                lines = [
                    line.strip()
                    for line in text.splitlines()
                    if line.strip().startswith(patterns)
                ] if patterns else []
                structure.append(f"{rel}: {', '.join(lines[:10])}")
            except Exception:
                structure.append(str(rel))
        return "\n".join(structure) if structure else "No source files found."


async def run_documentation_review(repo_path: Path, languages: list[str]) -> DocumentationReviewResult:
    """Execute the documentation review agent."""
    with tracer.start_as_current_span(
        "documentation_review",
        attributes={"repo.path": str(repo_path), "repo.languages": ",".join(languages)},
    ):
        logger.info("Starting documentation review agent for languages: %s", ", ".join(languages))
        current_agent_id.set("documentation_agent")
        current_agent_name.set("documentation_agent")
        deps = DocsDeps(repo_path=repo_path, languages=languages)
        lang_list = ", ".join(languages)
        result = await documentation_agent.run(
            f"Review this {lang_list} repository's documentation. "
            "Find all doc files, read their content, and compare against "
            "the source code structure to assess completeness and relevance.",
            deps=deps,
            model=DEFAULT_MODEL,
        )
        logger.info("Documentation review agent complete")
        return result.output
