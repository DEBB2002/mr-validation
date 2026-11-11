#!/usr/bin/env python3
"""
CLI Local Runner for Merge Request Architectural Compliance Checker.
Evaluates local git diffs or .diff files against architectural guidelines using LangGraph & Gemini.
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# Ensure the root directory of this project is on sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from colorama import init, Fore, Style
from dotenv import load_dotenv
from src.graph import run_review
from src.diff_parser import filter_and_parse_diff

# Initialize colorama for Windows/Linux/macOS cross-platform ANSI support
init(autoreset=True)
load_dotenv()


def read_file_contents(file_path: str) -> str:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    return path.read_text(encoding="utf-8")


def get_git_diff_against_branch(base_branch: str = "main") -> str:
    """Fetch git diff against a base branch using git diff -U15 base...HEAD."""
    try:
        cmd = ["git", "diff", f"-U15", f"{base_branch}...HEAD"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        # Fallback to base..HEAD if three-dot fails
        try:
            cmd = ["git", "diff", f"-U15", f"{base_branch}..HEAD"]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return result.stdout
        except Exception:
            raise RuntimeError(f"Failed to execute git diff against branch '{base_branch}': {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("git executable not found in PATH.")


def print_banner(model_name: str):
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 75}")
    print(f"  Merge Request Architectural Compliance Checker (AI Review Engine)")
    print(f"  Powered by LangGraph & Google Gemini ({model_name})")
    print(f"{'=' * 75}{Style.RESET_ALL}\n")


def display_report(report, ignored_files, model_name: str):
    print(f"{Fore.WHITE}{Style.BRIGHT}--- EVALUATION SUMMARY ---{Style.RESET_ALL}")
    print(f"{report.summary}\n")

    if ignored_files:
        print(f"{Fore.MAGENTA}Filtered / Ignored Files ({len(ignored_files)}):{Style.RESET_ALL}")
        for ign in ignored_files:
            print(f"  • {ign.get('file')} - {Fore.BLACK}{Style.BRIGHT}[{ign.get('reason')}]{Style.RESET_ALL}")
        print()

    if report.violations:
        print(f"{Fore.WHITE}{Style.BRIGHT}--- ARCHITECTURAL VIOLATIONS DETECTED ({len(report.violations)}) ---{Style.RESET_ALL}")
        for idx, v in enumerate(report.violations, 1):
            if v.severity == "CRITICAL":
                badge = f"{Fore.RED}{Style.BRIGHT}[CRITICAL]{Style.RESET_ALL}"
            else:
                badge = f"{Fore.YELLOW}{Style.BRIGHT}[WARNING]{Style.RESET_ALL}"

            loc = f":{v.line_number}" if v.line_number else ""
            print(f"{idx}. {badge} {Fore.CYAN}{v.file_path}{loc}{Style.RESET_ALL}")
            print(f"   {Fore.WHITE}Rule:{Style.RESET_ALL} {v.rule_violated}")
            print(f"   {Fore.WHITE}Explanation:{Style.RESET_ALL} {v.explanation}")
            print(f"   {Fore.GREEN}Suggested Fix:{Style.RESET_ALL} {v.suggested_fix}\n")
    else:
        print(f"{Fore.GREEN}{Style.BRIGHT}✓ No architectural violations found! All guidelines satisfied.{Style.RESET_ALL}\n")

    # Display Token Usage Statistics ("check the whole usage of it")
    print(f"{Fore.CYAN}{Style.BRIGHT}--- GEMINI USAGE METRICS ---{Style.RESET_ALL}")
    if report.usage:
        print(f"  • Model:         {Fore.YELLOW}{model_name}{Style.RESET_ALL}")
        print(f"  • Input Tokens:  {Fore.YELLOW}{report.usage.input_tokens:,}{Style.RESET_ALL}")
        print(f"  • Output Tokens: {Fore.YELLOW}{report.usage.output_tokens:,}{Style.RESET_ALL}")
        print(f"  • Total Tokens:  {Fore.YELLOW}{Style.BRIGHT}{report.usage.total_tokens:,}{Style.RESET_ALL}")
    else:
        print("  • Token usage data not recorded.")
    print()

    # Final Result
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 75}{Style.RESET_ALL}")
    if report.passed:
        print(f"{Fore.GREEN}{Style.BRIGHT}>>> RESULT: PASSED (MR is architecturally compliant) <<<{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}{Style.BRIGHT}>>> RESULT: FAILED (Critical architectural violations must be resolved) <<<{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 75}{Style.RESET_ALL}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Run local architectural compliance check on git diffs."
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--diff", "-d", type=str, help="Path to a .diff or .patch file to evaluate.")
    group.add_argument("--branch", "-b", type=str, default="main", help="Base branch to compare against (default: main).")

    parser.add_argument(
        "--rules", "-r",
        type=str,
        default=str(Path(__file__).parent / "rules" / "architecture.md"),
        help="Path to architectural rules markdown file (default: rules/architecture.md)."
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        help="Gemini model name (default: gemini-3.5-flash-lite)."
    )

    args = parser.parse_args()

    print_banner(args.model)

    # 1. Load architectural rules
    try:
        rules_content = read_file_contents(args.rules)
        print(f"Loaded rules from: {Fore.YELLOW}{args.rules}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error loading rules file: {e}{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(2)

    # 2. Obtain git diff
    if args.diff:
        try:
            raw_diff = read_file_contents(args.diff)
            print(f"Loaded diff from:  {Fore.YELLOW}{args.diff}{Style.RESET_ALL}\n")
        except Exception as e:
            print(f"{Fore.RED}Error loading diff file: {e}{Style.RESET_ALL}", file=sys.stderr)
            sys.exit(2)
    else:
        try:
            print(f"Comparing current branch against: {Fore.YELLOW}{args.branch}{Style.RESET_ALL}...")
            raw_diff = get_git_diff_against_branch(args.branch)
            if not raw_diff.strip():
                print(f"{Fore.YELLOW}No git diff detected between HEAD and '{args.branch}'. Nothing to review.{Style.RESET_ALL}")
                sys.exit(0)
        except Exception as e:
            print(f"{Fore.RED}Git diff error: {e}{Style.RESET_ALL}", file=sys.stderr)
            sys.exit(2)

    # Get preview of filtered/ignored files
    _, ignored_files = filter_and_parse_diff(raw_diff)

    # 3. Execute LangGraph Review Pipeline
    print(f"Running LangGraph review workflow using {Fore.GREEN}{args.model}{Style.RESET_ALL}...\n")
    try:
        report = run_review(raw_diff, rules_content, model_name=args.model)
    except Exception as e:
        print(f"{Fore.RED}Failed during architectural review execution: {e}{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(3)

    # 4. Display Results
    display_report(report, ignored_files, args.model)

    # 5. Exit code: 0 if passed, 1 if failed
    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
