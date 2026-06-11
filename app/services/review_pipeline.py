from app.models.schemas import ReviewResult
from app.services.comment_poster import CommentPoster
from app.services.context_builder import ContextBuilder
from app.services.convention_learner import ConventionLearner
from app.services.diff_parser import parse_patch
from app.services.github import GitHubClient
from app.services.reviewer import AIReviewer


class ReviewPipeline:
    def __init__(
        self,
        github: GitHubClient | None = None,
        reviewer: AIReviewer | None = None,
        convention_learner: ConventionLearner | None = None,
    ):
        self.github = github or GitHubClient()
        self.reviewer = reviewer or AIReviewer()
        self.context_builder = ContextBuilder(self.github)
        self.comment_poster = CommentPoster(self.github)
        self.convention_learner = convention_learner or ConventionLearner(self.github)

    async def review_pr(
        self,
        pr_url: str,
        conventions: list[str] | None = None,
        auto_learn_conventions: bool = True,
        post_to_github: bool = True,
    ) -> tuple[ReviewResult, dict]:
        owner, repo, number = self.github.parse_pr_url(pr_url)
        pr = await self.github.get_pr(owner, repo, number)
        files = await self.github.get_pr_files(owner, repo, number)

        parsed_files = []
        for f in files:
            if f.patch:
                parsed_files.append(parse_patch(f.filename, f.patch))

        contexts = await self.context_builder.build_contexts(
            owner, repo, pr.head_sha, files, parsed_files
        )

        applied_conventions = list(conventions or [])
        if auto_learn_conventions and not applied_conventions:
            extraction = await self.convention_learner.extract_conventions(
                owner, repo, max_prs=10
            )
            applied_conventions = [r.rule + ": " + r.description for r in extraction.rules]

        result = await self.reviewer.review(pr, contexts, applied_conventions)
        post_result = await self.comment_poster.post_review(pr, result, post_to_github)

        return result, post_result
