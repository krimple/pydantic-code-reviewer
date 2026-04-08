"""Security review agent — checks for vulnerabilities and bad dependencies."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from code_reviewer.config import DEFAULT_MODEL
from code_reviewer.file_utils import cap_tool_output, get_source_summary, read_file_content
from code_reviewer.models.review import SecurityReviewResult
from code_reviewer.telemetry import get_tracer

tracer = get_tracer("code-reviewer.security")


@dataclass
class SecurityDeps:
    """Dependencies for the security review agent."""
    repo_path: Path


security_agent = Agent(
    deps_type=SecurityDeps,
    output_type=SecurityReviewResult,
    instructions=(
        "You are a security reviewer. Analyze the tool outputs from bandit "
        "(static security analysis) and pip-audit (dependency vulnerability check). "
        "Also review the source summary, then use read_specific_file to inspect "
        "any files that look suspicious. "
        "Summarize findings into a structured SecurityReviewResult. "
        "Rate severity accurately: CRITICAL for RCE/injection, HIGH for auth issues, "
        "MEDIUM for information disclosure, LOW for best-practice violations."
    ),
)


@security_agent.tool
async def run_bandit_scan(ctx: RunContext[SecurityDeps]) -> str:
    """Run bandit static security analysis on the repository."""
    with tracer.start_as_current_span(
        "run_bandit",
        attributes={"repo.path": str(ctx.deps.repo_path)},
    ):
        try:
            result = subprocess.run(
                ["bandit", "-r", str(ctx.deps.repo_path), "-f", "json", "-q"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout or result.stderr or "No issues found."
            return cap_tool_output(output)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            return f"Bandit scan error: {e}"


@security_agent.tool
async def run_dependency_audit(ctx: RunContext[SecurityDeps]) -> str:
    """Check for known vulnerabilities in project dependencies."""
    with tracer.start_as_current_span(
        "run_pip_audit",
        attributes={"repo.path": str(ctx.deps.repo_path)},
    ):
        req_files = list(ctx.deps.repo_path.glob("**/requirements*.txt"))
        pyproject = ctx.deps.repo_path / "pyproject.toml"

        if not req_files and not pyproject.exists():
            return "No requirements files or pyproject.toml found."

        results = []
        for req_file in req_files:
            try:
                result = subprocess.run(
                    ["pip-audit", "-r", str(req_file), "-f", "json"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                results.append(result.stdout or result.stderr)
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                results.append(f"pip-audit error for {req_file.name}: {e}")

        if pyproject.exists() and not req_files:
            try:
                result = subprocess.run(
                    ["pip-audit", "-f", "json"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    cwd=str(ctx.deps.repo_path),
                )
                results.append(result.stdout or result.stderr)
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                results.append(f"pip-audit error for pyproject.toml: {e}")

        return "\n".join(results) if results else "No dependency issues found."


@security_agent.tool
async def read_source_summary(ctx: RunContext[SecurityDeps]) -> str:
    """Get a summary of all source files with their function/class signatures.
    Use read_specific_file to drill into any file that looks suspicious."""
    with tracer.start_as_current_span("read_source_summary"):
        return get_source_summary(ctx.deps.repo_path)


@security_agent.tool
async def read_specific_file(ctx: RunContext[SecurityDeps], file_path: str) -> str:
    """Read the full content of a specific source file by its relative path.
    Use this to drill into files identified as potentially problematic."""
    with tracer.start_as_current_span("read_specific_file"):
        return read_file_content(ctx.deps.repo_path, file_path)


async def run_security_review(repo_path: Path) -> SecurityReviewResult:
    """Execute the security review agent."""
    with tracer.start_as_current_span(
        "security_review",
        attributes={"repo.path": str(repo_path)},
    ):
        deps = SecurityDeps(repo_path=repo_path)
        result = await security_agent.run(
            "Analyze this repository for security issues. "
            "Run the bandit scan and dependency audit tools. "
            "Then review the source summary and use read_specific_file "
            "to inspect any files that look suspicious.",
            deps=deps,
            model=DEFAULT_MODEL,
        )
        return result.output
