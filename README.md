# Merge Request (MR) Architectural Compliance Checker

Automated, modular architectural compliance checker for Android Merge Requests (Kotlin & Java), built using **Python**, **LangGraph**, and **Google Gemini (`gemini-3.5-flash-lite`)**.

---

## Architecture Overview

```
mr-validation/
├── src/
│   ├── schemas.py           # Pydantic schemas (Violation, ReviewResult, TokenUsage)
│   ├── diff_parser.py       # Diff filter (excludes lockfiles/binaries) & hunk chunking
│   ├── graph.py             # LangGraph state machine (prepare -> evaluate -> validate)
│   └── integrations/        # Phase 2 VCS Provider contracts
│       ├── vcs_base.py
│       ├── gitlab_provider.py
│       └── github_provider.py
├── rules/
│   └── architecture.md      # Android Clean Architecture, Kotlin & Java conventions
├── samples/
│   ├── violation.diff       # Sample with Presentation & Memory leak violations
│   ├── clean.diff           # Clean architecture compliant diff
│   └── formatting.diff      # Comment/docs only diff
├── tests/
│   └── test_graph.py        # Pytest test suite
├── ci/
│   └── gitlab-ci.example.yml # GitLab CI/CD pipeline template
├── cli_local.py             # Local CLI runner with token usage metrics
├── requirements.txt
└── .env
```

---

## Quick Start

### 1. Environment Configuration
Ensure `.env` contains your Google API key and desired model:
```bash
GOOGLE_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.5-flash-lite
```

### 2. Run Local CLI
Test against sample diffs:

```bash
# Test diff with critical architectural violations (Exits with code 1)
python cli_local.py --diff samples/violation.diff

# Test clean diff following Clean Architecture (Exits with code 0)
python cli_local.py --diff samples/clean.diff

# Test against your current git branch vs main
python cli_local.py --branch main
```

### 3. Run Test Suite
```bash
python -m pytest tests/test_graph.py -v
```

---

## Token Usage & Model Tracking
Every evaluation tracks and reports:
- Model: `gemini-3.5-flash-lite`
- Input Tokens
- Output Tokens
- Total Accumulated Tokens

