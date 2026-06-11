from fastapi import APIRouter, HTTPException

from app.models.schemas import ConventionRequest
from app.services.convention_learner import ConventionLearner
from app.services.github import GitHubClient

router = APIRouter(prefix="/api/conventions", tags=["conventions"])


@router.post("/extract")
async def extract_conventions(request: ConventionRequest):
    """Extract team coding conventions from a repository's merged PR history."""
    try:
        github = GitHubClient()
        owner, repo = github.parse_repo_url(request.repo_url)
        learner = ConventionLearner(github)
        result = await learner.extract_conventions(owner, repo, request.max_prs)
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")
