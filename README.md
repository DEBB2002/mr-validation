# Merge Request (MR) Architectural Compliance Checker

Automated, modular architectural compliance checker for Merge Requests (Android Clean Architecture, Kotlin & Java conventions), built using **Python**, **LangGraph**, and **Google Gemini (`gemini-3.5-flash-lite`)**.

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

---

## Integrating into a New Project (GitLab CI/CD)

You can use `mr-validation` as a centralized architectural review engine across any number of repositories (e.g. `MyTestApp`). The client repositories stay lightweight and pull this engine during Merge Request pipelines.

### Step 1: Authorize the New Project in `mr-validation`

Because `mr-validation` is a private repository, GitLab runners in other projects require inbound access authorization via `CI_JOB_TOKEN`:

Using `glab` in your terminal:
```powershell
# 1. Retrieve the new project's ID
$NEW_PROJECT_ID = (glab api projects/<USERNAME>%2F<NEW_PROJECT_NAME> | ConvertFrom-Json).id

# 2. Allow the new project in mr-validation's job token allowlist (mr-validation ID: 88924590)
glab api --method POST projects/88924590/job_token_scope/allowlist --raw-field target_project_id=$NEW_PROJECT_ID
```

*(Or via Web UI: Open `mr-validation` > **Settings** > **CI/CD** > **Token Access** > click **Add project**).*

---

### Step 2: Configure `GOOGLE_API_KEY` in the New Project

Provide the Gemini API key for the new project's CI runner:

```powershell
glab variable set GOOGLE_API_KEY --value "YOUR_GEMINI_API_KEY" --masked --protected=false --repo <USERNAME>/<NEW_PROJECT_NAME>
```

> **Tip:** If your repositories are housed under a GitLab Group, add `GOOGLE_API_KEY` once at **Group Settings > CI/CD > Variables**. All existing and future repositories in that group will inherit it automatically.

---

### Step 3: Add `.gitlab-ci.yml` to the New Project

Create or update `.gitlab-ci.yml` in the root of the new project:

```yaml
stages:
  - compliance

architectural_compliance_check:
  stage: compliance
  image: python:3.11-slim
  rules:
    # Trigger automatically on any Merge Request event
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
  variables:
    GEMINI_MODEL: "gemini-3.5-flash-lite"
    GIT_DEPTH: "0" # Full git history to compare branch against target
  before_script:
    - apt-get update && apt-get install -y git
    - pip install --upgrade pip
    # Clone the centralized engine using the GitLab CI Job Token
    - git clone https://gitlab-ci-token:${CI_JOB_TOKEN}@gitlab.com/debbiswas2002/mr-validation.git /tmp/mr-validation
    - pip install -r /tmp/mr-validation/requirements.txt
  script:
    # Fetch base target branch (e.g. main)
    - git fetch origin "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME"
    # Execute the compliance review
    - python /tmp/mr-validation/cli_local.py --branch "origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME" --rules /tmp/mr-validation/rules/architecture.md
  allow_failure: true # Set to false to strictly block non-compliant MRs from merging
```

---

### Step 4: Customizing Rules per Project (Optional)

The checker supports custom rules via the `--rules` flag:

- **Use Central Rules:** `--rules /tmp/mr-validation/rules/architecture.md` (default Android Clean Architecture).
- **Use Project-Specific Rules:** Create a `rules.md` file directly in the client repository and point to it:
  ```yaml
  script:
    - python /tmp/mr-validation/cli_local.py --branch "origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME" --rules ./rules.md
  ```

---

### Local Testing (Developers Pre-Push)

Developers can run the check locally on their machine before pushing to GitLab:

```powershell
# From the client project root:
python E:\Agentic\mr-validation\cli_local.py --branch main
```
