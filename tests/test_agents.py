"""Tests for review agents."""


from code_reviewer.agents.security import SecurityDeps, security_agent
from code_reviewer.agents.complexity import ComplexityDeps, complexity_agent
from code_reviewer.agents.documentation import DocsDeps, documentation_agent
from code_reviewer.agents.report import ReportDeps, report_agent
from code_reviewer.models.review import (
    ComplexityReviewResult,
    DocumentationReviewResult,
    SecurityReviewResult,
)


class TestSecurityAgent:
    def test_agent_exists(self):
        assert security_agent is not None

    def test_security_deps(self, tmp_path):
        deps = SecurityDeps(repo_path=tmp_path)
        assert deps.repo_path == tmp_path


class TestComplexityAgent:
    def test_agent_exists(self):
        assert complexity_agent is not None

    def test_complexity_deps(self, tmp_path):
        deps = ComplexityDeps(repo_path=tmp_path)
        assert deps.repo_path == tmp_path


class TestDocumentationAgent:
    def test_agent_exists(self):
        assert documentation_agent is not None

    def test_docs_deps(self, tmp_path):
        deps = DocsDeps(repo_path=tmp_path)
        assert deps.repo_path == tmp_path


class TestReportAgent:
    def test_agent_exists(self):
        assert report_agent is not None

    def test_report_deps(self):
        deps = ReportDeps(
            repo_url="https://github.com/user/repo",
            branch="main",
            security=SecurityReviewResult(summary="OK"),
            complexity=ComplexityReviewResult(summary="OK"),
            documentation=DocumentationReviewResult(summary="OK"),
        )
        assert deps.repo_url == "https://github.com/user/repo"
