"""
Unit tests for GitLab Code Quality JSON artifact generation.
"""

import json
from pathlib import Path
from src.schemas import ReviewResult, Violation, TokenUsage
from src.codequality import generate_codequality_json, save_codequality_report


def test_codequality_json_generation_structure():
    report = ReviewResult(
        passed=False,
        summary="Found critical architectural violations.",
        violations=[
            Violation(
                file_path="app/src/main/java/com/example/ui/UserViewModel.kt",
                line_number=15,
                rule_violated="No UI Context in ViewModel",
                severity="CRITICAL",
                explanation="Storing Context in ViewModel leads to memory leaks.",
                suggested_fix="Remove context reference.",
            ),
            Violation(
                file_path="app/src/main/java/com/example/data/UserRepository.kt",
                line_number=42,
                rule_violated="Dispatcher Injection",
                severity="WARNING",
                explanation="Hardcoded Dispatchers.IO used.",
                suggested_fix="Inject CoroutineDispatcher.",
            ),
        ],
        usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
    )

    items = generate_codequality_json(report)
    assert len(items) == 2

    # Verify first issue (CRITICAL -> critical)
    item1 = items[0]
    assert item1["check_name"] == "No UI Context in ViewModel"
    assert item1["severity"] == "critical"
    assert item1["location"]["path"] == "app/src/main/java/com/example/ui/UserViewModel.kt"
    assert item1["location"]["lines"]["begin"] == 15
    assert "fingerprint" in item1
    assert "memory leaks" in item1["description"]
    assert "Suggested Fix:" in item1["description"]

    # Verify second issue (WARNING -> minor)
    item2 = items[1]
    assert item2["check_name"] == "Dispatcher Injection"
    assert item2["severity"] == "minor"
    assert item2["location"]["path"] == "app/src/main/java/com/example/data/UserRepository.kt"
    assert item2["location"]["lines"]["begin"] == 42


def test_codequality_save_report(tmp_path: Path):
    report = ReviewResult(
        passed=True,
        summary="Clean architecture verified.",
        violations=[],
    )

    out_file = tmp_path / "gl-code-quality-report.json"
    saved_path = save_codequality_report(report, str(out_file))

    assert Path(saved_path).is_file()
    data = json.loads(Path(saved_path).read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 0
