"""
Unit tests for GitLabProvider (GitLab MR Notes & Inline Discussions).
"""

from unittest.mock import MagicMock, patch
from src.schemas import ReviewResult, Violation, TokenUsage
from src.integrations.gitlab_provider import GitLabProvider, SUMMARY_MARKER


def test_format_summary_markdown():
    provider = GitLabProvider(token="mock_token", project_id="12345")

    report_failed = ReviewResult(
        passed=False,
        summary="Presentation layer boundary breach.",
        violations=[
            Violation(
                file_path="app/src/main/java/com/example/ui/MainActivity.kt",
                line_number=20,
                rule_violated="Presentation Boundaries",
                severity="CRITICAL",
                explanation="Activity querying database directly.",
                suggested_fix="Delegate to UseCase.",
            )
        ],
        usage=TokenUsage(input_tokens=1000, output_tokens=200, total_tokens=1200),
    )

    md = provider.format_summary_markdown(report_failed)
    assert SUMMARY_MARKER in md
    assert "FAILED" in md
    assert "Presentation Boundaries" in md
    assert "MainActivity.kt:20" in md
    assert "1,200" in md


@patch("src.integrations.gitlab_provider.requests.request")
def test_post_summary_comment_creates_new_note(mock_request):
    # Mock GET notes returns empty list -> POST new note
    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.json.return_value = []

    mock_post = MagicMock()
    mock_post.status_code = 201
    mock_post.json.return_value = {"id": 999}

    mock_request.side_effect = [mock_get, mock_post]

    provider = GitLabProvider(token="mock_token", project_id="12345")
    report = ReviewResult(passed=True, summary="All clean.", violations=[])

    success = provider.post_summary_comment(mr_id="42", report=report)
    assert success is True
    assert mock_request.call_count == 2
    # Verify second call was POST to merge_requests/42/notes
    assert mock_request.call_args_list[1][1]["method"] == "POST"
    assert "merge_requests/42/notes" in mock_request.call_args_list[1][1]["url"]


@patch("src.integrations.gitlab_provider.requests.request")
def test_post_summary_comment_updates_existing_note(mock_request):
    # Mock GET notes returns existing bot note -> PUT update note
    mock_get = MagicMock()
    mock_get.status_code = 200
    mock_get.json.return_value = [
        {"id": 888, "body": f"Old note {SUMMARY_MARKER}", "system": False}
    ]

    mock_put = MagicMock()
    mock_put.status_code = 200
    mock_put.json.return_value = {"id": 888}

    mock_request.side_effect = [mock_get, mock_put]

    provider = GitLabProvider(token="mock_token", project_id="12345")
    report = ReviewResult(passed=True, summary="Updated report.", violations=[])

    success = provider.post_summary_comment(mr_id="42", report=report)
    assert success is True
    assert mock_request.call_count == 2
    assert mock_request.call_args_list[1][1]["method"] == "PUT"
    assert "merge_requests/42/notes/888" in mock_request.call_args_list[1][1]["url"]


@patch("src.integrations.gitlab_provider.requests.request")
def test_post_inline_comments(mock_request):
    # Mock MR details response to get diff_refs
    mock_mr_details = MagicMock()
    mock_mr_details.status_code = 200
    mock_mr_details.json.return_value = {
        "diff_refs": {
            "base_sha": "base123",
            "start_sha": "start123",
            "head_sha": "head123",
        }
    }

    # Mock discussions POST
    mock_post_disc = MagicMock()
    mock_post_disc.status_code = 201
    mock_post_disc.json.return_value = {"id": "disc1"}

    mock_request.side_effect = [mock_mr_details, mock_post_disc]

    provider = GitLabProvider(token="mock_token", project_id="12345")
    violations = [
        Violation(
            file_path="app/src/main/java/com/example/ui/TestViewModel.kt",
            line_number=25,
            rule_violated="Lifecycle Leaks",
            severity="CRITICAL",
            explanation="Context leaked.",
            suggested_fix="Remove context.",
        )
    ]

    count = provider.post_inline_comments(mr_id="42", violations=violations)
    assert count == 1
    assert mock_request.call_count == 2

    # Check discussion payload
    disc_call_args = mock_request.call_args_list[1][1]
    assert disc_call_args["method"] == "POST"
    assert "merge_requests/42/discussions" in disc_call_args["url"]
    pos = disc_call_args["json"]["position"]
    assert pos["base_sha"] == "base123"
    assert pos["head_sha"] == "head123"
    assert pos["new_path"] == "app/src/main/java/com/example/ui/TestViewModel.kt"
    assert pos["new_line"] == 25
