import os
from typing import TypedDict, List, Dict, Any, Optional
from dotenv import load_dotenv

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END

from src.schemas import Violation, ReviewResult, TokenUsage
from src.diff_parser import filter_and_parse_diff, ParsedFileDiff

load_dotenv()


class ReviewState(TypedDict):
    """LangGraph state schema for MR architectural compliance checking."""
    raw_diff: str
    filtered_files: List[Dict[str, Any]]
    ignored_files: List[Dict[str, str]]
    arch_rules: str
    violations: List[Violation]
    final_report: Optional[ReviewResult]
    token_usage: Dict[str, int]
    model_name: str


def get_gemini_llm(model_name: Optional[str] = None) -> ChatGoogleGenerativeAI:
    """Instantiate ChatGoogleGenerativeAI with API key and selected model."""
    selected_model = model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing GOOGLE_API_KEY or GEMINI_API_KEY environment variable.")
    return ChatGoogleGenerativeAI(
        model=selected_model,
        google_api_key=api_key,
    )


def prepare_context_node(state: ReviewState) -> Dict[str, Any]:
    """
    Node 1: Cleans and filters raw git diffs.
    Excludes lockfiles, images, binaries, and build outputs.
    """
    raw_diff = state.get("raw_diff", "")
    valid_files, ignored_files = filter_and_parse_diff(raw_diff)

    return {
        "filtered_files": [f.model_dump() for f in valid_files],
        "ignored_files": ignored_files,
        "violations": [],
        "token_usage": state.get("token_usage") or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


def evaluate_architecture_node(state: ReviewState) -> Dict[str, Any]:
    """
    Node 2: Evaluates filtered diff chunks against architectural rules
    using Google Gemini with structured output.
    """
    filtered_files = state.get("filtered_files", [])
    arch_rules = state.get("arch_rules", "")
    token_usage = dict(state.get("token_usage", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}))
    model_name = state.get("model_name") or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    # If no valid code files changed, pass immediately
    if not filtered_files:
        empty_result = ReviewResult(
            passed=True,
            summary="No actionable code files detected in this diff (only ignored/binary/lockfile changes).",
            violations=[],
            usage=TokenUsage(**token_usage),
        )
        return {
            "violations": [],
            "final_report": empty_result,
            "token_usage": token_usage,
        }

    # Format the code diffs for Gemini
    diff_text_blocks = []
    for f in filtered_files:
        status = "new" if f.get("is_new") else ("deleted" if f.get("is_deleted") else "modified")
        diff_text_blocks.append(
            f"### File: {f.get('file_path')} (Status: {status})\n```diff\n{f.get('patch', '')}\n```"
        )
    formatted_diff = "\n\n".join(diff_text_blocks)

    system_prompt = (
        "You are a Principal Android Architect and Lead DevOps Compliance Reviewer.\n"
        "Your task is to review Git Merge Request diffs strictly against the provided Architectural Rules.\n\n"
        "GUIDELINES:\n"
        "1. Focus strictly on Architectural Integrity, Clean Architecture boundaries, Android Lifecycle safety, "
        "and Kotlin/Java conventions.\n"
        "2. Do NOT flag minor styling, indentation, reordered imports, or trivial comment edits unless they violate stated rules.\n"
        "3. Mark severity as 'CRITICAL' if changes break layer boundaries (e.g. Presentation directly querying DB/network, "
        "Domain importing Android framework, Activity/Context leaking in ViewModel, GlobalScope coroutine), which blocks the MR.\n"
        "4. Mark severity as 'WARNING' for convention issues (e.g. hardcoded Dispatchers, public mutable StateFlow, !! operator).\n"
        "5. If no architectural rules are violated, return passed=True with an empty violations list."
    )

    user_prompt = (
        f"# ARCHITECTURAL RULES:\n{arch_rules}\n\n"
        f"# MERGE REQUEST CODE DIFF TO EVALUATE:\n{formatted_diff}\n\n"
        "Please perform your architectural evaluation and return the structured ReviewResult."
    )

    llm = get_gemini_llm(model_name)
    structured_llm = llm.with_structured_output(ReviewResult, include_raw=True)

    response = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    # Accumulate token usage
    raw_response = response.get("raw")
    if raw_response and hasattr(raw_response, "usage_metadata") and raw_response.usage_metadata:
        meta = raw_response.usage_metadata
        token_usage["input_tokens"] += meta.get("input_tokens", 0)
        token_usage["output_tokens"] += meta.get("output_tokens", 0)
        token_usage["total_tokens"] += meta.get("total_tokens", 0)

    parsed: Optional[ReviewResult] = response.get("parsed")
    candidate_violations = parsed.violations if parsed else []

    return {
        "violations": candidate_violations,
        "token_usage": token_usage,
    }


