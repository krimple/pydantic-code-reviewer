"""Security review agent — checks for vulnerabilities and bad dependencies."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from code_reviewer.config import DEFAULT_MODEL
from code_reviewer.agent_context import current_agent_id, current_agent_name
from code_reviewer.languages import get_source_summary, read_file_content
from code_reviewer.models.review import SecurityReviewResult
from code_reviewer.telemetry import get_tracer
from code_reviewer.tool_config import (
    SECURITY_TOOLS,
    run_tools_for_languages,
)

logger = logging.getLogger(__name__)
tracer = get_tracer("code-reviewer.security")


@dataclass
class SecurityDeps:
    """Dependencies for the security review agent."""

    repo_path: Path
    languages: list[str]


security_agent = Agent(
    name="security_agent",
    deps_type=SecurityDeps,
    output_type=SecurityReviewResult,
    instructions=(
        "You are a security reviewer. Analyze the tool outputs from static security "
        "analysis and dependency vulnerability checks for all detected languages. "
        "If any tool output is prefixed with [TOOL_UNAVAILABLE], perform that analysis "
        "yourself by first reviewing the source summary, then using read_specific_file "
        "to inspect any files that look suspicious. "
        "Summarize findings into a structured SecurityReviewResult. "
        "Rate severity accurately: CRITICAL for RCE/injection, HIGH for auth issues, "
        "MEDIUM for information disclosure, LOW for best-practice violations."
    ),
)


@security_agent.tool
async def run_static_security_scan(ctx: RunContext[SecurityDeps]) -> str:
    """Run static security analysis tools for all detected languages."""
    return await run_tools_for_languages(
        SECURITY_TOOLS,
        ctx.deps.languages,
        ctx.deps.repo_path,
    )


@security_agent.tool
async def run_dependency_audit(ctx: RunContext[SecurityDeps]) -> str:
    """Check for known vulnerabilities in project dependencies."""
    with tracer.start_as_current_span(
        "run_dependency_audit",
        attributes={"repo.path": str(ctx.deps.repo_path)},
    ):
        results: list[str] = []

        # Python: pip-audit with requirements files
        if "python" in ctx.deps.languages:
            results.append(await _run_python_dependency_audit(ctx.deps.repo_path))

        # JavaScript: npm audit
        if "javascript" in ctx.deps.languages:
            results.append(await _run_js_dependency_audit(ctx.deps.repo_path))

        # Go: govulncheck
        if "go" in ctx.deps.languages:
            results.append(await _run_go_dependency_audit(ctx.deps.repo_path))

        return "\n\n".join(results) if results else "No dependency files found for any detected language."


@security_agent.tool
async def read_source_summary(ctx: RunContext[SecurityDeps]) -> str:
    """Get a summary of all source files with their function/class signatures.
    Use read_specific_file to drill into any file that looks suspicious."""
    with tracer.start_as_current_span("read_source_summary"):
        return get_source_summary(ctx.deps.repo_path, ctx.deps.languages)


@security_agent.tool
async def read_specific_file(ctx: RunContext[SecurityDeps], file_path: str) -> str:
    """Read the full content of a specific source file by its relative path.
    Use this to drill into files identified as potentially problematic."""
    with tracer.start_as_current_span("read_specific_file"):
        return read_file_content(ctx.deps.repo_path, file_path)


async def run_security_review(repo_path: Path, languages: list[str]) -> SecurityReviewResult:
    """Execute the security review agent."""
    with tracer.start_as_current_span(
        "security_review",
        attributes={"repo.path": str(repo_path), "repo.languages": ",".join(languages)},
    ):
        logger.info("Starting security review agent for languages: %s", ", ".join(languages))
        current_agent_id.set("security_agent")
        current_agent_name.set("security_agent")
        deps = SecurityDeps(repo_path=repo_path, languages=languages)
        lang_list = ", ".join(languages)
        result = await security_agent.run(
            f"Analyze this {lang_list} repository for security issues. "
            "Run the static security scan and dependency audit tools. "
            "Then use read_source_summary to review the codebase structure, "
            "and read_specific_file to inspect any files that need closer review.",
            deps=deps,
            model=DEFAULT_MODEL,
        )
        logger.info("Security review agent complete")
        return result.output


async def _run_python_dependency_audit(repo_path: Path) -> str:
    """Run pip-audit for Python dependencies."""
    req_files = list(repo_path.glob("**/requirements*.txt"))
    pyproject = repo_path / "pyproject.toml"

    if not req_files and not pyproject.exists():
        return "Python: No requirements files or pyproject.toml found."

    results: list[str] = []
    for req_file in req_files:
        try:
            result = subprocess.run(
                ["pip-audit", "-r", str(req_file), "-f", "json"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            results.append(f"pip-audit ({req_file.name}): {result.stdout or result.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            results.append(f"pip-audit error for {req_file.name}: {e}")

    if pyproject.exists() and not req_files:
        try:
            result = subprocess.run(
                ["pip-audit", "-f", "json"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(repo_path),
            )
            results.append(f"pip-audit (pyproject.toml): {result.stdout or result.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            results.append(f"pip-audit error for pyproject.toml: {e}")

    return "\n".join(results)


async def _run_js_dependency_audit(repo_path: Path) -> str:
    """Run npm audit for JavaScript dependencies."""
    package_lock = repo_path / "package-lock.json"
    package_json = repo_path / "package.json"

    if not package_json.exists():
        return "JavaScript: No package.json found."

    if not package_lock.exists():
        # npm audit needs a lockfile; provide package.json for LLM analysis
        try:
            text = package_json.read_text(errors="ignore")[:8000]
            return (
                "[TOOL_UNAVAILABLE: npm audit] No package-lock.json found. "
                f"Please analyze dependencies from package.json:\n\n{text}"
            )
        except Exception:
            return "JavaScript: Could not read package.json."

    try:
        result = subprocess.run(
            ["npm", "audit", "--json"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(repo_path),
        )
        return f"npm audit: {result.stdout or result.stderr}"
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return f"npm audit error: {e}"


async def _run_go_dependency_audit(repo_path: Path) -> str:
    """Run govulncheck for Go dependencies."""
    go_mod = repo_path / "go.mod"

    if not go_mod.exists():
        return "Go: No go.mod found."

    try:
        result = subprocess.run(
            ["govulncheck", "./..."],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(repo_path),
        )
        return f"govulncheck: {result.stdout or result.stderr}"
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        try:
            text = go_mod.read_text(errors="ignore")[:8000]
            return (
                f"[TOOL_UNAVAILABLE: govulncheck] govulncheck error: {e}. "
                f"Please analyze dependencies from go.mod:\n\n{text}"
            )
        except Exception:
            return f"govulncheck error: {e}"
