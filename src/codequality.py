"""
GitLab Code Quality JSON Formatter.
Generates Code Quality artifacts adhering to the GitLab Code Quality (Code Climate subset) schema:
https://docs.gitlab.com/ee/ci/testing/code_quality.html
"""

import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any
from src.schemas import ReviewResult, Violation


SEVERITY_MAPPING: Dict[str, str] = {
    "CRITICAL": "critical",
    "WARNING": "minor",
    "INFO": "info",
}


def generate_codequality_json(report: ReviewResult) -> List[Dict[str, Any]]:
    """
    Transforms an architectural ReviewResult into GitLab's native Code Quality JSON schema.

    :param report: The final ReviewResult from the LangGraph pipeline.
    :return: A list of issue dictionaries following GitLab Code Quality specification.
    """
    issues: List[Dict[str, Any]] = []

    for violation in report.violations:
        line_num = violation.line_number if violation.line_number and violation.line_number > 0 else 1
        
        # Deterministic fingerprint based on file path, line, and rule violated
        raw_fingerprint = f"{violation.file_path}:{line_num}:{violation.rule_violated}"
        fingerprint = hashlib.md5(raw_fingerprint.encode("utf-8")).hexdigest()

        # Build clean description combining explanation and fix
        desc = violation.explanation.strip()
        if violation.suggested_fix:
            desc = f"{desc} (Suggested Fix: {violation.suggested_fix.strip()})"

        severity_level = SEVERITY_MAPPING.get(violation.severity.upper(), "major")

        issue = {
            "description": desc,
            "check_name": violation.rule_violated,
            "fingerprint": fingerprint,
            "severity": severity_level,
            "location": {
                "path": violation.file_path.replace("\\", "/"),
                "lines": {
                    "begin": line_num
                }
            }
        }
        issues.append(issue)

    return issues


def save_codequality_report(report: ReviewResult, output_path: str) -> str:
    """
    Serializes GitLab Code Quality issues to a JSON file.

    :param report: The ReviewResult object.
    :param output_path: Destination file path (e.g. 'gl-code-quality-report.json').
    :return: Absolute string path of the saved report.
    """
    dest = Path(output_path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    issues = generate_codequality_json(report)
    dest.write_text(json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(dest)
