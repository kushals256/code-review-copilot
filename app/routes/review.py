from fastapi import APIRouter, HTTPException

from app.models.schemas import ReviewRequest
from app.services.review_pipeline import ReviewPipeline
from app.services.github import GitHubAuthError

router = APIRouter(prefix="/api/review", tags=["review"])


@router.post("")
async def review_pr(request: ReviewRequest):
    """Review a PR by URL. Set conventions manually or let the system auto-learn them."""
    try:
        pipeline = ReviewPipeline()
        result, post_result = await pipeline.review_pr(
            pr_url=request.pr_url,
            conventions=request.conventions or None,
            auto_learn_conventions=not request.conventions,
            post_to_github=True,
        )
        return {
            "review": result.model_dump(),
            "github": post_result,
        }
    except GitHubAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {e}")


@router.post("/dry-run")
async def review_pr_dry_run(request: ReviewRequest):
    """Review a PR without posting comments to GitHub (preview mode)."""
    try:
        pipeline = ReviewPipeline()
        result, post_result = await pipeline.review_pr(
            pr_url=request.pr_url,
            conventions=request.conventions or None,
            auto_learn_conventions=not request.conventions,
            post_to_github=False,
        )
        return {
            "review": result.model_dump(),
            "github": post_result,
        }
    except GitHubAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review failed: {e}")