def validate_findings_node(state: ReviewState) -> Dict[str, Any]:
    """
    Node 3: Self-reflection and verification step.
    Filters out low-confidence false positives, verifies violations against the actual diff,
    and constructs the final ReviewResult.
    """
    candidate_violations = state.get("violations", [])
    token_usage = dict(state.get("token_usage", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}))
    arch_rules = state.get("arch_rules", "")
    filtered_files = state.get("filtered_files", [])
    model_name = state.get("model_name") or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    # If already resolved or no violations were found in Node 2
    if state.get("final_report") is not None:
        return {"final_report": state["final_report"]}

    if not candidate_violations:
        final_report = ReviewResult(
            passed=True,
            summary="All modified files comply with the Android Clean Architecture rules. No violations detected.",
            violations=[],
            usage=TokenUsage(**token_usage),
        )
        return {
            "final_report": final_report,
            "token_usage": token_usage,
        }

    # Format candidate violations for verification
    violations_summary = "\n".join([
        f"- File: {v.file_path}, Line: {v.line_number}, Rule: {v.rule_violated}, Severity: {v.severity}\n"
        f"  Explanation: {v.explanation}\n  Suggested Fix: {v.suggested_fix}"
        for v in candidate_violations
    ])

    diff_snippets = "\n".join([
        f"File: {f.get('file_path')}\n{f.get('patch', '')}"
        for f in filtered_files
    ])

    system_prompt = (
        "You are an Architectural Verification Auditor.\n"
        "Your task is to double-check candidate violations identified in an automated code review.\n"
        "Critically evaluate each candidate violation:\n"
        "1. Verify that the violation actually exists in the modified diff lines (+ lines).\n"
        "2. Discard any false positives, hallucinated lines, or nitpicks that are not true violations of the rules.\n"
        "3. Confirm that 'CRITICAL' severity is reserved for true architectural blockers (layer violations, memory leaks).\n"
        "4. Return the finalized ReviewResult containing only verified, high-confidence violations."
    )

    user_prompt = (
        f"# ARCHITECTURAL RULES:\n{arch_rules}\n\n"
        f"# CODE DIFF:\n{diff_snippets}\n\n"
        f"# CANDIDATE VIOLATIONS TO VERIFY:\n{violations_summary}\n\n"
        "Validate each candidate violation. Discard any false positives and return the final ReviewResult."
    )

    llm = get_gemini_llm(model_name)
    structured_llm = llm.with_structured_output(ReviewResult, include_raw=True)

    response = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    # Accumulate token usage from verification pass
    raw_response = response.get("raw")
    if raw_response and hasattr(raw_response, "usage_metadata") and raw_response.usage_metadata:
        meta = raw_response.usage_metadata
        token_usage["input_tokens"] += meta.get("input_tokens", 0)
        token_usage["output_tokens"] += meta.get("output_tokens", 0)
        token_usage["total_tokens"] += meta.get("total_tokens", 0)

    parsed: Optional[ReviewResult] = response.get("parsed")
    if parsed:
        verified_violations = parsed.violations
        has_critical = any(v.severity == "CRITICAL" for v in verified_violations)
        final_report = ReviewResult(
            passed=(not has_critical),
            summary=parsed.summary,
            violations=verified_violations,
            usage=TokenUsage(**token_usage),
        )
    else:
        # Fallback to candidates if parsing encountered an issue
        has_critical = any(v.severity == "CRITICAL" for v in candidate_violations)
        final_report = ReviewResult(
            passed=(not has_critical),
            summary="Completed architectural evaluation with initial candidate findings.",
            violations=candidate_violations,
            usage=TokenUsage(**token_usage),
        )

    return {
        "violations": final_report.violations,
        "final_report": final_report,
        "token_usage": token_usage,
    }


def build_review_graph() -> Any:
    """Builds and compiles the LangGraph state machine workflow."""
    workflow = StateGraph(ReviewState)

    # Add Nodes
    workflow.add_node("prepare_context", prepare_context_node)
    workflow.add_node("evaluate_architecture", evaluate_architecture_node)
    workflow.add_node("validate_findings", validate_findings_node)

    # Add Edges
    workflow.add_edge(START, "prepare_context")
    workflow.add_edge("prepare_context", "evaluate_architecture")
    workflow.add_edge("evaluate_architecture", "validate_findings")
    workflow.add_edge("validate_findings", END)

    return workflow.compile()


def run_review(raw_diff: str, arch_rules: str, model_name: Optional[str] = None) -> ReviewResult:
    """
    Synchronous helper to run a full architectural review on a git diff string.
    """
    app = build_review_graph()
    initial_state: ReviewState = {
        "raw_diff": raw_diff,
        "filtered_files": [],
        "ignored_files": [],
        "arch_rules": arch_rules,
        "violations": [],
        "final_report": None,
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "model_name": model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    }

    result = app.invoke(initial_state)
    return result["final_report"]

