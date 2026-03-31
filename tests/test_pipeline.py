"""Tests for the review pipeline orchestration."""

from unittest.mock import AsyncMock, patch

import pytest

from code_reviewer.models.review import (
    ComplexityReviewResult,
    DocumentationReviewResult,
    FinalReport,
    ReviewRequest,
    SecurityReviewResult,
    Severity,
)
from code_reviewer.pipeline import run_review_pipeline


class TestReviewPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_runs_all_workstreams(self, tmp_path):
        """Test that the pipeline clones, detects languages, runs all reviews, and generates a report."""
        mock_security = SecurityReviewResult(summary="No security issues")
        mock_complexity = ComplexityReviewResult(summary="Low complexity")
        mock_docs = DocumentationReviewResult(
            summary="Docs present", has_readme=True
        )
        mock_report = FinalReport(
            repo_url="https://github.com/user/repo",
            branch="main",
            security=mock_security,
            complexity=mock_complexity,
            documentation=mock_docs,
            overall_summary="All clear",
            overall_risk_level=Severity.LOW,
            total_findings=0,
        )

        with (
            patch("code_reviewer.pipeline.clone_repo", return_value=tmp_path),
            patch("code_reviewer.pipeline.cleanup_repo") as mock_cleanup,
            patch("code_reviewer.pipeline.detect_languages", return_value=["python"]),
            patch(
                "code_reviewer.pipeline.run_security_review",
                new_callable=AsyncMock,
                return_value=mock_security,
            ),
            patch(
                "code_reviewer.pipeline.run_complexity_review",
                new_callable=AsyncMock,
                return_value=mock_complexity,
            ),
            patch(
                "code_reviewer.pipeline.run_documentation_review",
                new_callable=AsyncMock,
                return_value=mock_docs,
            ),
            patch(
                "code_reviewer.pipeline.run_report_generation",
                new_callable=AsyncMock,
                return_value=mock_report,
            ),
        ):
            request = ReviewRequest(repo_url="https://github.com/user/repo")
            result = await run_review_pipeline(request)

            assert isinstance(result, FinalReport)
            assert result.total_findings == 0
            assert result.overall_risk_level == Severity.LOW
            mock_cleanup.assert_called_once_with(tmp_path)

    @pytest.mark.asyncio
    async def test_pipeline_cleans_up_on_error(self, tmp_path):
        """Test that cleanup happens even when a review fails."""
        with (
            patch("code_reviewer.pipeline.clone_repo", return_value=tmp_path),
            patch("code_reviewer.pipeline.cleanup_repo") as mock_cleanup,
            patch("code_reviewer.pipeline.detect_languages", return_value=["python"]),
            patch(
                "code_reviewer.pipeline.run_security_review",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Agent failed"),
            ),
            patch(
                "code_reviewer.pipeline.run_complexity_review",
                new_callable=AsyncMock,
            ),
            patch(
                "code_reviewer.pipeline.run_documentation_review",
                new_callable=AsyncMock,
            ),
        ):
            request = ReviewRequest(repo_url="https://github.com/user/repo")
            with pytest.raises(RuntimeError, match="Agent failed"):
                await run_review_pipeline(request)

            # Cleanup should still be called
            mock_cleanup.assert_called_once_with(tmp_path)
