import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.services.review_pipeline import ReviewPipeline

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
):
    """Handle GitHub webhook events. Triggers review on pull_request opened/synchronize."""
    body = await request.body()

    if settings.github_webhook_secret:
        if not _verify_signature(body, x_hub_signature_256, settings.github_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()

    if x_github_event == "ping":
        return {"status": "pong"}

    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "action": action}

    pr_data = payload.get("pull_request", {})
    pr_url = pr_data.get("html_url")
    if not pr_url:
        raise HTTPException(status_code=400, detail="No PR URL in payload")

    pipeline = ReviewPipeline()
    result, post_result = await pipeline.review_pr(
        pr_url=pr_url,
        auto_learn_conventions=True,
        post_to_github=True,
    )

    return {
        "status": "reviewed",
        "pr": pr_url,
        "comments": len(result.comments),
        "quality_score": result.risk_summary.quality_score,
        "github": post_result,
    }
