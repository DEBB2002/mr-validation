"""
GitLab VCS Provider Implementation.
Interacts with GitLab REST API v4 for:
- Fetching MR raw diffs
- Posting idempotent MR summary notes with architectural reports
- Posting line-level inline discussions and suggestions on MR diffs
"""

import json
import logging
import urllib.parse
from typing import List, Optional, Dict, Any

import requests
from src.schemas import Violation, ReviewResult
from .vcs_base import VCSProvider

logger = logging.getLogger(__name__)

SUMMARY_MARKER = "<!-- mr-validation-summary-marker -->"


class GitLabProvider(VCSProvider):
    """
    GitLab implementation of VCSProvider for GitLab Merge Requests.
    Supports Personal Access Tokens, OAuth2 Tokens, Project Access Tokens, and CI Job Tokens.
    """

    def __init__(
        self,
        token: str,
        project_id: str,
        base_url: str = "https://gitlab.com",
        auth_type: Optional[str] = None,
    ):
        super().__init__(token=token, project_id=str(project_id), base_url=base_url)
        quoted_project_id = urllib.parse.quote(str(project_id), safe="")
        self.api_base = f"{self.base_url.rstrip('/')}/api/v4/projects/{quoted_project_id}"
        
        # Configure headers based on token type
        self.headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if auth_type == "job_token" or token.startswith("glcbt-"):
            self.headers["JOB-TOKEN"] = token
        elif auth_type == "bearer" or (len(token) == 64 and all(c in "0123456789abcdefABCDEF" for c in token)):
            self.headers["Authorization"] = f"Bearer {token}"
        else:
            self.headers["PRIVATE-TOKEN"] = token

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        response = requests.request(
            method=method,
            url=url,
            headers=self.headers,
            json=data,
            params=params,
            timeout=30,
        )
        return response

    def get_mr_diff(self, mr_id: str) -> str:
        """
        Fetches the unified diff for a GitLab MR via GET /merge_requests/:mr_iid/diffs.
        """
        response = self._request(f"merge_requests/{mr_id}/diffs")
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch diffs for MR !{mr_id} (HTTP {response.status_code}): {response.text}"
            )
        diff_items = response.json()
        diff_chunks = []
        for item in diff_items:
            old_p = item.get("old_path", "")
            new_p = item.get("new_path", "")
            diff_body = item.get("diff", "")
            diff_chunks.append(f"--- a/{old_p}\n+++ b/{new_p}\n{diff_body}")
        return "\n".join(diff_chunks)

    def get_mr_details(self, mr_id: str) -> Dict[str, Any]:
        """
        Retrieves MR metadata including diff_refs (base_sha, head_sha, start_sha).
        """
        response = self._request(f"merge_requests/{mr_id}")
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch MR !{mr_id} details (HTTP {response.status_code}): {response.text}"
            )
        return response.json()

    def format_summary_markdown(self, report: ReviewResult) -> str:
        """
        Builds the markdown payload for the high-level MR summary comment.
        """
        status_badge = "❌ **FAILED**" if not report.passed else "✅ **PASSED**"
        if report.passed and any(v.severity.upper() == "WARNING" for v in report.violations):
            status_badge = "⚠️ **PASSED WITH WARNINGS**"

        lines = [
            SUMMARY_MARKER,
            "## 🏛️ Merge Request Architectural Compliance Review",
            f"**Review Status:** {status_badge}",
            "",
            "### 📋 Executive Summary",
            report.summary.strip(),
            "",
        ]

        if report.violations:
            critical_count = sum(1 for v in report.violations if v.severity.upper() == "CRITICAL")
            warning_count = sum(1 for v in report.violations if v.severity.upper() == "WARNING")
            
            lines.append(f"### ⚠️ Detected Architectural Violations ({len(report.violations)})")
            lines.append(f"**Critical Issues (Blockers):** `{critical_count}` | **Advisory Warnings:** `{warning_count}`\n")
            lines.append("| Severity | File & Location | Architectural Rule | Details & Recommendation |")
            lines.append("|---|---|---|---|")

            for v in report.violations:
                sev_icon = "🔴 `CRITICAL`" if v.severity.upper() == "CRITICAL" else "🟡 `WARNING`"
                loc = f"`{v.file_path}:{v.line_number}`" if v.line_number else f"`{v.file_path}`"
                fix_text = f"<br/>💡 **Suggested Fix:** {v.suggested_fix}" if v.suggested_fix else ""
                lines.append(f"| {sev_icon} | {loc} | **{v.rule_violated}** | {v.explanation}{fix_text} |")
            lines.append("")
        else:
            lines.append("### ✅ Compliance Verified")
            lines.append("No architectural violations found. All layer boundaries, lifecycle bounds, and conventions are satisfied.\n")

        if report.usage:
            model_used = getattr(report.usage, "model_name", None) or "gemini-3.5-flash-lite"
            lines.append("<details>")
            lines.append("<summary>📊 <b>LLM Inference & Token Usage Metrics</b></summary>\n")
            lines.append(f"- **Engine Model:** `{model_used}`")
            lines.append(f"- **Input Tokens:** `{report.usage.input_tokens:,}`")
            lines.append(f"- **Output Tokens:** `{report.usage.output_tokens:,}`")
            lines.append(f"- **Total Tokens:** `{report.usage.total_tokens:,}`")
            lines.append("</details>\n")

        lines.append("---")
        lines.append("*Automated review generated by [mr-validation](https://gitlab.com/debbiswas2002/mr-validation)*")

        return "\n".join(lines)

    def post_summary_comment(self, mr_id: str, report: ReviewResult) -> bool:
        """
        Publishes or updates the high-level summary note on the MR.
        Idempotent: updates existing bot note if already present.
        """
        body_text = self.format_summary_markdown(report)

        # 1. Check for existing bot note
        existing_note_id: Optional[int] = None
        try:
            notes_resp = self._request(f"merge_requests/{mr_id}/notes", params={"per_page": 50})
            if notes_resp.status_code == 200:
                for note in notes_resp.json():
                    if SUMMARY_MARKER in note.get("body", "") and not note.get("system", False):
                        existing_note_id = note.get("id")
                        break
        except Exception as e:
            logger.warning(f"Could not list MR notes to check for existing summary: {e}")

        # 2. Update existing note or create a new one
        if existing_note_id:
            logger.info(f"Updating existing review comment note ID {existing_note_id} on MR !{mr_id}")
            put_resp = self._request(
                f"merge_requests/{mr_id}/notes/{existing_note_id}",
                method="PUT",
                data={"body": body_text},
            )
            return put_resp.status_code in (200, 201)
        else:
            logger.info(f"Creating new review comment note on MR !{mr_id}")
            post_resp = self._request(
                f"merge_requests/{mr_id}/notes",
                method="POST",
                data={"body": body_text},
            )
            return post_resp.status_code in (200, 201)

    def post_inline_comments(
        self,
        mr_id: str,
        violations: List[Violation],
        diff_refs: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Publishes inline discussion comments at specific diff line positions via GitLab Discussions API.
        Includes single-click suggestion blocks where available.

        :param mr_id: Merge Request IID
        :param violations: List of architectural violations detected
        :param diff_refs: Dict containing base_sha, head_sha, start_sha (fetched if None)
        :return: Count of successfully posted comments
        """
        if not violations:
            return 0

        # Fetch diff_refs if not provided
        if not diff_refs:
            try:
                mr_details = self.get_mr_details(mr_id)
                diff_refs = mr_details.get("diff_refs")
            except Exception as e:
                logger.error(f"Failed to fetch diff_refs for MR !{mr_id}: {e}")
                return 0

        if not diff_refs or not diff_refs.get("head_sha"):
            logger.error(f"No valid diff_refs found for MR !{mr_id}; cannot anchor inline comments.")
            return 0

        posted_count = 0

        for v in violations:
            if not v.line_number or v.line_number <= 0:
                continue

            sev_badge = "🔴 `[CRITICAL]`" if v.severity.upper() == "CRITICAL" else "🟡 `[WARNING]`"
            
            body_parts = [
                f"### {sev_badge} Architectural Violation: {v.rule_violated}",
                "",
                f"**Explanation:** {v.explanation}",
            ]

            if v.suggested_fix:
                body_parts.extend([
                    "",
                    "**Suggested Action:**",
                    "```suggestion",
                    f"{v.suggested_fix}",
                    "```",
                ])

            body_text = "\n".join(body_parts)

            pos_payload = {
                "base_sha": diff_refs.get("base_sha"),
                "start_sha": diff_refs.get("start_sha"),
                "head_sha": diff_refs.get("head_sha"),
                "position_type": "text",
                "new_path": v.file_path.replace("\\", "/"),
                "new_line": v.line_number,
            }

            discussion_data = {
                "body": body_text,
                "position": pos_payload,
            }

            resp = self._request(
                f"merge_requests/{mr_id}/discussions",
                method="POST",
                data=discussion_data,
            )

            if resp.status_code in (200, 201):
                posted_count += 1
                logger.info(f"Posted inline comment on {v.file_path}:{v.line_number}")
            else:
                logger.warning(
                    f"GitLab rejected inline position for {v.file_path}:{v.line_number} "
                    f"(HTTP {resp.status_code}): {resp.text}. Falling back to general note."
                )
                # Fallback to general note referencing the file and line
                fallback_data = {
                    "body": f"⚠️ **[{v.severity}] {v.rule_violated}** on `{v.file_path}:{v.line_number}`:\n\n{v.explanation}\n\n*Fix:* {v.suggested_fix}"
                }
                fb_resp = self._request(f"merge_requests/{mr_id}/notes", method="POST", data=fallback_data)
                if fb_resp.status_code in (200, 201):
                    posted_count += 1

        return posted_count
