"""Pydantic models for code review inputs and outputs."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity level for review findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Finding(BaseModel):
    """A single review finding."""
    title: str
    description: str
    severity: Severity
    file_path: str | None = None
    line_number: int | None = None
    recommendation: str = ""


class SecurityReviewResult(BaseModel):
    """Results from the security review workstream."""
    findings: list[Finding] = Field(default_factory=list)
    dependencies_checked: int = 0
    vulnerable_dependencies: list[str] = Field(default_factory=list)
    summary: str = ""


class ComplexityReviewResult(BaseModel):
    """Results from the complexity review workstream."""
    findings: list[Finding] = Field(default_factory=list)
    average_cyclomatic_complexity: float = 0.0
    high_complexity_functions: list[str] = Field(default_factory=list)
    repeated_code_blocks: list[str] = Field(default_factory=list)
    dead_code_items: list[str] = Field(default_factory=list)
    summary: str = ""


class DocumentationReviewResult(BaseModel):
    """Results from the documentation review workstream."""
    findings: list[Finding] = Field(default_factory=list)
    has_readme: bool = False
    has_api_docs: bool = False
    has_contributing_guide: bool = False
    documentation_coverage: float = 0.0
    relevance_score: float = 0.0
    summary: str = ""


class ReviewRequest(BaseModel):
    """Input for a code review."""
    repo_url: str = Field(description="GitHub repository URL to review")
    branch: str = Field(default="main", description="Branch to review")


class FinalReport(BaseModel):
    """The complete code review report combining all workstreams."""
    repo_url: str
    branch: str
    security: SecurityReviewResult
    complexity: ComplexityReviewResult
    documentation: DocumentationReviewResult
    overall_summary: str = ""
    overall_risk_level: Severity = Severity.INFO
    total_findings: int = 0
