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


def _iter_source_files(repo_path: Path):
    """Iterate over source files, skipping excluded directories."""
    for f in repo_path.rglob("*"):
        if f.is_file() and not any(part in EXCLUDED_DIRS for part in f.parts):
            yield f
