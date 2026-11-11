"""VCS Integration Package for Merge Request & Pull Request Platforms."""

from .vcs_base import VCSProvider
from .gitlab_provider import GitLabProvider
from .github_provider import GitHubProvider

__all__ = ["VCSProvider", "GitLabProvider", "GitHubProvider"]

