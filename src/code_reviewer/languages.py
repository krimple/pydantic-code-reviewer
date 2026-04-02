"""Language detection and file extension mappings for multi-language support."""

from __future__ import annotations

import shutil
from pathlib import Path

LANG_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "javascript": [".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"],
    "go": [".go"],
}

MARKER_FILES: dict[str, list[str]] = {
    "python": ["pyproject.toml", "setup.py", "setup.cfg", "Pipfile"],
    "javascript": ["package.json", "tsconfig.json"],
    "go": ["go.mod"],
}

EXCLUDED_DIRS: set[str] = {
    "node_modules", "vendor", "dist", "build", ".next",
    "__pycache__", ".git", ".venv", "venv", ".tox",
}

STRUCTURE_PATTERNS: dict[str, tuple[str, ...]] = {
    "python": ("class ", "def ", "async def "),
    "javascript": ("class ", "function ", "export ", "export default ", "module.exports"),
    "go": ("func ", "type ", "package "),
}


def detect_languages(repo_path: Path) -> list[str]:
    """Detect which programming languages are present in a repository.

    Checks for marker files first (fast), then scans for source extensions.
    Returns a list of detected language names, e.g. ["python", "javascript"].
    """
    detected: set[str] = set()

    # Check marker files first (fast)
    for lang, markers in MARKER_FILES.items():
        for marker in markers:
            if (repo_path / marker).exists():
                detected.add(lang)
                break

    # Scan source file extensions if markers didn't cover everything
    if len(detected) < len(LANG_EXTENSIONS):
        ext_to_lang: dict[str, str] = {}
        for lang, exts in LANG_EXTENSIONS.items():
            if lang not in detected:
                for ext in exts:
                    ext_to_lang[ext] = lang

        for f in _iter_source_files(repo_path):
            lang = ext_to_lang.get(f.suffix)
            if lang:
                detected.add(lang)
            if len(detected) == len(LANG_EXTENSIONS):
                break

    return sorted(detected) if detected else ["unknown"]


def get_source_files(repo_path: Path, languages: list[str], limit: int = 20) -> list[Path]:
    """Get source files for the given languages, respecting exclusion dirs and limit."""
    extensions: set[str] = set()
    for lang in languages:
        extensions.update(LANG_EXTENSIONS.get(lang, []))

    files: list[Path] = []
    for f in _iter_source_files(repo_path):
        if f.suffix in extensions:
            files.append(f)
            if len(files) >= limit:
                break
    return files


def tool_available(name: str) -> bool:
    """Check if a CLI tool is available on PATH."""
    return shutil.which(name) is not None


def get_source_summary(repo_path: Path, languages: list[str], limit: int = 50) -> str:
    """Return a lightweight summary: file list with function/class signatures only."""
    files = get_source_files(repo_path, languages, limit=limit)

    patterns: tuple[str, ...] = ()
    for lang in languages:
        patterns = patterns + STRUCTURE_PATTERNS.get(lang, ())

    summary_parts: list[str] = []
    for f in files:
        rel = f.relative_to(repo_path)
        try:
            text = f.read_text(errors="ignore")
            lines = text.splitlines()
            line_count = len(lines)
            sig_lines = [
                line.rstrip()
                for line in lines
                if line.strip().startswith(patterns)
            ][:15] if patterns else []
            sigs = "\n  ".join(sig_lines) if sig_lines else "(no signatures extracted)"
            summary_parts.append(f"{rel} ({line_count} lines):\n  {sigs}")
        except Exception:
            summary_parts.append(f"{rel} (unreadable)")

    return "\n".join(summary_parts) if summary_parts else "No source files found."


def read_file_content(repo_path: Path, relative_path: str, max_chars: int = 12000) -> str:
    """Read a single file's content, capped at max_chars."""
    target = (repo_path / relative_path).resolve()
    if not str(target).startswith(str(repo_path.resolve())):
        return f"Error: path {relative_path} is outside the repository."
    if not target.is_file():
        return f"Error: {relative_path} not found."
    try:
        text = target.read_text(errors="ignore")[:max_chars]
        truncated = " (truncated)" if len(text) == max_chars else ""
        return f"--- {relative_path}{truncated} ---\n{text}"
    except Exception as e:
        return f"Error reading {relative_path}: {e}"


def _iter_source_files(repo_path: Path):
    """Iterate over source files, skipping excluded directories."""
    for f in repo_path.rglob("*"):
        if f.is_file() and not any(part in EXCLUDED_DIRS for part in f.parts):
            yield f
