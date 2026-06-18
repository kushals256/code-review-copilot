from app.models.schemas import ReviewResult
from app.services.comment_poster import CommentPoster
from app.services.context_builder import ContextBuilder
from app.services.convention_learner import ConventionLearner
from app.services.diff_parser import parse_patch
from app.services.github import GitHubClient
from app.services.prompt_limits import MAX_FILES, file_change_score, should_skip_file
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
        self.convention_learner = ConventionLearner(self.github)

    def _select_files(self, files: list) -> tuple[list, int]:
        """Pick reviewable files, prioritizing smaller meaningful changes."""
        reviewable = [
            f for f in files
            if f.patch and f.status != "removed" and not should_skip_file(f.filename)
        ]
        skipped = len(files) - len(reviewable)

        reviewable.sort(
            key=lambda f: file_change_score(f.additions, f.deletions),
            reverse=True,
        )

        if len(reviewable) > MAX_FILES:
            skipped += len(reviewable) - MAX_FILES
            reviewable = reviewable[:MAX_FILES]

        return reviewable, skipped

    async def review_pr(
        self,
        pr_url: str,
        conventions: list[str] | None = None,
        auto_learn_conventions: bool = True,
        post_to_github: bool = True,
    ) -> tuple[ReviewResult, dict]:
        owner, repo, number = self.github.parse_pr_url(pr_url)
        pr = await self.github.get_pr(owner, repo, number)
        all_files = await self.github.get_pr_files(owner, repo, number)
        files, skipped_count = self._select_files(all_files)

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
                owner, repo, max_prs=5
            )
            applied_conventions = [r.rule + ": " + r.description for r in extraction.rules]

        result = await self.reviewer.review(
            pr, contexts, applied_conventions, skipped_files=skipped_count
        )
        post_result = await self.comment_poster.post_review(pr, result, post_to_github)

        return result, post_result
