from app.models.schemas import ReviewComment, ReviewResult, Severity
from app.services.github import GitHubClient, PRInfo

SEVERITY_EMOJI = {
    Severity.BUG: "🐛",
    Severity.SECURITY: "🔒",
    Severity.PERFORMANCE: "⚡",
    Severity.STYLE: "🎨",
    Severity.SUGGESTION: "💡",
}

SEVERITY_LABEL = {
    Severity.BUG: "Bug",
    Severity.SECURITY: "Security",
    Severity.PERFORMANCE: "Performance",
    Severity.STYLE: "Style",
    Severity.SUGGESTION: "Suggestion",
}


def format_inline_comment(comment: ReviewComment) -> str:
    emoji = SEVERITY_EMOJI.get(comment.severity, "📝")
    label = SEVERITY_LABEL.get(comment.severity, comment.severity.value)
    return (
        f"{emoji} **[{label}]** {comment.issue}\n\n"
        f"**Why it matters:** {comment.why_it_matters}\n\n"
        f"**Suggested fix:**\n```\n{comment.suggested_fix}\n```\n\n"
        f"**Learn more:** {comment.explanation}\n\n"
        f"---\n*Reviewed by Code Review Copilot*"
    )


def format_risk_summary(result: ReviewResult) -> str:
    rs = result.risk_summary
    rec_emoji = {
        "approve": "✅",
        "request_changes": "❌",
        "comment": "💬",
    }.get(rs.merge_recommendation, "💬")

    score_bar = "█" * (rs.quality_score // 10) + "░" * (10 - rs.quality_score // 10)

    lines = [
        "## 🤖 Code Review Copilot — Risk Summary",
        "",
        f"### Quality Score: {rs.quality_score}/100",
        f"`{score_bar}` {rs.quality_score}%",
        "",
        f"### Merge Recommendation: {rec_emoji} **{rs.merge_recommendation.replace('_', ' ').title()}**",
        rs.merge_rationale,
        "",
    ]

    if rs.highest_risk_changes:
        lines.append("### Highest-Risk Changes")
        for item in rs.highest_risk_changes:
            emoji = SEVERITY_EMOJI.get(item.severity, "⚠️")
            lines.append(
                f"- {emoji} **`{item.file_path}`** (risk {item.risk_score}/10): {item.description}"
            )
        lines.append("")

    if result.conventions_applied:
        lines.append("### Team Conventions Applied")
        for rule in result.conventions_applied:
            lines.append(f"- {rule}")
        lines.append("")

    lines.extend([
        f"### Review Stats",
        f"- **{len(result.comments)}** inline comments posted",
        f"- Severities: {', '.join(_count_severities(result.comments))}",
        "",
        "---",
        "*Automated review by Code Review Copilot. Senior engineers should still review architecture and business logic.*",
    ])
    return "\n".join(lines)


def _count_severities(comments: list[ReviewComment]) -> list[str]:
    counts: dict[str, int] = {}
    for c in comments:
        counts[c.severity.value] = counts.get(c.severity.value, 0) + 1
    return [f"{k}: {v}" for k, v in sorted(counts.items())]


class CommentPoster:
    def __init__(self, github: GitHubClient):
        self.github = github

    async def post_review(
        self, pr: PRInfo, result: ReviewResult, post_to_github: bool = True
    ) -> dict:
        if not post_to_github:
            return {"summary": format_risk_summary(result), "comments_posted": 0}

        summary_body = format_risk_summary(result)
        await self.github.post_pr_comment(
            pr.owner, pr.repo, pr.number, summary_body
        )

        posted = 0
        errors: list[str] = []
        for comment in result.comments:
            try:
                await self.github.post_review_comment(
                    owner=pr.owner,
                    repo=pr.repo,
                    number=pr.number,
                    commit_id=pr.head_sha,
                    path=comment.file_path,
                    line=comment.line,
                    body=format_inline_comment(comment),
                )
                posted += 1
            except Exception as e:
                errors.append(f"{comment.file_path}:{comment.line} — {e}")

        return {
            "summary_posted": True,
            "comments_posted": posted,
            "comments_total": len(result.comments),
            "errors": errors,
        }
