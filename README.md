# Merge Request (MR) Architectural Compliance Checker

> **An automated, modular architectural compliance engine for Merge Requests and Pull Requests.**  
> Powered by **Python**, **LangGraph**, **Google Gemini (`gemini-3.5-flash-lite`)**, and **Smart Context Expansion**.

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [High-Level Architecture](#high-level-architecture)
3. [Repository Structure](#repository-structure)
4. [Multi-Node LangGraph Review Pipeline](#multi-node-langgraph-review-pipeline)
5. [Smart Context Expansion (Beyond Raw Diffs)](#smart-context-expansion-beyond-raw-diffs)
6. [Architectural Rules System](#architectural-rules-system)
7. [Production CI/CD Integration (GitLab CI)](#production-cicd-integration-gitlab-ci)
8. [Native GitLab Code Quality Report Integration (MR Widget)](#native-gitlab-code-quality-report-integration-mr-widget)
9. [GitLab MR Bot Comments & Inline Discussions (GitLabProvider)](#gitlab-mr-bot-comments--inline-discussions-gitlabprovider)
10. [Local CLI Runner & Developer Workflow](#local-cli-runner--developer-workflow)
11. [Tested Real-World Scenarios](#tested-real-world-scenarios)
12. [Automated Pytest Test Suite](#automated-pytest-test-suite)

---

## Executive Summary

Modern engineering teams struggle with architectural drift: **layer boundary violations**, **data transport leaks**, **unstructured concurrency**, and **lifecycle memory leaks** that slip through code reviews unnoticed.

The **MR Architectural Compliance Checker** acts as an automated Principal Software Architect in your CI/CD pipelines. It is designed around three core principles:
1. **Completely Decoupled & Platform-Agnostic:** The core engine accepts any unified git diff and architectural guidelines defined purely in Markdown (`rules_markdown`). No framework-specific or language-specific rules are hardcoded in Python.
2. **Beyond Raw Diffs (Smart Context Expansion):** Raw git diffs frequently hide enclosing classes, modules, and file-level imports. The engine automatically inspects the surrounding file context across any programming language (Kotlin, Java, Swift, Python, Go, TypeScript, etc.) to give the LLM full architectural awareness.
3. **Deterministic Gating with Structured Outputs:** Powered by LangGraph and Pydantic schemas, the pipeline guarantees that any `CRITICAL` violation strictly triggers a build failure (`passed = False`), while advisory warnings inform developers without blocking merges.

---

## High-Level Architecture

The compliance checker functions as a **centralized review engine** that any client repository (such as `MyTestApp`) pulls during Merge Request pipelines:

```mermaid
flowchart TD
    subgraph ClientRepository ["Client Repository (e.g. MyTestApp)"]
        MR["Developer Opens Merge Request"] --> CIPipeline["GitLab CI Pipeline (.gitlab-ci.yml)"]
    end

    subgraph CentralEngine ["Central Review Engine (mr-validation)"]
        CIPipeline -->|"1. Clone Engine via CI_JOB_TOKEN"| Engine["Centralized mr-validation"]
        CIPipeline -->|"2. Fetch Base Branch Diff"| RawDiff["Unified Git Diff (-U15)"]
        Engine --> StateMachine["LangGraph Review Pipeline"]
        RawDiff --> StateMachine

        subgraph StateMachineFlow ["LangGraph Multi-Node State Machine"]
            Node1["Node 1: prepare_context\n(Diff Filter & Smart Context Expansion)"] --> Node2["Node 2: evaluate_architecture\n(Gemini 3.5 Flash-Lite Structured Evaluation)"]
            Node2 --> Node3["Node 3: validate_findings\n(Self-Reflection Auditor & Verification Pass)"]
        end

        StateMachine --> Report["Pydantic ReviewResult\n(passed, summary, violations, usage)"]
    end

    subgraph EvaluationOutput ["Pipeline Evaluation & Gating"]
        Report -->|"passed == False (CRITICAL)"| Exit1["❌ Exit Code 1: Block Merge / Alert Team"]
        Report -->|"passed == True (CLEAN / WARNINGS)"| Exit0["✅ Exit Code 0: Compliant Pipeline Pass"]
    end
```

---

## Repository Structure

```
mr-validation/
├── src/
│   ├── schemas.py           # Strict Pydantic models (Violation, ReviewResult, TokenUsage)
│   ├── diff_parser.py       # Excludes lockfiles/binaries and chunks file diffs
│   ├── context_expander.py  # Language-agnostic Smart Context Expansion (scope, imports, outline)
│   ├── graph.py             # Multi-node LangGraph state machine with self-reflection
│   └── integrations/        # VCS Provider contracts for GitLab/GitHub
│       ├── vcs_base.py      # Abstract VCSProvider interface
│       ├── gitlab_provider.py # GitLab discussion & MR notes provider stub
│       └── github_provider.py # GitHub review comments provider stub
├── rules/
│   └── architecture.md      # Android Clean Architecture, Kotlin & Java conventions
├── samples/
│   ├── violation.diff       # Sample with Presentation & Memory leak violations
│   ├── clean.diff           # Compliant Clean Architecture sample
│   └── formatting.diff      # Docs and formatting-only diff sample
├── tests/
│   └── test_graph.py        # Pytest test suite (6 passing unit/integration tests)
├── ci/
│   └── gitlab-ci.example.yml # GitLab CI/CD template for client repositories
├── cli_local.py             # Local CLI runner with ANSI colors and token tracking
├── requirements.txt         # Core dependencies (LangGraph, Google GenAI, Pydantic)
├── .env.example             # Environment variable template
├── .env                     # Local API keys (excluded from git)
└── README.md
```

---

## Multi-Node LangGraph Review Pipeline

The review engine is built as an executable state machine using **LangGraph** (`langgraph.graph.StateGraph`):

```mermaid
flowchart LR
    START((Start)) --> PrepareContext["1. prepare_context\n(Filter diff & Expand Context)"]
    PrepareContext --> EvaluateArch["2. evaluate_architecture\n(Gemini 3.5 Flash-Lite LLM Review)"]
    EvaluateArch --> ValidateFindings["3. validate_findings\n(Self-Reflection Verification)"]
    ValidateFindings --> END((End))
```

### Node 1: `prepare_context`
* Cleans and filters the unified git diff using `diff_parser.py`:
  * Automatically ignores lockfiles (`package-lock.json`, `poetry.lock`, `gradle.lockfile`), compiled binaries (`.dex`, `.class`, `.jar`, `.aar`, `.so`), images, and minified assets.
* Executes **Smart Context Expansion** (`context_expander.py`):
  * Reads the modified file's surrounding source code (if present on disk or git tree).
  * Extracts module hierarchy, namespace/package, file-level imports, and enclosing classes/functions.

### Node 2: `evaluate_architecture`
* Formats each file diff alongside its **Expanded Context block**.
* Calls **Google Gemini (`gemini-3.5-flash-lite`)** via `.with_structured_output(ReviewResult, include_raw=True)`.
* Instructs Gemini to evaluate architectural compliance strictly based on the provided `arch_rules.md` while ignoring cosmetic indentation, formatting, or comments.
* Tracks token usage (`input_tokens`, `output_tokens`, `total_tokens`).

### Node 3: `validate_findings`
* Acts as an **automated self-reflection auditor**:
  * Cross-references every candidate violation against the modified diff lines (`+` lines) to eliminate hallucinations or false positives.
  * Ensures `CRITICAL` severity is reserved exclusively for true architectural blockers (layer boundary crossings, memory leaks, unstructured concurrency).
  * Enforces the hard rule: `passed = False` if any `CRITICAL` violation remains.

---

## Smart Context Expansion (Beyond Raw Diffs)

### The Problem with Raw Git Diffs
In a standard `git diff -U15`, only modified lines and immediate surrounding lines are shown. If a developer edits line 75 of a class:
* The class header (`class UserViewModel : ViewModel()`) is 70 lines above and **invisible to the LLM**.
* The file-level imports (`import com.example.data.AppDatabase`) are at line 5 and **invisible to the LLM**.
* Without context, an LLM cannot know whether the modified class is a ViewModel, an Activity, a UseCase, or an Entity.

### The Universal, Platform-Agnostic Solution
Instead of hardcoding language-specific regex rules, `src/context_expander.py` uses language-agnostic structural heuristics that work across **Kotlin, Java, Swift, Python, Go, C#, TypeScript, Rust, and PHP**:

1. **Path & Module Hierarchy:** Deconstructs the directory path (`app / src / main / java / com / example / ui / payment`).
2. **File-Level Dependencies:** Collects all `import`, `using`, `from ... import`, or `require` statements from the source file.
3. **Enclosing Declaration Scopes:** Scans upwards from the modified line to identify enclosing `class`, `struct`, `interface`, `trait`, `service`, `def`, `func`, or `fn` declarations and their supertypes.
4. **File Structure Outline:** Summarizes declared types and signatures in the file.

#### Raw Diff vs. Enriched Context

````carousel
```diff
--- a/app/src/main/java/com/example/ui/payment/PaymentViewModel.kt
+++ b/app/src/main/java/com/example/ui/payment/PaymentViewModel.kt
@@ -10,3 +10,4 @@ class PaymentViewModel : ViewModel() {
+    var activityContext: Context? = null
```
<!-- slide -->
```markdown
### File: app/src/main/java/com/example/ui/payment/PaymentViewModel.kt (Status: modified)
[Smart Expanded Context]
  • File: app/src/main/java/com/example/ui/payment/PaymentViewModel.kt
  • Path Segments: app / src / main / java / com / example / ui / payment
  • Namespace/Package: com.example.ui.payment
  • Enclosing Scope: class PaymentViewModel : ViewModel()
  • Declared Types: class PaymentViewModel : ViewModel()
  • Imports/Dependencies (2): import android.content.Context, import androidx.lifecycle.ViewModel

```diff
@@ -10,3 +10,4 @@
+    var activityContext: Context? = null
```
````

---

## Architectural Rules System

Architectural guidelines are completely decoupled into Markdown documents (`rules/architecture.md`). You can swap rulesets per project or language without changing a line of code.

### Android Clean Architecture Reference (`rules/architecture.md`):

| Rule | Severity | Requirement |
|---|:---:|---|
| **Rule 1.1: Presentation Boundaries** | `CRITICAL` | ViewModels/Activities must never call Data layer components (Room DAOs, Retrofit API services, DB instances) directly. Must interact via Domain UseCases. |
| **Rule 1.2: Domain Layer Purity** | `CRITICAL` | Domain layer (Entities, UseCases) must be pure Kotlin/Java with zero Android Framework (`android.*`, `androidx.*`) or ORM annotations (`@Entity`, `@Dao`). |
| **Rule 1.3: Data Layer Encapsulation** | `CRITICAL` | Network DTOs and Room entities must not leak into Presentation layer; they must be mapped to pure Domain models via mappers. |
| **Rule 2.1: Lifecycle & Leaks** | `CRITICAL` | ViewModels or long-lived Singletons must never retain references to Android `Context`, `Activity`, `Fragment`, or `View`. |
| **Rule 2.2: Concurrency Lifecycles** | `CRITICAL` | Never launch coroutines using `GlobalScope`. Use structured concurrency (`viewModelScope` or `lifecycleScope`). |
| **Rule 3.1: Immutability & State** | `WARNING` | ViewModels must expose immutable `StateFlow` to the UI. The backing `MutableStateFlow` must be private. |
| **Rule 3.2: Dispatcher Injection** | `WARNING` | Do not hardcode `Dispatchers.IO` or `Dispatchers.Default` in repositories. Inject `CoroutineDispatcher` for unit testability. |
| **Rule 3.3: Kotlin Null-Safety** | `WARNING` | Avoid force unwrapping `!!`. Use safe calls (`?.`), Elvis operator (`?:`), or smart casting. |

---

## Production CI/CD Integration (GitLab CI)

You can integrate this review engine into any new repository on GitLab in three steps:

### Step 1: Authorize the Client Project in `mr-validation`
Because `mr-validation` is a private repository, allow the client project's runner to clone it via `CI_JOB_TOKEN`:
```powershell
# 1. Fetch your target project ID
$CLIENT_ID = (glab api projects/<USERNAME>%2F<PROJECT_NAME> | ConvertFrom-Json).id

# 2. Add to inbound allowlist in mr-validation (ID: 88924590)
glab api --method POST projects/88924590/job_token_scope/allowlist --raw-field target_project_id=$CLIENT_ID
```

### Step 2: Configure CI/CD Variables
Configure your Gemini API key and GitLab token as masked CI/CD variables:
```powershell
# Required: Google Gemini API Key
glab variable set GOOGLE_API_KEY --value "YOUR_GEMINI_KEY" --masked --protected=false --repo <USERNAME>/<PROJECT_NAME>

# Optional (for automated MR bot comments & inline suggestions):
glab variable set GITLAB_TOKEN --value "YOUR_GITLAB_ACCESS_TOKEN" --masked --protected=false --repo <USERNAME>/<PROJECT_NAME>
```

### Step 3: Add `.gitlab-ci.yml` to the Client Project
Drop this standard job into `.gitlab-ci.yml` in the root of the client project:

```yaml
stages:
  - compliance

architectural_compliance_check:
  stage: compliance
  image: python:3.11-slim
  rules:
    # Trigger automatically on every Merge Request
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
    # 1. Fetch base target branch (e.g. main)
    - git fetch origin "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME"
    # 2. Execute compliance review with Code Quality JSON artifact and automated MR bot comments
    - >
      python /tmp/mr-validation/cli_local.py
      --branch "origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME"
      --rules /tmp/mr-validation/rules/architecture.md
      --export-codequality gl-code-quality-report.json
      --post-gitlab-comments
  allow_failure: true # Change to false to strictly block non-compliant MRs from merging
  artifacts:
    when: always
    reports:
      # Native GitLab MR Code Quality widget integration
      codequality: gl-code-quality-report.json
    paths:
      - gl-code-quality-report.json
    expire_in: 7 days
```

---

## Native GitLab Code Quality Report Integration (MR Widget)

The compliance checker exports violations into GitLab's native [Code Quality report schema](https://docs.gitlab.com/ee/ci/testing/code_quality.html) (`src/codequality.py`).

### Generated `gl-code-quality-report.json` Format:
```json
[
  {
    "description": "Activities, Fragments, and ViewModels must never call Data Layer components directly. (Suggested Fix: Introduce a Domain UseCase or Repository interface)",
    "check_name": "Rule 1.1: Presentation Layer Boundaries",
    "fingerprint": "d12bc9aa6eba6ddd354e28071b17b535",
    "severity": "critical",
    "location": {
      "path": "app/src/main/java/com/example/ui/MainActivity.kt",
      "lines": {
        "begin": 17
      }
    }
  }
]
```

### Native GitLab MR Widget Integration:
When `artifacts: reports: codequality: gl-code-quality-report.json` is configured in `.gitlab-ci.yml`:
* **MR Overview Widget:** Directly embeds an architectural health card:
  > *"Code Quality degraded on 2 points"*
* **Expandable Issue List:** Shows severity icons (🔴 Critical / 🟡 Minor), rule names, and clickable links to the exact file path and line number in the MR diff.
* **Diff Comparison:** Highlights newly introduced violations in the current MR compared against the target branch (`main`).

---

## GitLab MR Bot Comments & Inline Discussions (`GitLabProvider`)

The review engine includes a full Version Control System provider (`src/integrations/gitlab_provider.py`) implementing `VCSProvider`:

### 1. High-Level Summary Note (Idempotent)
* Posts an overview markdown report to `POST /projects/:id/merge_requests/:mr_iid/notes`.
* Displays review status badge (`❌ FAILED`, `⚠️ PASSED WITH WARNINGS`, or `✅ PASSED`), an executive summary, a structured violations table, and collapsible LLM inference metrics.
* **Idempotent:** Embeds a hidden marker `<!-- mr-validation-summary-marker -->`. Subsequent pipeline runs automatically **update the existing note** via `PUT /notes/:id` to prevent comment clutter on the MR.

### 2. Line-Level Inline Discussions & Architectural Guidance
* Posts directly to the affected line in the MR diff via `POST /projects/:id/merge_requests/:mr_iid/discussions`.
* Anchors discussion threads precisely using `diff_refs` (`base_sha`, `start_sha`, `head_sha`) and `position.new_line`.
* **Focused Architectural Guidance:** Focuses strictly on clear rule explanations and architectural design recommendations without cluttered or hallucinated code replacement patches:

```markdown
### 🔴 `[CRITICAL]` Architectural Violation: Rule 2.1: Lifecycle & Memory Leaks

**Explanation:** A ViewModel must never retain a reference to an Activity or Context object. Retaining hostActivity in LoginViewModel causes activity leaks across configuration changes.

**Recommendation:** Remove the hostActivity property completely and pass callbacks or observe StateFlow events from the UI layer.
```

---

## Local CLI Runner & Developer Workflow

Developers can test their local git branch or a `.diff` patch locally before pushing:

```bash
# Compare current git branch against main
python cli_local.py --branch main

# Evaluate a specific .diff file
python cli_local.py --diff samples/violation.diff

# Export native GitLab Code Quality report artifact
python cli_local.py --diff samples/violation.diff --export-codequality gl-code-quality-report.json

# Post automated MR bot review and inline discussions to GitLab
python cli_local.py --branch main --export-codequality gl-code-quality-report.json --post-gitlab-comments

# Use custom architectural rules or Gemini models
python cli_local.py --branch main --rules ./custom-rules.md --model gemini-3.5-flash-lite
```

### Sample Terminal Report Output

```text
===========================================================================
  Merge Request Architectural Compliance Checker (AI Review Engine)
  Powered by LangGraph & Google Gemini (gemini-3.5-flash-lite)
===========================================================================

Loaded rules from: rules/architecture.md
Loaded diff from:  samples/violation.diff

Running LangGraph review workflow using gemini-3.5-flash-lite...

--- EVALUATION SUMMARY ---
The pull request contains critical architectural violations including direct database access from the Presentation layer (Activity) and storing an Android Context reference inside a ViewModel.

--- ARCHITECTURAL VIOLATIONS DETECTED (2) ---
1. [CRITICAL] app/src/main/java/com/example/ui/MainActivity.kt:18
   Rule: Presentation Layer Boundaries
   Explanation: Activities, Fragments, and ViewModels must never call Data Layer components directly.
   Suggested Fix: Remove direct database calls from MainActivity. Delegate data fetching to a Domain UseCase.

2. [CRITICAL] app/src/main/java/com/example/ui/UserViewModel.kt:9
   Rule: No UI Context or View References in ViewModels
   Explanation: Storing activityContext in a ViewModel causes severe activity and memory leaks across configuration changes.
   Suggested Fix: Remove activityContext property from UserViewModel.

--- GEMINI USAGE METRICS ---
  • Model:         gemini-3.5-flash-lite
  • Input Tokens:  4,096
  • Output Tokens: 825
  • Total Tokens:  4,921

===========================================================================
>>> RESULT: FAILED (Critical architectural violations must be resolved) <<<
===========================================================================
```

---

## Tested Real-World Scenarios

The engine was tested in production across 7 live Merge Requests in [`MyTestApp`](https://gitlab.com/debbiswas2002/MyTestApp):

| MR | Scenario Name | Test Objective | Pipeline Outcome |
|:---:|---|---|:---:|
| **[!1](https://gitlab.com/debbiswas2002/MyTestApp/-/merge_requests/1)** | Clean Architecture Initial Refactoring | Verifies compliant 3-layer architecture with DTO mapping | ✅ **PASSED** (0 Violations) |
| **[!2](https://gitlab.com/debbiswas2002/MyTestApp/-/merge_requests/2)** | Payment Module with Violations | Tests multi-violation detection: direct DB query, Context in ViewModel, and Android framework in Domain | ❌ **FAILED** (3 CRITICAL) |
| **[!3](https://gitlab.com/debbiswas2002/MyTestApp/-/merge_requests/3)** | Memory Leak & GlobalScope in ViewModel | Tests lifecycle leak detection (`Activity` in ViewModel) & `GlobalScope.launch` | ❌ **FAILED** (2 CRITICAL) |
| **[!4](https://gitlab.com/debbiswas2002/MyTestApp/-/merge_requests/4)** | Presentation Boundary Breach & DTO Leak | Tests layer boundary breach (Activity directly querying API) & raw DTO leakage to UI | ❌ **FAILED** (2 CRITICAL) |
| **[!5](https://gitlab.com/debbiswas2002/MyTestApp/-/merge_requests/5)** | Kotlin Conventions & Mutability Warnings | Tests non-blocking advisory warnings: public `MutableStateFlow`, hardcoded `Dispatchers.IO`, and `!!` operator | ⚠️ **PASSED (w/ 3 Warnings)** |
| **[!6](https://gitlab.com/debbiswas2002/MyTestApp/-/merge_requests/6)** | Documentation & KDoc Comments | Tests false-positive resilience on markdown and code comment edits | ✅ **PASSED** (0 Violations) |
| **[!7](https://gitlab.com/debbiswas2002/MyTestApp/-/merge_requests/7)** | Full Clean Architecture Feature (Product Catalog) | Complete end-to-end feature module: Domain UseCase, Data DTO mapper with injected Dispatcher, Compose screen | ✅ **PASSED** (0 Violations) |

---

## Automated Pytest Test Suite

The test suite in [`tests/test_graph.py`](tests/test_graph.py) runs unit tests on diff parsing and Pydantic models, plus end-to-end integration tests using Gemini:

```powershell
python -m pytest tests/test_graph.py -v
```

### Test Coverage:
* `test_diff_parser_filters_lockfiles_and_binaries`: Ensures lockfiles and binary media are excluded.
* `test_pydantic_schema_enforces_critical_failure`: Verifies `ReviewResult` validator enforces `passed = False` whenever a `CRITICAL` violation is present.
* `test_smart_context_expansion_platform_agnostic`: Verifies universal header parsing and enclosing scope detection.
* `test_critical_architectural_violation_detected`: Integration test on diff with critical violations (must fail).
* `test_clean_architecture_diff_passes`: Integration test on compliant Clean Architecture diff (must pass).
* `test_formatting_and_comments_no_false_positives`: Verifies zero false positives on comment/documentation edits.
