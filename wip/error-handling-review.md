# Pipelex Error Handling Review

**Date:** 2026-04-12
**Branch:** `refactor/Inference-error-handling`
**Scope:** Full codebase error handling audit

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Axis 1 -- Error Flow: Catch, Enrich, Bubble, Deliver](#2-axis-1----error-flow)
3. [Axis 2 -- Error Class Architecture](#3-axis-2----error-class-architecture)
4. [Centralized Error Codes Assessment](#4-centralized-error-codes-assessment)
5. [Findings and Recommendations](#5-findings-and-recommendations)

---

## 1. Executive Summary

The Pipelex error handling system is **mature and well-structured** for a project at this stage. Key strengths:

- Single-rooted exception hierarchy (`PipelexError`) with consistent patterns
- Clean separation between human CLI (Rich), agent CLI (JSON), and internal propagation
- The inference layer refactor (`CogtError` + `InferenceErrorCategory` + `ErrorReport`) sets a strong standard
- Consistent `msg = "..."; raise XError(msg) from exc` pattern throughout
- No bare `except:` clauses; broad `Exception` catches only at CLI entry points

Key areas for improvement:

- **Inconsistent structured data**: Only inference exceptions carry `ErrorReport` metadata; core/pipeline exceptions are message-only
- **Parallel classification systems**: `AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, `RETRYABLE_ERROR_TYPES` live as string-keyed dicts disconnected from the class hierarchy
- **No error codes**: Errors are identified by class name strings, not stable codes
- **Missing categories on many CogtError subclasses**: ~20 CogtError subclasses have no `error_category` default

---

## 2. Axis 1 -- Error Flow: Catch, Enrich, Bubble, Deliver

### 2.1 Layer Model

```
Layer 5: CLI Entry Points          (catch + format for human/agent)
Layer 4: CLI Factories             (catch setup errors, route to handlers)
Layer 3: Pipeline Runner           (catch + wrap as PipelineExecutionError)
Layer 2: Pipe Router / Operators   (catch + wrap with pipe context)
Layer 1: Workers / SDK calls       (catch third-party + classify)
Layer 0: Third-party SDKs          (raw OpenAI/Anthropic/Google/etc. exceptions)
```

### 2.2 Layer 0 -> 1: Third-Party Error Transformation

**Location:** `pipelex/plugins/*/` worker files

Every provider worker catches SDK-specific exceptions and transforms them into `CogtError` subclasses with:
- `error_category` (TRANSIENT / CONFIGURATION / CONTENT / CAPACITY)
- `user_action` (actionable hint with billing links)
- Model descriptor in the message

**Example (OpenAI)** at `plugins/openai/openai_completions_llm_worker.py:145-182`:
```
openai.NotFoundError(404)         -> LLMCompletionError(CONFIGURATION)
openai.RateLimitError(429)+quota  -> LLMCompletionError(CAPACITY, billing_link)
openai.RateLimitError(429)        -> LLMCompletionError(TRANSIENT)
openai.APITimeoutError            -> LLMCompletionError(TRANSIENT)
openai.BadRequestError+content    -> LLMCompletionError(CONTENT)
openai.AuthenticationError(401)   -> LLMCompletionError(CONFIGURATION)
```

Classification logic is centralized in `cogt/inference/error_classification.py` -- pure functions that inspect error messages to distinguish quota exhaustion from rate limiting, with per-provider pattern tuples.

**Assessment:** This layer is the strongest part of the system. Consistent, well-tested (60+ parametrized test cases), and provider-agnostic classification.

### 2.3 Layer 1 -> 2: Pipe Operators

**Location:** `pipelex/pipe_operators/*/`

Pipe operators define thin wrapper exceptions (`PipeLLMFactoryError`, `PipeImgGenRunError`, etc.) and add pipe-level context (pipe_code, pipe_type, model_handle). The `PipeOperatorModelAvailabilityError` at `pipe_operators/exceptions.py:5` is the richest -- carries `run_mode`, `pipe_type`, `pipe_code`, `pipe_stack`, `model_handle`, `fallback_list`.

### 2.4 Layer 2 -> 3: Pipeline Runner

**Location:** `pipelex/pipeline/runner.py:131-187`

The `PipelexRunner.execute_pipeline()` method catches three exception types:

| Caught | Wrapped As | Context Added |
|--------|-----------|---------------|
| `PipeRouterError` | `PipelineExecutionError` | run_mode, pipe_code, output_name, pipe_stack |
| `PipelexError` (other) | `PipelineExecutionError` | run_mode, pipe_code, output_name, pipe_stack |
| `ValidationError` (Pydantic) | `PipeExecutionError` | formatted validation message |

The original exception is always chained via `from exc`, so the full cause chain is preserved. Telemetry events are tracked on failure.

### 2.5 Layer 3 -> 4: CLI Factories

**Location:** `pipelex/cli/cli_factory.py` (human) and `pipelex/cli/agent_cli/commands/agent_cli_factory.py` (agent)

These catch initialization errors from `Pipelex.make()` and route to the appropriate handler. The agent factory catches 7+ specific exception types and sends each through `agent_error()`. The human factory delegates to dedicated `handle_*_error()` functions in `error_handlers.py`.

### 2.6 Layer 4 -> 5: CLI Entry Points -- Delivery

#### Human CLI (Rich Console)

**Location:** `pipelex/cli/error_handlers.py`

Each error type has a dedicated handler function with:
- Red error banner with context label
- Structured fields (Pipe, Model, Fallbacks, Pipe Stack)
- Actionable tip (from `ErrorReport.user_action` or hardcoded fallback)
- Documentation and Discord links
- `raise typer.Exit(1) from exc`

**Assessment:** Well-crafted, but handler functions are verbose and repetitive. Each handler follows the same structure (banner -> fields -> tip -> links -> exit) with minor variations.

#### Agent CLI (Structured JSON)

**Location:** `pipelex/cli/agent_cli/commands/agent_output.py`

The `agent_error()` function produces:
```json
{
  "error": true,
  "error_type": "LLMCompletionError",
  "message": "...",
  "hint": "...",
  "retryable": true,
  "error_domain": "runtime",
  "error_category": "transient",
  "model": "gpt-4o",
  "provider": "openai",
  "error_source": ["LLMCompletionError @ .../worker.py:152 (in _gen_text)"]
}
```

The hint, domain, and retryable are resolved from three parallel sources:
1. `ErrorReport` (from `cause.to_error_report()`) -- preferred
2. `AGENT_ERROR_HINTS` dict -- fallback lookup by class name string
3. `AGENT_ERROR_DOMAINS` dict -- always from lookup
4. `RETRYABLE_ERROR_TYPES` set -- fallback when report doesn't have retryable

**Assessment:** This works but has a dual-source problem. The `ErrorReport` mechanism (class-level metadata) and the dict-based lookups (string-keyed) can drift. Adding a new error class requires updating both the class hierarchy AND the agent_output.py dicts.

#### Validation Errors (Flattened)

**Location:** `agent_output.py:220-301` (`extract_validation_errors()`)

`ValidateBundleError` aggregates errors from different validation phases. The `extract_validation_errors()` function flattens them into a uniform list with `category` tags (blueprint_validation, pipe_factory, pipe_validation, instantiation). This is the most structured error delivery in the codebase.

#### Markdown Output (Special Case)

`InferenceSetupRequiredError` is rendered as markdown to stdout (not JSON) with exit code 0. This is used by agent skills to display setup guidance directly.

### 2.7 Error Flow Summary

| Error Origin | Catch Layer | Enrichment | Human Delivery | Agent Delivery |
|---|---|---|---|---|
| SDK API call | Worker | category + user_action + model | Rich formatted | JSON with category/retryable |
| Model routing | Pipe operator | pipe_code + pipe_stack + fallbacks | Rich formatted | JSON with pipe context |
| Pipeline execution | Runner | pipe_code + pipe_stack + output_name | Rich formatted | JSON with cause chain |
| Bundle validation | Validator | aggregated error lists | Rich table | Flattened JSON array |
| Configuration/setup | Pipelex.make() | specific error type | Rich formatted | JSON or markdown |
| File/input parsing | CLI command | file path + TOML location | typer.secho red | JSON with hint |

---

## 3. Axis 2 -- Error Class Architecture

### 3.1 Class Hierarchy Overview

```
Exception
  PipelexError                         base_exceptions.py
    PipelexUnexpectedError
    PipelexConfigError
    PipelexSetupError
    CogtError                          cogt/exceptions.py
      [49 inference-related subclasses]
    PipeExecutionError                 pipeline/exceptions.py
    PipelineExecutionError
    PipeStackOverflowError
    ConceptError                       core/concepts/exceptions.py
      ConceptCodeError
      ConceptRefineError
      ConceptStringError
    StuffError                         core/stuffs/exceptions.py
      StuffFactoryError
      StuffContentFactoryError
      StuffContentTypeError
      ...
    WorkingMemoryError                 core/memory/exceptions.py
      WorkingMemoryConsistencyError
      WorkingMemoryVariableError
        WorkingMemoryTypeError
        WorkingMemoryStuffNotFoundError
    LibraryError                       libraries/exceptions.py
      LibraryLoadingError
        DomainLoadingError
        ConceptLoadingError
        PipeLoadingError
    PipeControllerError                pipe_controllers/exceptions.py
    PipeRunError                       pipe_run/exceptions.py
      PipeRouterError
      PipeRunInputsError
    PipelexServiceError                system/pipelex_service/exceptions.py
      InferenceSetupRequiredError
      GatewayTermsNotAcceptedError
      ...
    PipelexInterpreterError            core/interpreter/exceptions.py
    GraphSpecError                     graph/exceptions.py
    KitError                           kit/exceptions.py
  ToolError                            system/exceptions.py
    StorageError                       tools/storage/exceptions.py
    Jinja2TemplateSyntaxError          tools/jinja2/jinja2_errors.py
    SecretNotFoundError                tools/secrets/secrets_errors.py
  TracebackMessageError                system/exceptions.py
    FatalError
      ConfigValidationError
      ConfigModelError (also ValueError)
```

### 3.2 Exception Module Organization

**Pattern: One `exceptions.py` per package.** This is followed consistently:

| Package | Exception File | Exception Count |
|---------|---------------|-----------------|
| `cogt/` | `exceptions.py` | 49 classes + 2 enums |
| `core/pipes/` | `exceptions.py` | 4 classes + 2 enums |
| `core/concepts/` | `exceptions.py` | 7 classes |
| `core/stuffs/` | `exceptions.py` | 7 classes |
| `core/memory/` | `exceptions.py` | 7 classes |
| `pipeline/` | `exceptions.py` | 4 classes |
| `pipe_run/` | `exceptions.py` | 4 classes |
| `pipe_operators/` | `exceptions.py` | 1 class |
| `pipe_controllers/` | `exceptions.py` | 2 classes |
| `libraries/` | `exceptions.py` | 5 classes |
| `system/` | `exceptions.py` | 9 classes |
| `cli/` | `exceptions.py` | 2 classes |
| Each plugin | `*_exceptions.py` | 2-6 classes |

**Total: ~130 custom exception classes across ~25 files.**

### 3.3 Actual Exception Subclasses vs. Data-Carrying Classes

Most exception classes fall into one of three patterns:

#### Pattern A: Plain message-only exception (grouping/categorization)

```python
class LLMPromptSpecError(CogtError):
    pass
```

~70% of all exception classes. They exist solely for type-based catching and identification. No additional structured data.

#### Pattern B: Exception with structured fields

```python
class PipelineExecutionError(PipelexError):
    def __init__(self, message, run_mode, pipe_code, output_name, pipe_stack):
        ...
```

~25% of classes. Carry context fields as instance attributes. Notable examples:
- `PipelineExecutionError` (pipe_code, run_mode, pipe_stack, output_name)
- `ModelChoiceNotFoundError` (model_type, model_choice, suggestions, available_options)
- `PipeValidationError` (error_type enum, domain_code, pipe_code, variable_names, file_path)
- `InferenceBackendCredentialsError` (credentials_error_type, backend_name, key_name)

#### Pattern C: Non-exception structured error data (BaseModel/dataclass)

```python
@dataclass(frozen=True)
class ErrorReport:
    error_type: str
    message: str
    error_category: str | None = None
    ...
```

These are **not raised** -- they are data containers:
- `ErrorReport` (dataclass) -- serialization target for `to_error_report()`
- `PipelexBundleBlueprintValidationErrorData` (BaseModel) -- aggregated in `ValidateBundleError`
- `PipesAndConceptValidationErrorData` (BaseModel) -- aggregated in `ValidateBundleError`
- `PipeFactoryErrorData` (BaseModel) -- aggregated in `ValidateBundleError`
- `SyntaxErrorData` (BaseModel) -- wraps Python SyntaxError fields

### 3.4 Key Observation: Two Error Reporting Systems

The codebase has **two parallel error reporting mechanisms**:

| Mechanism | Where Used | Metadata Source |
|-----------|-----------|-----------------|
| `to_error_report()` | Inference layer (CogtError hierarchy) | Class-level attributes (`error_category`, `user_action`) |
| Dict lookups | Agent CLI output (`agent_output.py`) | String-keyed dicts (`AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, `RETRYABLE_ERROR_TYPES`) |

The `agent_error()` function merges both: it calls `to_error_report()` first, then falls back to dict lookups. This means:

- Inference errors (CogtError) get metadata from the class hierarchy -- **self-describing**
- Non-inference errors (pipeline, validation, setup) get metadata from the dicts -- **externally described**

---

## 4. Centralized Error Codes Assessment

### 4.1 Current State

There are **no stable error codes** in the system. Errors are identified by:

1. **Class name** (e.g., `"PipelineExecutionError"`) -- used in `AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, `error_type` field in JSON
2. **Error type enums** (e.g., `PipeValidationErrorType.MISSING_INPUT_VARIABLE`) -- used within specific domains
3. **Error category enum** (`InferenceErrorCategory`) -- used for retry decisions

### 4.2 Should We Add Error Codes?

**Recommendation: Not now, but prepare the ground.**

Error codes (like `PPLX-1001`) make sense when:
- External consumers need stable identifiers across versions (public API)
- Errors need to be documented in a searchable knowledge base
- Programmatic consumers need to match on something more stable than class names

For Pipelex today:
- The agent CLI is the primary programmatic consumer, and it already has good classification via `error_domain` + `error_category` + `error_type`
- Class names are fairly stable and descriptive
- Adding error codes to 130+ exceptions is high effort for low immediate value

**Instead, consider these incremental steps:**

1. **Extend `ErrorReport` to all PipelexError subclasses** (not just CogtError) -- this is the highest-value change
2. **Move `AGENT_ERROR_HINTS` and `AGENT_ERROR_DOMAINS` into the class hierarchy** -- eliminate the parallel dict system
3. **Add error codes only when shipping a public API** -- at that point, auto-generate a code from the class path (e.g., `cogt.LLMCompletionError` -> `COGT-001`)

---

## 5. Findings and Recommendations

### 5.1 Strengths (Keep Doing)

| # | What | Evidence |
|---|------|----------|
| S1 | Single-rooted hierarchy | All custom exceptions inherit from `PipelexError` or `ToolError` |
| S2 | Consistent `from exc` chaining | Every re-raise preserves the cause chain |
| S3 | Message-before-raise pattern | `msg = "..."; raise XError(msg) from exc` throughout |
| S4 | No broad Exception catches in business logic | Only at CLI entry points |
| S5 | Structured inference error classification | `InferenceErrorCategory` + per-provider classifiers + `ErrorReport` |
| S6 | Dual CLI delivery | Rich for humans, JSON for agents -- same errors, different rendering |
| S7 | Validation error aggregation | `ValidateBundleError` collects all validation issues before reporting |
| S8 | Good test coverage on inference errors | 60+ parametrized classification tests + worker error handling tests |

### 5.2 Issues and Improvement Proposals

#### Issue 1: `ErrorReport` is inference-only

**Problem:** `PipelexError.to_error_report()` returns a bare `ErrorReport(error_type, message)` with no category, retryability, or user_action. Only `CogtError` overrides this to include metadata. Non-inference errors (pipeline, validation, setup, library) produce empty reports.

**Impact:** The agent CLI falls back to hardcoded dicts for non-inference errors. The two systems can drift.

**Proposal:** Add `error_category` and `user_action` to key non-inference exceptions:

```python
class PipelineExecutionError(PipelexError):
    error_category = "runtime"
    user_action = "Check 'pipe_stack' to identify which pipe failed"
```

This would let `to_error_report()` carry the metadata that currently lives in `AGENT_ERROR_HINTS` and `AGENT_ERROR_DOMAINS`.

**Files to modify:** `pipeline/exceptions.py`, `pipe_run/exceptions.py`, `core/pipes/exceptions.py`, `system/pipelex_service/exceptions.py`, `libraries/exceptions.py`

---

#### Issue 2: ~20 CogtError subclasses have no error_category

**Problem:** These classes inherit `CogtError.error_category = None`:

- `ImageContentError`, `CostRegistryError`, `ReportingManagerError`, `SdkTypeError`
- `LLMCompletionError`, `LLMAssignmentError`, `LLMPromptSpecError`, `LLMPromptTemplateInputsError`, `LLMPromptParameterError`
- `PromptImageFactoryError`, `PromptImageFormatError`, `PromptDocumentFactoryError`
- `ImgGenPromptError`, `ImgGenParameterError`, `ImgGenGenerationError`
- `ExtractOutputError`, `GeneratedImageError`, `ExtractJobFailureError`, `SearchJobFailureError`
- `RoutingProfileLibraryNotFoundError`, `RoutingProfileLibraryError`, `InferenceModelSpecError`
- `InferenceBackendLibraryNotFoundError`, `InferenceBackendLibraryValidationError`
- `InferenceBackendLibraryError`, `ModelManagerError`, `ModelDeckNotFoundError`, `ModelDeckValidationError`

**Impact:** When these are raised without an instance-level category override (which only happens in workers), `ErrorReport.error_category` and `retryable` are `None`. The agent gets no classification guidance.

**Proposal:** Set sensible class-level defaults. Most of these fall into obvious categories:

| Class | Proposed Category |
|-------|------------------|
| `LLMCompletionError` | Leave as None (set per-instance by workers -- this is correct) |
| `LLMPromptSpecError`, `LLMPromptTemplateInputsError`, `LLMPromptParameterError` | CONTENT |
| `PromptImageFactoryError`, `PromptDocumentFactoryError` | CONTENT |
| `ImgGenPromptError`, `ImgGenParameterError` | CONTENT |
| `RoutingProfileLibraryNotFoundError`, `InferenceBackendLibraryNotFoundError` | CONFIGURATION |
| `ModelManagerError`, `ModelDeckNotFoundError`, `ModelDeckValidationError` | CONFIGURATION |
| `CostRegistryError`, `ReportingManagerError` | TRANSIENT |

`LLMCompletionError` and `ImgGenGenerationError` correctly have no default because workers set the category dynamically based on the actual SDK error.

---

#### Issue 3: Dict-based classification in agent_output.py is fragile

**Problem:** `AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, and `RETRYABLE_ERROR_TYPES` use string keys matching class names. Adding a new exception class requires remembering to update these dicts. There is no compile-time check.

**Proposal (short-term):** Add a unit test that verifies every PipelexError subclass that appears in the agent CLI error handlers also has an entry in these dicts. This catches drift.

**Proposal (medium-term):** Move domain and hint onto the exception classes themselves:

```python
class PipelexError(Exception):
    error_domain: str | None = None     # "input", "config", "runtime"
    user_action: str | None = None      # hint text

    def to_error_report(self) -> ErrorReport:
        return ErrorReport(
            error_type=type(self).__name__,
            message=self.message,
            error_domain=self.error_domain,
            user_action=self.user_action,
        )
```

Then `agent_error()` reads from the report instead of the dicts. The dicts become the fallback for third-party exceptions only.

---

#### Issue 4: `ToolError` sits outside `PipelexError`

**Problem:** `ToolError` (base for storage, Jinja2, secrets errors) inherits from `Exception`, not `PipelexError`. This means `ToolError` subclasses:
- Don't have `to_error_report()`
- Aren't caught by `except PipelexError` blocks
- Don't participate in the structured error reporting pipeline

**Impact:** A `StorageError` raised deep in the stack would bypass `PipelexError` catches in the pipeline runner and bubble up as an unhandled exception.

**Proposal:** Make `ToolError` inherit from `PipelexError`:

```python
class ToolError(PipelexError):
    pass
```

This is a safe change -- `ToolError` subclasses already follow the same patterns (message string, specific catches). The only risk is that existing `except PipelexError` catches would now also catch `ToolError`, which is actually the desired behavior.

---

#### Issue 5: `TracebackMessageError` has a separate lifecycle

**Problem:** `TracebackMessageError` and its children (`FatalError`, `ConfigValidationError`, `ConfigModelError`) inherit from `Exception` and have their own logging mechanism via `TracebackMessageErrorMode`. They don't participate in `ErrorReport` serialization.

**Impact:** Limited. These are only used during app startup for fatal configuration errors. But it's a separate error path that doesn't benefit from the structured reporting.

**Proposal:** Low priority. Consider eventually making `FatalError` inherit from `PipelexError` + adding `error_category = "configuration"`. But the startup path works fine as-is.

---

#### Issue 6: Repetitive Rich error handler functions

**Problem:** `error_handlers.py` has 10 handler functions that all follow the same pattern:
1. Get report
2. Print red banner
3. Print structured fields
4. Print tip
5. Print links
6. `raise typer.Exit(1) from exc`

Each is 20-40 lines. The total file is 434 lines.

**Proposal:** Extract a generic `display_error_panel()` helper:

```python
def display_error_panel(
    exc: PipelexError,
    title: str,
    fields: dict[str, str],
    context_lines: list[str] | None = None,
) -> NoReturn:
    report = exc.to_error_report()
    console = get_console()
    console.print(f"\n[bold red]{title}[/bold red]\n")
    for label, value in fields.items():
        console.print(f"[bold cyan]{label}:[/bold cyan] [yellow]{escape(value)}[/yellow]")
    ...
```

This would cut the file roughly in half and make the pattern explicit.

---

#### Issue 7: No error serialization test for the full chain

**Problem:** Tests exist for `ErrorReport` serialization and for individual worker error classification. But there is no integration test that verifies the full path: worker exception -> pipeline runner -> CLI agent_error() -> JSON output.

**Proposal:** Add an integration test that simulates a pipeline execution failure with a known inference error and verifies the JSON output contains the expected `error_category`, `retryable`, `model`, `provider`, and `error_source` fields.

---

### 5.3 Priority Matrix

| # | Issue | Effort | Impact | Priority |
|---|-------|--------|--------|----------|
| I2 | Set default categories on uncategorized CogtError subclasses | Small | Medium | **P1** |
| I3-short | Add drift-detection test for agent_output dicts | Small | Medium | **P1** |
| I4 | Make ToolError inherit from PipelexError | Small | Medium | **P2** |
| I1 | Extend ErrorReport to non-inference exceptions | Medium | High | **P2** |
| I6 | Extract generic Rich error display helper | Medium | Low | **P3** |
| I3-medium | Move hints/domains onto exception classes | Medium | Medium | **P3** |
| I7 | Full-chain error serialization integration test | Medium | Medium | **P3** |
| I5 | Unify TracebackMessageError with PipelexError | Small | Low | **P4** |

---

### 5.4 Maturity Assessment

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Exception hierarchy | 8/10 | Clean, single-rooted, well-organized by package |
| Error context preservation | 9/10 | Consistent `from exc`, structured fields on key exceptions |
| Third-party error transformation | 9/10 | Excellent inference layer with classification + tests |
| Human-facing error delivery | 8/10 | Rich formatting with actionable tips, slightly verbose |
| Agent-facing error delivery | 7/10 | Good JSON structure, but dual-source metadata is fragile |
| Error codes / stable identifiers | 4/10 | No codes, relies on class name strings |
| Validation error aggregation | 9/10 | ValidateBundleError with flattened extraction is well done |
| Test coverage | 7/10 | Inference layer excellent, other layers less covered |
| **Overall** | **7.5/10** | Strong foundation, inference refactor sets the right pattern to extend |
