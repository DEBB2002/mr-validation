from typing import List, Optional
from src.schemas import Violation, ReviewResult
from .vcs_base import VCSProvider


class GitLabProvider(VCSProvider):
    """
    GitLab implementation of VCSProvider for GitLab Merge Requests.
    Interacts with GitLab REST API v4 to fetch diffs and post discussion notes.
    """

    def __init__(self, token: str, project_id: str, base_url: str = "https://gitlab.com"):
        super().__init__(token=token, project_id=project_id, base_url=base_url)
        self.api_url = f"{self.base_url.rstrip('/')}/api/v4/projects/{self.project_id}"

    def get_mr_diff(self, mr_id: str) -> str:
        """
        Fetches the raw diff for GitLab MR via GET /projects/:id/merge_requests/:mr_iid/raw_diff.
        (Placeholder stub for Phase 2 integration).
        """
        # Phase 2 implementation will use httpx or python-gitlab to query self.api_url
        raise NotImplementedError("GitLabProvider.get_mr_diff will be implemented in Phase 2.")

    def post_summary_comment(self, mr_id: str, report: ReviewResult) -> bool:
        """
        Posts high-level markdown review summary to GitLab MR notes thread.
        (Placeholder stub for Phase 2 integration).
        """
        raise NotImplementedError("GitLabProvider.post_summary_comment will be implemented in Phase 2.")

    def post_inline_comments(self, mr_id: str, violations: List[Violation]) -> int:
        """
        Posts inline discussion comments at specific diff line positions via GitLab Discussions API.
        (Placeholder stub for Phase 2 integration).
        """
        raise NotImplementedError("GitLabProvider.post_inline_comments will be implemented in Phase 2.")

