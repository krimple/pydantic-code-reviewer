"""Tests for Pydantic review models."""

from code_reviewer.models.review import (
    ComplexityReviewResult,
    DocumentationReviewResult,
    FinalReport,
    Finding,
    ReviewRequest,
    SecurityReviewResult,
    Severity,
)


class TestFinding:
    def test_create_finding(self):
        f = Finding(
            title="SQL Injection",
            description="Unsanitized input in query",
            severity=Severity.CRITICAL,
            file_path="app.py",
            line_number=42,
            recommendation="Use parameterized queries",
        )
        assert f.title == "SQL Injection"
        assert f.severity == Severity.CRITICAL
        assert f.file_path == "app.py"

    def test_finding_defaults(self):
        f = Finding(
            title="Minor issue",
            description="Something small",
            severity=Severity.LOW,
        )
        assert f.file_path is None
        assert f.line_number is None
        assert f.recommendation == ""


class TestSecurityReviewResult:
    def test_empty_result(self):
        r = SecurityReviewResult(summary="No issues")
        assert r.findings == []
        assert r.dependencies_checked == 0
        assert r.vulnerable_dependencies == []

    def test_with_findings(self):
        r = SecurityReviewResult(
            findings=[
                Finding(
                    title="Hardcoded secret",
                    description="API key in source",
                    severity=Severity.HIGH,
                )
            ],
            dependencies_checked=10,
            vulnerable_dependencies=["requests==2.25.0"],
            summary="Found 1 issue",
        )
        assert len(r.findings) == 1
        assert r.dependencies_checked == 10


class TestComplexityReviewResult:
    def test_empty_result(self):
        r = ComplexityReviewResult(summary="Clean code")
        assert r.average_cyclomatic_complexity == 0.0
        assert r.high_complexity_functions == []
        assert r.dead_code_items == []

    def test_with_data(self):
        r = ComplexityReviewResult(
            average_cyclomatic_complexity=5.2,
            high_complexity_functions=["process_data"],
            repeated_code_blocks=["auth check pattern"],
            dead_code_items=["old_handler"],
            summary="Some complexity issues",
        )
        assert r.average_cyclomatic_complexity == 5.2
        assert len(r.high_complexity_functions) == 1


class TestDocumentationReviewResult:
    def test_empty_result(self):
        r = DocumentationReviewResult(summary="No docs")
        assert r.has_readme is False
        assert r.documentation_coverage == 0.0

    def test_with_good_docs(self):
        r = DocumentationReviewResult(
            has_readme=True,
            has_api_docs=True,
            has_contributing_guide=True,
            documentation_coverage=0.85,
            relevance_score=0.9,
            summary="Good documentation",
        )
        assert r.has_readme is True
        assert r.relevance_score == 0.9


class TestReviewRequest:
    def test_create_request(self):
        r = ReviewRequest(repo_url="https://github.com/user/repo")
        assert r.branch == "main"

    def test_custom_branch(self):
        r = ReviewRequest(
            repo_url="https://github.com/user/repo", branch="develop"
        )
        assert r.branch == "develop"


class TestFinalReport:
    def test_create_report(self):
        report = FinalReport(
            repo_url="https://github.com/user/repo",
            branch="main",
            security=SecurityReviewResult(summary="OK"),
            complexity=ComplexityReviewResult(summary="OK"),
            documentation=DocumentationReviewResult(summary="OK"),
            overall_summary="All clear",
            overall_risk_level=Severity.LOW,
            total_findings=0,
        )
        assert report.total_findings == 0
        assert report.overall_risk_level == Severity.LOW

    def test_report_serialization(self):
        report = FinalReport(
            repo_url="https://github.com/user/repo",
            branch="main",
            security=SecurityReviewResult(summary="OK"),
            complexity=ComplexityReviewResult(summary="OK"),
            documentation=DocumentationReviewResult(summary="OK"),
        )
        data = report.model_dump()
        assert "security" in data
        assert "complexity" in data
        assert "documentation" in data

        # Round-trip
        restored = FinalReport.model_validate(data)
        assert restored.repo_url == report.repo_url
