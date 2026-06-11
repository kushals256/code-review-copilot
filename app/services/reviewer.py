import json
import re

from app.config import settings
from app.models.schemas import ReviewComment, ReviewResult, RiskSummary, Severity
from app.services.context_builder import FileContext
from app.services.github import PRInfo
from app.services.llm import get_llm_client, llm_extra_kwargs

SYSTEM_PROMPT = """You are Code Review Copilot, an expert senior engineer who reviews pull requests.

Your job is to catch real issues, explain decisions clearly, and teach junior developers.

For every issue you find, you MUST provide:
1. The specific issue
2. Why it matters in production
3. A concrete suggested fix
4. A plain-English explanation a junior developer can understand without outside research

Severity categories (use exactly one per comment):
- bug: Logic errors, crashes, incorrect behavior
- security: Vulnerabilities, auth issues, data exposure
- performance: Inefficient code, memory leaks, N+1 queries
- style: Naming, formatting, readability (non-blocking)
- suggestion: Improvements that aren't bugs but would help

Rules:
- Only comment on lines that were ADDED or MODIFIED in the diff
- Reference exact line numbers from the new file (RIGHT side of diff)
- Be specific — cite the actual code
- Don't nitpick trivial style unless it violates team conventions
- Prioritize high-impact issues over minor suggestions
- Maximum 15 comments per review

Respond with valid JSON only, no markdown fences."""

REVIEW_SCHEMA = {
    "comments": [
        {
            "file_path": "string",
            "line": "integer (line number in new file)",
            "severity": "bug|security|performance|style|suggestion",
            "issue": "string",
            "why_it_matters": "string",
            "suggested_fix": "string",
            "explanation": "string",
        }
    ],
    "risk_summary": {
        "quality_score": "integer 0-100",
        "highest_risk_changes": [
            {
                "file_path": "string",
                "description": "string",
                "severity": "bug|security|performance|style|suggestion",
                "risk_score": "integer 1-10",
            }
        ],
        "merge_recommendation": "approve|request_changes|comment",
        "merge_rationale": "string",
    },
}


def _build_review_prompt(
    pr: PRInfo,
    contexts: list[FileContext],
    conventions: list[str],
) -> str:
    parts = [
        f"# Pull Request: {pr.title}",
        f"Repository: {pr.owner}/{pr.repo}",
        f"PR #{pr.number}",
        "",
    ]

    if pr.body:
        parts.extend(["## PR Description", pr.body, ""])

    if conventions:
        parts.append("## Team Conventions (apply these during review)")
        for i, rule in enumerate(conventions, 1):
            parts.append(f"{i}. {rule}")
        parts.append("")

    for ctx in contexts:
        parts.append(f"## File: {ctx.filename} (status: {ctx.status})")
        if ctx.imports_and_definitions:
            parts.append("### Imports & Definitions")
            parts.append(ctx.imports_and_definitions)
        parts.append("### Diff")
        parts.append(f"```\n{ctx.diff_summary}\n```")
        if ctx.surrounding_context:
            parts.append("### Surrounding Context")
            parts.append(f"```\n{ctx.surrounding_context}\n```")
        parts.append("")

    parts.append(
        "Analyze this PR and respond with JSON matching this schema:\n"
        + json.dumps(REVIEW_SCHEMA, indent=2)
    )
    return "\n".join(parts)


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    return json.loads(text)


class AIReviewer:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.client = get_llm_client()
        self.model = model or settings.effective_model

    async def review(
        self,
        pr: PRInfo,
        contexts: list[FileContext],
        conventions: list[str] | None = None,
    ) -> ReviewResult:
        prompt = _build_review_prompt(pr, contexts, conventions or [])
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            **llm_extra_kwargs(),
        )

        raw = response.choices[0].message.content or "{}"
        data = _parse_json_response(raw)

        comments = []
        for c in data.get("comments", []):
            try:
                comments.append(
                    ReviewComment(
                        file_path=c["file_path"],
                        line=int(c["line"]),
                        severity=Severity(c["severity"]),
                        issue=c["issue"],
                        why_it_matters=c["why_it_matters"],
                        suggested_fix=c["suggested_fix"],
                        explanation=c["explanation"],
                    )
                )
            except (KeyError, ValueError):
                continue

        rs = data.get("risk_summary", {})
        risk_summary = RiskSummary(
            quality_score=min(100, max(0, int(rs.get("quality_score", 50)))),
            highest_risk_changes=[
                {
                    "file_path": r["file_path"],
                    "description": r["description"],
                    "severity": Severity(r["severity"]),
                    "risk_score": min(10, max(1, int(r.get("risk_score", 5)))),
                }
                for r in rs.get("highest_risk_changes", [])
            ],
            merge_recommendation=rs.get("merge_recommendation", "comment"),
            merge_rationale=rs.get("merge_rationale", "Review completed."),
        )

        return ReviewResult(
            pr_url=pr.url,
            pr_number=pr.number,
            repo=f"{pr.owner}/{pr.repo}",
            comments=comments,
            risk_summary=risk_summary,
            conventions_applied=conventions or [],
        )
