"""Tool configuration for multi-language analysis — specs and LLM fallback."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from code_reviewer.languages import tool_available
from code_reviewer.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer("code-reviewer.tools")


@dataclass
class ToolSpec:
    """Specification for an external analysis tool."""

    name: str
    cmd: list[str]
    run_in_repo: bool = False
    timeout: int = 120
    description: str = ""


# --- Security tools per language ---

SECURITY_TOOLS: dict[str, list[ToolSpec]] = {
    "python": [
        ToolSpec(
            name="bandit",
            cmd=["bandit", "-r", "{repo_path}", "-f", "json", "-q"],
            description="Python static security analysis",
        ),
    ],
    "javascript": [],  # LLM fallback — no good single CLI tool without project-specific config
    "go": [
        ToolSpec(
            name="gosec",
            cmd=["gosec", "-fmt=json", "./..."],
            run_in_repo=True,
            description="Go static security analysis",
        ),
    ],
}

DEPENDENCY_AUDIT_TOOLS: dict[str, list[ToolSpec]] = {
    "python": [
        ToolSpec(
            name="pip-audit",
            cmd=["pip-audit", "-f", "json"],
            run_in_repo=True,
            description="Python dependency vulnerability check",
        ),
    ],
    "javascript": [
        ToolSpec(
            name="npm",
            cmd=["npm", "audit", "--json"],
            run_in_repo=True,
            description="Node.js dependency vulnerability check",
        ),
    ],
    "go": [
        ToolSpec(
            name="govulncheck",
            cmd=["govulncheck", "./..."],
            run_in_repo=True,
            description="Go dependency vulnerability check",
        ),
    ],
}

# --- Complexity tools per language ---

COMPLEXITY_TOOLS: dict[str, list[ToolSpec]] = {
    "python": [
        ToolSpec(
            name="radon",
            cmd=["radon", "cc", "{repo_path}", "-s", "-j"],
            description="Python cyclomatic complexity analysis",
        ),
    ],
    "javascript": [
        ToolSpec(
            name="npx",
            cmd=["npx", "eslint", "--format", "json", "."],
            run_in_repo=True,
            timeout=600,
            description="JavaScript complexity via ESLint",
        ),
    ],
    "go": [
        ToolSpec(
            name="gocyclo",
            cmd=["gocyclo", "-over", "10", "."],
            run_in_repo=True,
            description="Go cyclomatic complexity analysis",
        ),
    ],
}

DEAD_CODE_TOOLS: dict[str, list[ToolSpec]] = {
    "python": [
        ToolSpec(
            name="vulture",
            cmd=["vulture", "{repo_path}"],
            description="Python dead code detection",
        ),
    ],
    "javascript": [],  # LLM fallback
    "go": [],  # LLM fallback
}


async def run_tool(
    spec: ToolSpec,
    repo_path: Path,
    fallback_context: str = "",
) -> tuple[str, bool]:
    """Run a CLI tool, or return fallback context if tool is unavailable.

    Returns (output_string, used_native_tool).
    """
    binary = spec.cmd[0]

    with tracer.start_as_current_span(
        f"run_{spec.name}",
        attributes={
            "tool.name": spec.name,
            "repo.path": str(repo_path),
        },
    ) as span:
        if not tool_available(binary):
            logger.warning("Tool %s not available, falling back to LLM analysis", spec.name)
            span.set_attribute("tool.mode", "llm_fallback")
            return (
                f"[TOOL_UNAVAILABLE: {spec.name}] "
                f"{spec.description} tool is not installed. "
                f"Please analyze the following code yourself:\n\n{fallback_context}"
            ), False

        logger.info("Running tool %s on %s", spec.name, repo_path)
        span.set_attribute("tool.mode", "native")
        cmd = [c.replace("{repo_path}", str(repo_path)) for c in spec.cmd]
        cwd = str(repo_path) if spec.run_in_repo else None

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=spec.timeout,
                cwd=cwd,
            )
            logger.info("Tool %s completed", spec.name)
            return (result.stdout or result.stderr or f"No issues found by {spec.name}."), True
        except subprocess.TimeoutExpired:
            logger.warning("Tool %s timed out after %ds", spec.name, spec.timeout)
            return f"{spec.name} timed out after {spec.timeout}s.", True
        except FileNotFoundError:
            logger.warning("Tool %s not found at execution time, falling back to LLM analysis", spec.name)
            span.set_attribute("tool.mode", "llm_fallback")
            return (
                f"[TOOL_UNAVAILABLE: {spec.name}] "
                f"Could not execute {spec.name}. "
                f"Please analyze the following code yourself:\n\n{fallback_context}"
            ), False


async def run_tools_for_languages(
    tool_registry: dict[str, list[ToolSpec]],
    languages: list[str],
    repo_path: Path,
    fallback_context: str = "",
) -> str:
    """Run all applicable tools for the detected languages.

    Iterates over languages, runs each tool (or falls back to LLM).
    Returns combined output string.
    """
    results: list[str] = []

    for lang in languages:
        specs = tool_registry.get(lang, [])
        if not specs:
            # No tools defined for this language — request LLM analysis
            results.append(
                f"[TOOL_UNAVAILABLE: {lang}] "
                f"No native analysis tool configured for {lang}. "
                f"Please analyze the following code yourself:\n\n{fallback_context}"
            )
            continue

        for spec in specs:
            output, _native = await run_tool(spec, repo_path, fallback_context)
            results.append(f"=== {spec.name} ({lang}) ===\n{output}")

    return "\n\n".join(results) if results else "No analysis tools available."
