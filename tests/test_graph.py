import os
import sys
from pathlib import Path
import pytest
from dotenv import load_dotenv

# Ensure mr-validation root is in sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from src.schemas import Violation, ReviewResult, TokenUsage
from src.diff_parser import filter_and_parse_diff, is_ignored_file
from src.graph import run_review


@pytest.fixture(scope="session")
def arch_rules() -> str:
    rules_path = PROJECT_ROOT / "rules" / "architecture.md"
    assert rules_path.is_file(), f"Rules file missing: {rules_path}"
    return rules_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit Tests: Diff Parser & Filtering
# ---------------------------------------------------------------------------

def test_diff_parser_filters_lockfiles_and_binaries():
    """Verify that lockfiles, images, and build files are ignored."""
    ignored_cases = [
        ("package-lock.json", True),
        ("yarn.lock", True),
        ("poetry.lock", True),
        ("gradle.lockfile", True),
        ("app/src/main/res/drawable/logo.png", True),
        ("app/build/intermediates/classes.dex", True),
        ("app/src/main/assets/script.min.js", True),
        (".gradle/caches/file.bin", True),
        ("app/src/main/java/com/example/ui/MainActivity.kt", False),
        ("domain/src/main/java/com/example/domain/User.kt", False),
    ]

    for file_path, expected_ignored in ignored_cases:
        ignored, reason = is_ignored_file(file_path)
        assert ignored == expected_ignored, f"Failed for {file_path}: expected {expected_ignored}, got {ignored} ({reason})"


def test_pydantic_schema_enforces_critical_failure():
    """Ensure ReviewResult validator enforces passed=False when CRITICAL violation exists."""
    violation = Violation(
        file_path="MainActivity.kt",
        line_number=15,
        rule_violated="Presentation Layer Boundaries",
        severity="CRITICAL",
        explanation="Direct DB call",
        suggested_fix="Use ViewModel",
    )
    result = ReviewResult(
        passed=True,  # Attempting to set True with CRITICAL violation
        summary="Test summary",
        violations=[violation],
    )
    assert result.passed is False, "ReviewResult must force passed=False if any CRITICAL violation is present."


# ---------------------------------------------------------------------------
# Integration Tests: LangGraph Pipeline with Gemini
# ---------------------------------------------------------------------------

def test_critical_architectural_violation_detected(arch_rules):
    """
    Test Case 1: Diff with clear architectural violations
    (Direct Room DAO call in Activity and Context in ViewModel).
    Must fail with passed=False and contain CRITICAL violations.
    """
    violation_diff = (PROJECT_ROOT / "samples" / "violation.diff").read_text(encoding="utf-8")

    report = run_review(raw_diff=violation_diff, arch_rules=arch_rules)

    assert isinstance(report, ReviewResult)
    assert report.passed is False, "Expected review to FAIL on critical violations."
    assert len(report.violations) > 0, "Expected at least one violation."

    # Verify that at least one violation is CRITICAL
    severities = [v.severity for v in report.violations]
    assert "CRITICAL" in severities, f"Expected CRITICAL severity in {severities}"

    # Verify token usage is recorded
    assert report.usage is not None
    assert report.usage.total_tokens > 0


def test_clean_architecture_diff_passes(arch_rules):
    """
    Test Case 2: Clean diff adhering to Clean Architecture rules.
    Must pass with passed=True and zero CRITICAL violations.
    """
    clean_diff = (PROJECT_ROOT / "samples" / "clean.diff").read_text(encoding="utf-8")

    report = run_review(raw_diff=clean_diff, arch_rules=arch_rules)

    assert isinstance(report, ReviewResult)
    assert report.passed is True, f"Expected clean diff to pass, but failed: {report.summary}"
    critical_violations = [v for v in report.violations if v.severity == "CRITICAL"]
    assert len(critical_violations) == 0, f"Unexpected critical violations: {critical_violations}"

    # Verify token usage is recorded
    assert report.usage is not None
    assert report.usage.total_tokens > 0


def test_formatting_and_comments_no_false_positives(arch_rules):
    """
    Test Case 3: Diff with only docstrings/comments and README changes.
    Must pass without false positive violations.
    """
    formatting_diff = (PROJECT_ROOT / "samples" / "formatting.diff").read_text(encoding="utf-8")

    report = run_review(raw_diff=formatting_diff, arch_rules=arch_rules)

    assert isinstance(report, ReviewResult)
    assert report.passed is True, f"Expected formatting diff to pass, got: {report.summary}"
    assert len(report.violations) == 0, f"Expected 0 violations for formatting diff, got: {report.violations}"

    # Verify token usage is recorded
    assert report.usage is not None
    assert report.usage.total_tokens > 0

