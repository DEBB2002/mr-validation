from typing import List, Optional
from src.schemas import Violation, ReviewResult
from .vcs_base import VCSProvider


class GitHubProvider(VCSProvider):
    """
    GitHub implementation of VCSProvider for GitHub Pull Requests.
    Interacts with GitHub REST API v3 to fetch diffs and post PR review comments.
    """

    def __init__(self, token: str, project_id: str, base_url: str = "https://api.github.com"):
        super().__init__(token=token, project_id=project_id, base_url=base_url)
        self.api_url = f"{self.base_url.rstrip('/')}/repos/{self.project_id}"

    def get_mr_diff(self, mr_id: str) -> str:
        """
        Fetches the PR diff using GitHub API with 'Accept: application/vnd.github.v3.diff'.
        (Placeholder stub for Phase 2 integration).
        """
        # Phase 2 implementation will fetch raw PR diff via GitHub API
        raise NotImplementedError("GitHubProvider.get_mr_diff will be implemented in Phase 2.")

    def post_summary_comment(self, mr_id: str, report: ReviewResult) -> bool:
        """
        Submits top-level PR review summary via POST /repos/:owner/:repo/pulls/:pull_number/reviews.
        (Placeholder stub for Phase 2 integration).
        """
        raise NotImplementedError("GitHubProvider.post_summary_comment will be implemented in Phase 2.")

    def post_inline_comments(self, mr_id: str, violations: List[Violation]) -> int:
        """
        Submits line-specific PR review comments via GitHub Pull Requests Review Comments API.
        (Placeholder stub for Phase 2 integration).
        """
        raise NotImplementedError("GitHubProvider.post_inline_comments will be implemented in Phase 2.")

