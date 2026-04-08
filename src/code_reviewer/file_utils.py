"""File reading utilities with token-aware size limits."""

from __future__ import annotations

from pathlib import Path

# Approximate chars-per-token for code (Claude tokenizer averages ~3.5-4 for code)
CHARS_PER_TOKEN = 4

EXCLUDED_DIRS: set[str] = {
    "node_modules", "vendor", "dist", "build", ".next",
    "__pycache__", ".git", ".venv", "venv", ".tox",
}

STRUCTURE_PATTERNS: tuple[str, ...] = (
    "class ", "def ", "async def ", "function ", "export ", "type ", "func ",
)


def estimate_tokens(text: str) -> int:
    """Estimate token count from character length."""
    return len(text) // CHARS_PER_TOKEN


def get_source_summary(
    repo_path: Path,
    extensions: set[str] | None = None,
    limit: int = 50,
) -> str:
    """Return a lightweight summary: file list with function/class signatures only.

    This keeps the prompt small — agents can then use read_file_content()
    to drill into specific files that look interesting.
    """
    if extensions is None:
        extensions = {".py"}

    files = _get_source_files(repo_path, extensions, limit=limit)

    summary_parts: list[str] = []
    for f in files:
        rel = f.relative_to(repo_path)
        try:
            text = f.read_text(errors="ignore")
            lines = text.splitlines()
            sig_lines = [
                line.rstrip()
                for line in lines
                if line.strip().startswith(STRUCTURE_PATTERNS)
            ][:15]
            sigs = "\n  ".join(sig_lines) if sig_lines else "(no signatures)"
            summary_parts.append(f"{rel} ({len(lines)} lines):\n  {sigs}")
        except Exception:
            summary_parts.append(f"{rel} (unreadable)")

    return "\n".join(summary_parts) if summary_parts else "No source files found."


def read_file_content(
    repo_path: Path,
    relative_path: str,
    max_tokens: int = 3000,
) -> str:
    """Read a single file's content, capped at max_tokens (estimated).

    Default 3000 tokens ≈ 12000 chars — enough for most files while
    keeping total prompt well under the 200K limit.
    """
    max_chars = max_tokens * CHARS_PER_TOKEN
    target = (repo_path / relative_path).resolve()

    if not str(target).startswith(str(repo_path.resolve())):
        return f"Error: path {relative_path} is outside the repository."
    if not target.is_file():
        return f"Error: {relative_path} not found."

    try:
        text = target.read_text(errors="ignore")
        if len(text) > max_chars:
            text = text[:max_chars]
            token_est = estimate_tokens(text)
            return (
                f"--- {relative_path} (truncated to ~{token_est} tokens) ---\n{text}"
            )
        token_est = estimate_tokens(text)
        return f"--- {relative_path} (~{token_est} tokens) ---\n{text}"
    except Exception as e:
        return f"Error reading {relative_path}: {e}"


def cap_tool_output(output: str, max_tokens: int = 7500) -> str:
    """Truncate tool output to stay within a token budget."""
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(output) > max_chars:
        return (
            output[:max_chars]
            + f"\n\n... (truncated — ~{estimate_tokens(output)} tokens total, "
            f"showing first ~{max_tokens})"
        )
    return output


def _get_source_files(
    repo_path: Path, extensions: set[str], limit: int = 20,
) -> list[Path]:
    """Get source files matching extensions, skipping excluded dirs."""
    files: list[Path] = []
    for f in repo_path.rglob("*"):
        if (
            f.is_file()
            and f.suffix in extensions
            and not any(part in EXCLUDED_DIRS for part in f.parts)
        ):
            files.append(f)
            if len(files) >= limit:
                break
    return files
