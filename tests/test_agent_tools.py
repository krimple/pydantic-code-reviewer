"""Tests for agent tool functions using mocked subprocess and file system."""

from unittest.mock import MagicMock, patch
import subprocess

import pytest

from code_reviewer.agents.security import SecurityDeps
from code_reviewer.agents.complexity import ComplexityDeps
from code_reviewer.agents.documentation import DocsDeps


def _make_ctx(deps):
    """Create a mock RunContext with the given deps."""
    ctx = MagicMock()
    ctx.deps = deps
    return ctx


class TestSecurityTools:
    @pytest.mark.asyncio
    async def test_run_bandit_scan(self, tmp_path):
        from code_reviewer.agents.security import run_bandit_scan

        deps = SecurityDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        with patch("code_reviewer.agents.security.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout='{"results": []}', stderr=""
            )
            result = await run_bandit_scan(ctx)
            assert "results" in result
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_bandit_scan_timeout(self, tmp_path):
        from code_reviewer.agents.security import run_bandit_scan

        deps = SecurityDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        with patch("code_reviewer.agents.security.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="bandit", timeout=120)
            result = await run_bandit_scan(ctx)
            assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_run_dependency_audit_no_files(self, tmp_path):
        from code_reviewer.agents.security import run_dependency_audit

        deps = SecurityDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        result = await run_dependency_audit(ctx)
        assert "No requirements files" in result

    @pytest.mark.asyncio
    async def test_run_dependency_audit_with_requirements(self, tmp_path):
        from code_reviewer.agents.security import run_dependency_audit

        req_file = tmp_path / "requirements.txt"
        req_file.write_text("requests==2.28.0\n")
        deps = SecurityDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        with patch("code_reviewer.agents.security.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout='{"dependencies": []}', stderr=""
            )
            result = await run_dependency_audit(ctx)
            assert "dependencies" in result

    @pytest.mark.asyncio
    async def test_run_dependency_audit_pyproject_only(self, tmp_path):
        from code_reviewer.agents.security import run_dependency_audit

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\n')
        deps = SecurityDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        with patch("code_reviewer.agents.security.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout='{"dependencies": []}', stderr=""
            )
            result = await run_dependency_audit(ctx)
            assert "dependencies" in result

    @pytest.mark.asyncio
    async def test_read_source_files(self, tmp_path):
        from code_reviewer.agents.security import read_source_files

        (tmp_path / "app.py").write_text("import os\nprint('hello')\n")
        deps = SecurityDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        result = await read_source_files(ctx)
        assert "app.py" in result
        assert "import os" in result

    @pytest.mark.asyncio
    async def test_read_source_files_empty(self, tmp_path):
        from code_reviewer.agents.security import read_source_files

        deps = SecurityDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        result = await read_source_files(ctx)
        assert "No Python files" in result


class TestComplexityTools:
    @pytest.mark.asyncio
    async def test_run_complexity_analysis(self, tmp_path):
        from code_reviewer.agents.complexity import run_complexity_analysis

        deps = ComplexityDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        with patch("code_reviewer.agents.complexity.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout='{"app.py": []}', stderr="")
            result = await run_complexity_analysis(ctx)
            assert "app.py" in result

    @pytest.mark.asyncio
    async def test_run_dead_code_detection(self, tmp_path):
        from code_reviewer.agents.complexity import run_dead_code_detection

        deps = ComplexityDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        with patch("code_reviewer.agents.complexity.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="app.py:10: unused function 'old_func'", stderr=""
            )
            result = await run_dead_code_detection(ctx)
            assert "old_func" in result

    @pytest.mark.asyncio
    async def test_run_dead_code_not_found(self, tmp_path):
        from code_reviewer.agents.complexity import run_dead_code_detection

        deps = ComplexityDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        with patch("code_reviewer.agents.complexity.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("vulture not found")
            result = await run_dead_code_detection(ctx)
            assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_read_source_for_duplication(self, tmp_path):
        from code_reviewer.agents.complexity import read_source_for_duplication

        (tmp_path / "module.py").write_text("def foo():\n    pass\n")
        deps = ComplexityDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        result = await read_source_for_duplication(ctx)
        assert "module.py" in result


class TestDocumentationTools:
    @pytest.mark.asyncio
    async def test_find_documentation_files(self, tmp_path):
        from code_reviewer.agents.documentation import find_documentation_files

        (tmp_path / "README.md").write_text("# Hello")
        (tmp_path / "CONTRIBUTING.md").write_text("# Contrib")
        deps = DocsDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        result = await find_documentation_files(ctx)
        assert "README.md" in result
        assert "CONTRIBUTING.md" in result

    @pytest.mark.asyncio
    async def test_find_documentation_files_empty(self, tmp_path):
        from code_reviewer.agents.documentation import find_documentation_files

        deps = DocsDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        result = await find_documentation_files(ctx)
        assert "No documentation files" in result

    @pytest.mark.asyncio
    async def test_read_documentation(self, tmp_path):
        from code_reviewer.agents.documentation import read_documentation

        (tmp_path / "README.md").write_text("# My Project\nSome docs here.")
        deps = DocsDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        result = await read_documentation(ctx)
        assert "My Project" in result

    @pytest.mark.asyncio
    async def test_read_documentation_empty(self, tmp_path):
        from code_reviewer.agents.documentation import read_documentation

        deps = DocsDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        result = await read_documentation(ctx)
        assert "No documentation content" in result

    @pytest.mark.asyncio
    async def test_read_source_structure(self, tmp_path):
        from code_reviewer.agents.documentation import read_source_structure

        (tmp_path / "app.py").write_text("class MyApp:\n    def run(self):\n        pass\n")
        deps = DocsDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        result = await read_source_structure(ctx)
        assert "app.py" in result
        assert "class MyApp" in result

    @pytest.mark.asyncio
    async def test_read_source_structure_empty(self, tmp_path):
        from code_reviewer.agents.documentation import read_source_structure

        deps = DocsDeps(repo_path=tmp_path)
        ctx = _make_ctx(deps)

        result = await read_source_structure(ctx)
        assert "No Python source files" in result


class TestReportTools:
    @pytest.mark.asyncio
    async def test_get_security_results(self):
        from code_reviewer.agents.report import get_security_results, ReportDeps
        from code_reviewer.models.review import (
            SecurityReviewResult,
            ComplexityReviewResult,
            DocumentationReviewResult,
        )

        deps = ReportDeps(
            repo_url="https://github.com/user/repo",
            branch="main",
            security=SecurityReviewResult(summary="Clean"),
            complexity=ComplexityReviewResult(summary="OK"),
            documentation=DocumentationReviewResult(summary="OK"),
        )
        ctx = _make_ctx(deps)
        result = await get_security_results(ctx)
        assert "Clean" in result

    @pytest.mark.asyncio
    async def test_get_complexity_results(self):
        from code_reviewer.agents.report import get_complexity_results, ReportDeps
        from code_reviewer.models.review import (
            SecurityReviewResult,
            ComplexityReviewResult,
            DocumentationReviewResult,
        )

        deps = ReportDeps(
            repo_url="https://github.com/user/repo",
            branch="main",
            security=SecurityReviewResult(summary="OK"),
            complexity=ComplexityReviewResult(summary="Low complexity"),
            documentation=DocumentationReviewResult(summary="OK"),
        )
        ctx = _make_ctx(deps)
        result = await get_complexity_results(ctx)
        assert "Low complexity" in result

    @pytest.mark.asyncio
    async def test_get_documentation_results(self):
        from code_reviewer.agents.report import get_documentation_results, ReportDeps
        from code_reviewer.models.review import (
            SecurityReviewResult,
            ComplexityReviewResult,
            DocumentationReviewResult,
        )

        deps = ReportDeps(
            repo_url="https://github.com/user/repo",
            branch="main",
            security=SecurityReviewResult(summary="OK"),
            complexity=ComplexityReviewResult(summary="OK"),
            documentation=DocumentationReviewResult(summary="Good docs", has_readme=True),
        )
        ctx = _make_ctx(deps)
        result = await get_documentation_results(ctx)
        assert "Good docs" in result
        assert "true" in result.lower()
