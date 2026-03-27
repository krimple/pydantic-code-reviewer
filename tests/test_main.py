"""Tests for the main CLI entry point."""

from unittest.mock import AsyncMock, patch

import pytest

from code_reviewer.main import async_main, main


class TestMain:
    def test_main_no_args_exits(self):
        with patch("sys.argv", ["code-reviewer"]):
            with pytest.raises(SystemExit, match="1"):
                main()

    @patch("code_reviewer.main.run_review_pipeline", new_callable=AsyncMock)
    @patch("code_reviewer.main.setup_telemetry")
    async def test_async_main(self, mock_telemetry, mock_pipeline):
        from code_reviewer.models.review import (
            ComplexityReviewResult,
            DocumentationReviewResult,
            FinalReport,
            SecurityReviewResult,
            Severity,
        )

        mock_provider = mock_telemetry.return_value
        mock_pipeline.return_value = FinalReport(
            repo_url="https://github.com/user/repo",
            branch="main",
            security=SecurityReviewResult(summary="OK"),
            complexity=ComplexityReviewResult(summary="OK"),
            documentation=DocumentationReviewResult(summary="OK"),
            overall_summary="All clear",
            overall_risk_level=Severity.LOW,
            total_findings=0,
        )

        await async_main("https://github.com/user/repo")
        mock_pipeline.assert_called_once()
        mock_provider.shutdown.assert_called_once()
