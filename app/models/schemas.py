from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    SUGGESTION = "suggestion"


class ReviewComment(BaseModel):
    file_path: str
    line: int
    severity: Severity
    issue: str
    why_it_matters: str
    suggested_fix: str
    explanation: str


class RiskItem(BaseModel):
    file_path: str
    description: str
    severity: Severity
    risk_score: int = Field(ge=1, le=10)


class RiskSummary(BaseModel):
    quality_score: int = Field(ge=0, le=100)
    highest_risk_changes: list[RiskItem]
    merge_recommendation: str
    merge_rationale: str


class ReviewResult(BaseModel):
    pr_url: str
    pr_number: int
    repo: str
    comments: list[ReviewComment]
    risk_summary: RiskSummary
    conventions_applied: list[str] = []


class ConventionRule(BaseModel):
    rule: str
    description: str
    examples: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)


class ConventionExtractionResult(BaseModel):
    repo: str
    rules: list[ConventionRule]
    prs_analyzed: int


class ReviewRequest(BaseModel):
    pr_url: str
    conventions: list[str] = []


class ConventionRequest(BaseModel):
    repo_url: str
    max_prs: int = Field(default=20, ge=1, le=100)
