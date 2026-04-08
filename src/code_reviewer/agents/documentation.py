"""Documentation review agent — checks for docs existence and relevance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from code_reviewer.config import DEFAULT_MODEL
from code_reviewer.file_utils import get_source_summary, read_file_content
from code_reviewer.models.review import DocumentationReviewResult
from code_reviewer.telemetry import get_tracer

tracer = get_tracer("code-reviewer.documentation")


@dataclass
class DocsDeps:
    """Dependencies for the documentation review agent."""
    repo_path: Path


documentation_agent = Agent(
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
    """Read the content of documentation files (capped per file to save tokens)."""
    with tracer.start_as_current_span("read_docs"):
        doc_extensions = {".md", ".rst", ".txt"}
        doc_files = []
        for f in ctx.deps.repo_path.rglob("*"):
            if f.is_file() and f.suffix in doc_extensions:
                doc_files.append(f)

        doc_files = doc_files[:10]  # Limit
        contents = []
        for f in doc_files:
            rel = str(f.relative_to(ctx.deps.repo_path))
            contents.append(read_file_content(ctx.deps.repo_path, rel, max_tokens=2000))
        return "\n\n".join(contents) if contents else "No documentation content found."


@documentation_agent.tool
async def read_source_structure(ctx: RunContext[DocsDeps]) -> str:
    """Get a summary of all source files with their function/class signatures.
    Use read_specific_file to drill into any file for detailed doc comparison."""
    with tracer.start_as_current_span("read_source_structure"):
        return get_source_summary(ctx.deps.repo_path)


@documentation_agent.tool
async def read_specific_file(ctx: RunContext[DocsDeps], file_path: str) -> str:
    """Read the full content of a specific file for detailed documentation comparison."""
    with tracer.start_as_current_span("read_specific_file"):
        return read_file_content(ctx.deps.repo_path, file_path)


async def run_documentation_review(repo_path: Path) -> DocumentationReviewResult:
    """Execute the documentation review agent."""
    with tracer.start_as_current_span(
        "documentation_review",
        attributes={"repo.path": str(repo_path)},
    ):
        deps = DocsDeps(repo_path=repo_path)
        result = await documentation_agent.run(
            "Review this repository's documentation. "
            "Find all doc files, read their content, and compare against "
            "the source code structure to assess completeness and relevance.",
            deps=deps,
            model=DEFAULT_MODEL,
        )
        return result.output
