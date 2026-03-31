"""Tests to cover remaining edge cases and branches."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from code_reviewer.agents.complexity import ComplexityDeps
from code_reviewer.agents.security import SecurityDeps


def _make_ctx(deps):
    ctx = MagicMock()
    ctx.deps = deps
    return ctx


class TestComplexityErrorBranches:
    @pytest.mark.asyncio
    async def test_complexity_tool_timeout(self, tmp_path):
        from code_reviewer.agents.complexity import run_complexity_analysis

        (tmp_path / "app.py").write_text("def foo(): pass\n")
        ctx = _make_ctx(ComplexityDeps(repo_path=tmp_path, languages=["python"]))
        with patch("code_reviewer.tool_config.subprocess.run") as mock:
            mock.side_effect = subprocess.TimeoutExpired(cmd="radon", timeout=120)
            result = await run_complexity_analysis(ctx)
            assert "timed out" in result.lower()

    @pytest.mark.asyncio
    async def test_complexity_tool_not_found(self, tmp_path):
        from code_reviewer.agents.complexity import run_complexity_analysis

        (tmp_path / "app.py").write_text("def foo(): pass\n")
        ctx = _make_ctx(ComplexityDeps(repo_path=tmp_path, languages=["python"]))
        with patch("code_reviewer.tool_config.tool_available", return_value=False):
            result = await run_complexity_analysis(ctx)
            assert "TOOL_UNAVAILABLE" in result

    @pytest.mark.asyncio
    async def test_complexity_tool_empty_output(self, tmp_path):
        from code_reviewer.agents.complexity import run_complexity_analysis

        (tmp_path / "app.py").write_text("def foo(): pass\n")
        ctx = _make_ctx(ComplexityDeps(repo_path=tmp_path, languages=["python"]))
        with patch("code_reviewer.tool_config.subprocess.run") as mock:
            mock.return_value = MagicMock(stdout="", stderr="")
            result = await run_complexity_analysis(ctx)
            assert "No issues found" in result or "radon" in result.lower()

    @pytest.mark.asyncio
    async def test_dead_code_tool_unavailable(self, tmp_path):
        from code_reviewer.agents.complexity import run_dead_code_detection

        (tmp_path / "app.py").write_text("def foo(): pass\n")
        ctx = _make_ctx(ComplexityDeps(repo_path=tmp_path, languages=["python"]))
        with patch("code_reviewer.tool_config.tool_available", return_value=False):
            result = await run_dead_code_detection(ctx)
            assert "TOOL_UNAVAILABLE" in result

    @pytest.mark.asyncio
    async def test_read_duplication_empty(self, tmp_path):
        from code_reviewer.agents.complexity import read_source_for_duplication

        ctx = _make_ctx(ComplexityDeps(repo_path=tmp_path, languages=["python"]))
        result = await read_source_for_duplication(ctx)
        assert "No source files" in result


class TestSecurityErrorBranches:
    @pytest.mark.asyncio
    async def test_security_tool_not_found(self, tmp_path):
        from code_reviewer.agents.security import run_static_security_scan

        (tmp_path / "app.py").write_text("import os\n")
        ctx = _make_ctx(SecurityDeps(repo_path=tmp_path, languages=["python"]))
        with patch("code_reviewer.tool_config.tool_available", return_value=False):
            result = await run_static_security_scan(ctx)
            assert "TOOL_UNAVAILABLE" in result

    @pytest.mark.asyncio
    async def test_security_tool_empty_output(self, tmp_path):
        from code_reviewer.agents.security import run_static_security_scan

        (tmp_path / "app.py").write_text("import os\n")
        ctx = _make_ctx(SecurityDeps(repo_path=tmp_path, languages=["python"]))
        with patch("code_reviewer.tool_config.subprocess.run") as mock:
            mock.return_value = MagicMock(stdout="", stderr="")
            result = await run_static_security_scan(ctx)
            assert "No issues found" in result or "bandit" in result.lower()

    @pytest.mark.asyncio
    async def test_pip_audit_timeout(self, tmp_path):
        from code_reviewer.agents.security import run_dependency_audit

        (tmp_path / "requirements.txt").write_text("flask\n")
        ctx = _make_ctx(SecurityDeps(repo_path=tmp_path, languages=["python"]))
        with patch("code_reviewer.agents.security.subprocess.run") as mock:
            mock.side_effect = subprocess.TimeoutExpired(cmd="pip-audit", timeout=120)
            result = await run_dependency_audit(ctx)
            assert "pip-audit error" in result

    @pytest.mark.asyncio
    async def test_pip_audit_pyproject_timeout(self, tmp_path):
        from code_reviewer.agents.security import run_dependency_audit

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        ctx = _make_ctx(SecurityDeps(repo_path=tmp_path, languages=["python"]))
        with patch("code_reviewer.agents.security.subprocess.run") as mock:
            mock.side_effect = subprocess.TimeoutExpired(cmd="pip-audit", timeout=120)
            result = await run_dependency_audit(ctx)
            assert "pip-audit error" in result


class TestTelemetryEdgeCases:
    def test_telemetry_disabled(self):
        with patch.dict("os.environ", {"CLAUDE_CODE_ENABLE_TELEMETRY": "false"}):
            from code_reviewer.telemetry import setup_telemetry
            provider = setup_telemetry()
            assert provider is not None
            provider.shutdown()

    def test_logfire_integration_failure(self):
        import builtins
        real_import = builtins.__import__

        def fail_logfire(name, *args, **kwargs):
            if name == "logfire":
                raise ImportError("no logfire")
            return real_import(name, *args, **kwargs)

        with patch.dict("os.environ", {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "true",
            "HONEYCOMB_API_KEY": "",
        }):
            with patch("builtins.__import__", side_effect=fail_logfire):
                from code_reviewer.telemetry import setup_telemetry
                provider = setup_telemetry()
                assert provider is not None
                provider.shutdown()


class TestPipelineHelpers:
    def test_log_status_when_enabled(self):
        from code_reviewer.pipeline import _log_status
        from code_reviewer.telemetry import SESSION_CONVERSATION_ID
        span = MagicMock()
        with patch.dict("os.environ", {"AGENT_LOG_STATUS": "true"}):
            _log_status(span, "reviewing")
            span.add_event.assert_called_once_with(
                "agent.status", {"status": "reviewing", "gen_ai.conversation.id": SESSION_CONVERSATION_ID}
            )

    def test_log_status_when_disabled(self):
        from code_reviewer.pipeline import _log_status
        span = MagicMock()
        with patch.dict("os.environ", {"AGENT_LOG_STATUS": "false"}):
            _log_status(span, "reviewing")
            span.add_event.assert_not_called()


class TestMainCLI:
    def test_main_with_args(self):
        from code_reviewer.main import main
        with (
            patch("sys.argv", ["code-reviewer", "https://github.com/u/r", "dev"]),
            patch("code_reviewer.main.asyncio.run") as mock_run,
        ):
            main()
            mock_run.assert_called_once()
