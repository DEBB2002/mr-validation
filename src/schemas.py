from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class Violation(BaseModel):
    """Represents a single architectural rule violation identified in a code diff."""
    file_path: str = Field(description="Relative path of the file containing the violation.")
    line_number: Optional[int] = Field(
        default=None,
        description="Line number where the violation occurs, or approximate line in the diff."
    )
    rule_violated: str = Field(description="Name or title of the violated architectural rule.")
    severity: Literal["CRITICAL", "WARNING"] = Field(
        description="Severity: 'CRITICAL' blocks the MR; 'WARNING' is advisory."
    )
    explanation: str = Field(description="Detailed explanation of why this violates architectural guidelines.")
    suggested_fix: str = Field(description="Actionable suggestion or code pattern to resolve the violation.")


class TokenUsage(BaseModel):
    """Token usage metrics recorded during evaluation."""
    model_name: Optional[str] = Field(default=None, description="The LLM model name used for evaluation.")
    input_tokens: int = Field(default=0, description="Total input prompt tokens.")
    output_tokens: int = Field(default=0, description="Total output completion tokens.")
    total_tokens: int = Field(default=0, description="Combined token usage.")


class ReviewResult(BaseModel):
    """Structured architectural evaluation result of the Merge Request diff."""
    passed: bool = Field(
        description="True if the MR passes compliance checks; False if any CRITICAL violation exists."
    )
    summary: str = Field(description="High-level architectural summary of the findings.")
    violations: List[Violation] = Field(
        default_factory=list,
        description="List of detected architectural violations."
    )
    usage: Optional[TokenUsage] = Field(
        default=None,
        description="Total token usage accumulated during review."
    )

    @model_validator(mode="after")
    def enforce_pass_fail_rule(self) -> "ReviewResult":
        """Ensure that passed is False if any CRITICAL violation is present."""
        has_critical = any(v.severity == "CRITICAL" for v in self.violations)
        if has_critical and self.passed:
            self.passed = False
        return self

