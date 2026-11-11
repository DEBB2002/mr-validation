from abc import ABC, abstractmethod
from typing import List, Optional
from src.schemas import Violation, ReviewResult


class VCSProvider(ABC):
    """
    Abstract Base Class defining the contract for Version Control System (VCS) integrations
    such as GitLab and GitHub.
    """

    def __init__(self, token: str, project_id: str, base_url: Optional[str] = None):
        self.token = token
        self.project_id = project_id
        self.base_url = base_url

    @abstractmethod
    def get_mr_diff(self, mr_id: str) -> str:
        """
        Fetch the unified git diff for a specific Merge Request / Pull Request.

        :param mr_id: The identifier or IID of the MR / PR.
        :return: Raw unified git diff string.
        """
        pass

    @abstractmethod
    def post_summary_comment(self, mr_id: str, report: ReviewResult) -> bool:
        """
        Publish a high-level summary comment on the Merge Request discussion thread.

        :param mr_id: The identifier or IID of the MR / PR.
        :param report: The final architectural ReviewResult.
        :return: True if comment posted successfully, False otherwise.
        """
        pass

    @abstractmethod
    def post_inline_comments(self, mr_id: str, violations: List[Violation]) -> int:
        """
        Publish inline review comments directly on affected diff lines for detected violations.

        :param mr_id: The identifier or IID of the MR / PR.
        :param violations: List of detected architectural violations.
        :return: Number of inline comments successfully posted.
        """
        pass

