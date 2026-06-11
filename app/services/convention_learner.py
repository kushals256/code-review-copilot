import json
import re

from app.config import settings
from app.models.schemas import ConventionExtractionResult, ConventionRule
from app.services.github import GitHubClient
from app.services.llm import get_llm_client, llm_extra_kwargs

EXTRACTION_PROMPT = """You are analyzing code review history from a GitHub repository to extract team-specific coding conventions.

Look at the review comments left on merged pull requests and identify recurring patterns, rules, and preferences the team enforces.

Extract at least 3 actionable conventions. Each convention should be:
- Specific enough to apply during automated code review
- Based on evidence from the review comments (not generic best practices)
- Written as a clear rule a linter or reviewer could check

Respond with valid JSON only:
{
  "rules": [
    {
      "rule": "short rule name",
      "description": "what the team expects and why",
      "examples": ["example from review comments"],
      "confidence": 0.0 to 1.0
    }
  ]
}"""


class ConventionLearner:
    def __init__(
        self,
        github: GitHubClient | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.github = github or GitHubClient()
        self.client = get_llm_client()
        self.model = model or settings.effective_model

    async def extract_conventions(
        self, owner: str, repo: str, max_prs: int = 20
    ) -> ConventionExtractionResult:
        merged_prs = await self.github.get_merged_prs(owner, repo, max_prs)

        all_review_comments: list[dict] = []
        for pr in merged_prs:
            comments = await self.github.get_pr_review_comments(
                owner, repo, pr["number"]
            )
            for c in comments:
                all_review_comments.append(
                    {
                        "pr": pr["number"],
                        "file": c.get("path", ""),
                        "body": c.get("body", ""),
                    }
                )

        if not all_review_comments:
            return ConventionExtractionResult(
                repo=f"{owner}/{repo}",
                rules=_default_conventions(),
                prs_analyzed=len(merged_prs),
            )

        comment_text = "\n\n".join(
            f"PR #{c['pr']} — {c['file']}:\n{c['body']}"
            for c in all_review_comments[:100]
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Repository: {owner}/{repo}\n"
                        f"Merged PRs analyzed: {len(merged_prs)}\n"
                        f"Review comments collected: {len(all_review_comments)}\n\n"
                        f"## Review Comments\n{comment_text}"
                    ),
                },
            ],
            temperature=0.3,
            **llm_extra_kwargs(),
        )

        raw = response.choices[0].message.content or "{}"
        text = raw.strip()
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
        data = json.loads(text)

        rules = []
        for r in data.get("rules", []):
            try:
                rules.append(
                    ConventionRule(
                        rule=r["rule"],
                        description=r["description"],
                        examples=r.get("examples", []),
                        confidence=float(r.get("confidence", 0.7)),
                    )
                )
            except (KeyError, ValueError):
                continue

        if len(rules) < 3:
            rules.extend(_default_conventions()[: 3 - len(rules)])

        return ConventionExtractionResult(
            repo=f"{owner}/{repo}",
            rules=rules,
            prs_analyzed=len(merged_prs),
        )


def _default_conventions() -> list[ConventionRule]:
    return [
        ConventionRule(
            rule="Descriptive variable names",
            description="Use clear, descriptive names instead of single-letter variables (except loop indices).",
            examples=["Rename `x` to `userCount`"],
            confidence=0.6,
        ),
        ConventionRule(
            rule="Error handling required",
            description="All async operations and API calls must have proper error handling with meaningful messages.",
            examples=["Wrap API calls in try/catch blocks"],
            confidence=0.6,
        ),
        ConventionRule(
            rule="No hardcoded secrets",
            description="Never commit API keys, passwords, or tokens directly in source code. Use environment variables.",
            examples=["Move API key to .env file"],
            confidence=0.8,
        ),
    ]
