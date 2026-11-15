import os
from typing import TypedDict, List, Dict, Any, Optional
from dotenv import load_dotenv

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END

from src.schemas import Violation, ReviewResult, TokenUsage
from src.diff_parser import filter_and_parse_diff, ParsedFileDiff
from src.context_expander import enrich_file_context, EnrichedFileContext

load_dotenv()


class ReviewState(TypedDict):
    """LangGraph state schema for MR architectural compliance checking."""
    raw_diff: str
    filtered_files: List[Dict[str, Any]]
    ignored_files: List[Dict[str, str]]
    enriched_contexts: Dict[str, Dict[str, Any]]
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
    Node 1: Cleans and filters raw git diffs, then executes language-agnostic
    Smart Context Expansion to extract surrounding module hierarchies, enclosing scopes,
    and active file imports without hardcoded regex or framework assumptions.
    """
    raw_diff = state.get("raw_diff", "")
    valid_files, ignored_files = filter_and_parse_diff(raw_diff)

    enriched_contexts: Dict[str, Dict[str, Any]] = {}
    for f in valid_files:
        ctx: EnrichedFileContext = enrich_file_context(f.file_path, f.patch)
        enriched_contexts[f.file_path] = ctx.model_dump()

    return {
        "filtered_files": [f.model_dump() for f in valid_files],
        "ignored_files": ignored_files,
        "enriched_contexts": enriched_contexts,
        "violations": [],
        "token_usage": state.get("token_usage") or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


def evaluate_architecture_node(state: ReviewState) -> Dict[str, Any]:
    """
    Node 2: Evaluates diff chunks enriched with smart surrounding context
    against the provided architectural guidelines using Google Gemini (gemini-3.5-flash-lite).
    """
    filtered_files = state.get("filtered_files", [])
    enriched_contexts = state.get("enriched_contexts", {})
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

    # Format the code diffs WITH Smart Expanded Context
    diff_text_blocks = []
    for f in filtered_files:
        file_path = f.get("file_path", "")
        status = "new" if f.get("is_new") else ("deleted" if f.get("is_deleted") else "modified")
        ctx_dict = enriched_contexts.get(file_path, {})
        context_summary = ctx_dict.get("context_summary", "")

        context_block = f"\n[Smart Expanded Context]\n{context_summary}\n" if context_summary else ""

        diff_text_blocks.append(
            f"### File: {file_path} (Status: {status}){context_block}\n"
            f"```diff\n{f.get('patch', '')}\n```"
        )
    formatted_diff = "\n\n".join(diff_text_blocks)

    system_prompt = (
        "You are an expert Principal Software Architect and DevOps Reviewer.\n"
        "Your task is to review Git Merge Request diffs strictly against the provided Architectural Rules.\n\n"
        "SMART ARCHITECTURAL CONTEXT:\n"
        "Each diff hunk is enriched with language-agnostic contextual metadata (Directory Hierarchy, "
        "File Namespace/Package, Enclosing Class/Function Scope, and File-Level Imports/Dependencies). "
        "Use this expanded context to understand the structural role of the modified code even if the outer "
        "class or module definition is outside the diff hunk.\n\n"
        "EVALUATION GUIDELINES:\n"
        "1. Strictly enforce the provided Architectural Rules against the diff and its expanded context.\n"
        "2. Do NOT flag cosmetic styling, whitespace, indentation, or minor comment edits unless they violate stated rules.\n"
        "3. Mark severity as 'CRITICAL' if changes break architectural boundaries, violate layer encapsulation, "
        "cause resource/lifecycle leaks, or violate core design rules specified in the architecture document.\n"
        "4. Mark severity as 'WARNING' for non-blocking conventions, testability issues, or advisory guidelines.\n"
        "5. If no architectural rules are violated, return passed=True with an empty violations list."
    )

    user_prompt = (
        f"# ARCHITECTURAL RULES:\n{arch_rules}\n\n"
        f"# MERGE REQUEST CODE DIFF TO EVALUATE (WITH SMART EXPANDED CONTEXT):\n{formatted_diff}\n\n"
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
            summary="All modified files comply with the provided architectural rules. No violations detected.",
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
        "3. Confirm that 'CRITICAL' severity is reserved for true architectural blockers.\n"
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
    """Builds and compiles the LangGraph state machine workflow with Smart Context Expansion."""
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
        "enriched_contexts": {},
        "arch_rules": arch_rules,
        "violations": [],
        "final_report": None,
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "model_name": model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    }

    result = app.invoke(initial_state)
    return result["final_report"]
