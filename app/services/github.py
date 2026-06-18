import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.config import settings

GITHUB_API = "https://api.github.com"


@dataclass
class PRInfo:
    owner: str
    repo: str
    number: int
    title: str
    body: Optional[str]
    head_sha: str
    base_sha: str
    url: str


@dataclass
class FileChange:
    filename: str
    status: str
    patch: Optional[str]
    additions: int
    deletions: int
    previous_filename: Optional[str] = None

class GitHubAuthError(Exception):
    """Raised when GitHub authentication fails."""
    pass

class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.github_token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    
    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{GITHUB_API}{path}", headers=self.headers, params=params
            )

            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                
                if e.response.status_code == 401:
                    raise GitHubAuthError(
                        "GitHub token is invalid or not configured."
                    )

                elif e.response.status_code == 403:
                    raise ValueError(
                        "GitHub API access forbidden or rate limit exceeded."
                    )
                elif e.response.status_code == 404:
                    raise ValueError(
                        "Repository or pull request not found."
                    )
                raise

            return resp.json()


    async def _post(self, path: str, json: dict) -> Any:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{GITHUB_API}{path}", headers=self.headers, json=json
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def parse_pr_url(url: str) -> tuple[str, str, int]:
        match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", url.strip()
        )
        if not match:
            raise ValueError(f"Invalid GitHub PR URL: {url}")
        return match.group(1), match.group(2), int(match.group(3))

    @staticmethod
    def parse_repo_url(url: str) -> tuple[str, str]:
        match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
        if not match:
            raise ValueError(f"Invalid GitHub repo URL: {url}")
        return match.group(1), match.group(2)

    async def get_pr(self, owner: str, repo: str, number: int) -> PRInfo:
        data = await self._get(f"/repos/{owner}/{repo}/pulls/{number}")
        return PRInfo(
            owner=owner,
            repo=repo,
            number=number,
            title=data["title"],
            body=data.get("body"),
            head_sha=data["head"]["sha"],
            base_sha=data["base"]["sha"],
            url=data["html_url"],
        )

    async def get_pr_files(self, owner: str, repo: str, number: int) -> list[FileChange]:
        files: list[FileChange] = []
        page = 1
        while True:
            batch = await self._get(
                f"/repos/{owner}/{repo}/pulls/{number}/files",
                params={"per_page": 100, "page": page},
            )
            if not batch:
                break
            for f in batch:
                files.append(
                    FileChange(
                        filename=f["filename"],
                        status=f["status"],
                        patch=f.get("patch"),
                        additions=f.get("additions", 0),
                        deletions=f.get("deletions", 0),
                        previous_filename=f.get("previous_filename"),
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return files

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> Optional[str]:
        try:
            data = await self._get(
                f"/repos/{owner}/{repo}/contents/{path}",
                params={"ref": ref},
            )
            if data.get("encoding") == "base64":
                import base64

                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        return None

    async def post_pr_comment(
        self, owner: str, repo: str, number: int, body: str
    ) -> dict:
        return await self._post(
            f"/repos/{owner}/{repo}/issues/{number}/comments", {"body": body}
        )

    async def post_review_comment(
        self,
        owner: str,
        repo: str,
        number: int,
        commit_id: str,
        path: str,
        line: int,
        body: str,
        side: str = "RIGHT",
    ) -> dict:
        payload = {
            "body": body,
            "commit_id": commit_id,
            "path": path,
            "line": line,
            "side": side,
        }
        return await self._post(
            f"/repos/{owner}/{repo}/pulls/{number}/comments", payload
        )

    async def get_merged_prs(
        self, owner: str, repo: str, max_prs: int = 20
    ) -> list[dict]:
        prs: list[dict] = []
        page = 1
        while len(prs) < max_prs:
            batch = await self._get(
                f"/repos/{owner}/{repo}/pulls",
                params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 30, "page": page},
            )
            if not batch:
                break
            for pr in batch:
                if pr.get("merged_at"):
                    prs.append(pr)
                    if len(prs) >= max_prs:
                        break
            if len(batch) < 30:
                break
            page += 1
        return prs

    async def get_pr_review_comments(
        self, owner: str, repo: str, number: int
    ) -> list[dict]:
        return await self._get(f"/repos/{owner}/{repo}/pulls/{number}/comments")
