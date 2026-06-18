import json

from app.config import settings
from app.models.schemas import ReviewComment, ReviewResult, RiskSummary, Severity
from app.services.context_builder import FileContext
from app.services.github import PRInfo
from app.services.json_parser import parse_llm_json
from app.services.llm import get_llm_client, llm_extra_kwargs
from app.services.prompt_limits import (
    MAX_CONVENTION_RULES,
    MAX_PR_BODY_CHARS,
    MAX_TOTAL_PROMPT_CHARS,
    truncate_text,
)

BASE_RULES = """You are Code Review Copilot, a senior engineer reviewing pull requests.
Severity tags: bug, security, performance, style, suggestion.
Only comment on ADDED/MODIFIED lines (RIGHT side of diff).
Return valid JSON only — no markdown fences.
Keep every string under 120 characters. One short sentence per field."""

RISK_SCHEMA = {
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
}

COMMENTS_SCHEMA = {
    "comments": [
        {
            "file_path": "string",
            "line": "integer",
            "severity": "bug|security|performance|style|suggestion",
            "issue": "string",
            "why_it_matters": "string",
            "suggested_fix": "string",
            "explanation": "string",
        }
    ]
}

FILES_PER_BATCH = 4
MAX_COMMENTS_PER_BATCH = 3
MAX_TOTAL_COMMENTS = 8


def _file_block(ctx: FileContext) -> str:
    parts = [f"## {ctx.filename} ({ctx.status})"]
    if ctx.imports_and_definitions:
        parts.extend(["Imports:", ctx.imports_and_definitions])
    parts.extend(["Diff:", f"```\n{ctx.diff_summary}\n```"])
    if ctx.surrounding_context:
        parts.extend(["Context:", f"```\n{ctx.surrounding_context}\n```"])
    return "\n".join(parts)


def _pr_header(pr: PRInfo, conventions: list[str], skipped_files: int) -> str:
    parts = [
        f"PR: {pr.title}",
        f"Repo: {pr.owner}/{pr.repo} #{pr.number}",
    ]
    if skipped_files:
        parts.append(f"({skipped_files} files skipped — lock/binary/limit)")
    if pr.body:
        parts.append(f"Description: {truncate_text(pr.body, 800)}")
    if conventions:
        rules = "; ".join(conventions[:MAX_CONVENTION_RULES])
        parts.append(f"Conventions: {rules}")
    return "\n".join(parts)


def _fit_contexts(contexts: list[FileContext], budget: int) -> list[FileContext]:
    included: list[FileContext] = []
    used = 0
    for ctx in contexts:
        block = _file_block(ctx)
        if used + len(block) > budget and included:
            break
        if len(block) > budget and not included:
            ctx = FileContext(
                filename=ctx.filename,
                status=ctx.status,
                full_content=ctx.full_content,
                diff_summary=truncate_text(ctx.diff_summary, budget // 2),
                surrounding_context="",
                imports_and_definitions=ctx.imports_and_definitions,
            )
            block = _file_block(ctx)
        included.append(ctx)
        used += len(block)
    return included


def _parse_comments(raw: list) -> list[ReviewComment]:
    comments: list[ReviewComment] = []
    for c in raw:
        try:
            comments.append(
                ReviewComment(
                    file_path=c["file_path"],
                    line=int(c["line"]),
                    severity=Severity(c["severity"]),
                    issue=str(c["issue"])[:200],
                    why_it_matters=str(c["why_it_matters"])[:200],
                    suggested_fix=str(c["suggested_fix"])[:200],
                    explanation=str(c["explanation"])[:200],
                )
            )
        except (KeyError, ValueError):
            continue
    return comments


def _parse_risk_summary(rs: dict) -> RiskSummary:
    return RiskSummary(
        quality_score=min(100, max(0, int(rs.get("quality_score", 50)))),
        highest_risk_changes=[
            {
                "file_path": r["file_path"],
                "description": r["description"],
                "severity": Severity(r["severity"]),
                "risk_score": min(10, max(1, int(r.get("risk_score", 5)))),
            }
            for r in rs.get("highest_risk_changes", [])[:5]
        ],
        merge_recommendation=rs.get("merge_recommendation", "comment"),
        merge_rationale=str(rs.get("merge_rationale", "Review completed."))[:300],
    )


class AIReviewer:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.client = get_llm_client()
        self.model = model or settings.effective_model

    async def _chat(self, system: str, user: str, max_tokens: int = 1024) -> dict:
        extra = llm_extra_kwargs()
        extra["max_tokens"] = max_tokens
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            **extra,
        )
        raw = response.choices[0].message.content or "{}"
        return parse_llm_json(raw)

    async def _fetch_risk_summary(
        self, pr: PRInfo, contexts: list[FileContext], conventions: list[str], skipped: int
    ) -> RiskSummary:
        file_list = "\n".join(
            f"- {ctx.filename} ({ctx.status})" for ctx in contexts[:30]
        )
        prompt = (
            f"{_pr_header(pr, conventions, skipped)}\n\n"
            f"Changed files:\n{file_list}\n\n"
            f"Return JSON risk summary (max 3 risk items):\n"
            f"{json.dumps(RISK_SCHEMA)}"
        )
        data = await self._chat(
            BASE_RULES + " Output risk summary JSON only.",
            prompt,
            max_tokens=800,
        )
        return _parse_risk_summary(data)

    async def _fetch_comments_batch(
        self,
        pr: PRInfo,
        batch: list[FileContext],
        conventions: list[str],
        batch_num: int,
        total_batches: int,
    ) -> list[ReviewComment]:
        files_text = "\n\n".join(_file_block(ctx) for ctx in batch)
        prompt = (
            f"{_pr_header(pr, conventions, 0)}\n"
            f"Batch {batch_num}/{total_batches}\n\n"
            f"{files_text}\n\n"
            f"Find up to {MAX_COMMENTS_PER_BATCH} issues in these files only.\n"
            f"Return JSON:\n{json.dumps(COMMENTS_SCHEMA)}"
        )
        data = await self._chat(
            BASE_RULES + f" Max {MAX_COMMENTS_PER_BATCH} comments. Short strings only.",
            prompt,
            max_tokens=1500,
        )
        return _parse_comments(data.get("comments", []))

    async def review(
        self,
        pr: PRInfo,
        contexts: list[FileContext],
        conventions: list[str] | None = None,
        skipped_files: int = 0,
    ) -> ReviewResult:
        conventions = conventions or []
        contexts = _fit_contexts(contexts, MAX_TOTAL_PROMPT_CHARS // 2)

        # Phase 1: small risk summary call
        risk_summary = await self._fetch_risk_summary(
            pr, contexts, conventions, skipped_files
        )

        # Phase 2: batched comment calls (small outputs each)
        all_comments: list[ReviewComment] = []
        batches = [
            contexts[i : i + FILES_PER_BATCH]
            for i in range(0, len(contexts), FILES_PER_BATCH)
        ]
        if not batches:
            batches = [[]]

        for idx, batch in enumerate(batches, 1):
            if not batch or len(all_comments) >= MAX_TOTAL_COMMENTS:
                break
            batch_comments = await self._fetch_comments_batch(
                pr, batch, conventions, idx, len(batches)
            )
            all_comments.extend(batch_comments[:MAX_TOTAL_COMMENTS - len(all_comments)])

        return ReviewResult(
            pr_url=pr.url,
            pr_number=pr.number,
            repo=f"{pr.owner}/{pr.repo}",
            comments=all_comments,
            risk_summary=risk_summary,
            conventions_applied=conventions,
        )
