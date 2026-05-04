# Pipelex Error Handling Review

**Original review:** 2026-04-12 (branch `refactor/Inference-error-handling`)
**Refreshed:** 2026-05-04 (branch `feature/Temporal-merge-2`, after Phase 0–3 merged)
**Scope:** Full codebase error handling audit, plus status of the active improvement plans

---

## What changed since the original review

| Original Issue | Status |
|---|---|
| Issue 1 — `ErrorReport` is inference-only | **In progress.** `to_error_report()` is now wired into `agent_error()` (Phase 1 done). Class-level `error_domain` / `user_action` on non-CogtError exceptions is the **Phase 6** scope. |
| Issue 2 — many CogtError subclasses have no `error_category` | **Mostly resolved.** `CONFIGURATION` defaults are set on the routing/backend/model-deck/handle-not-found/spec families. Remaining unset (intentionally — workers set per-instance) and the proposed CONTENT defaults are the **Phase 6** scope. |
| Issue 3 — dict-based classification in `agent_output.py` is fragile | **Open.** `AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, `RETRYABLE_ERROR_TYPES` still live in `pipelex/cli/agent_cli/commands/agent_output.py`. Drift-detection test + migration onto classes is **Phase 6**. |
| Issue 4 — `ToolError` sits outside `PipelexError` | **Resolved.** `class ToolError(PipelexError)` in `pipelex/system/exceptions.py:8`. |
| Issue 5 — `TracebackMessageError` separate lifecycle | **Open (low priority).** Still inherits from `PipelexError` indirectly via its own subclass chain; logging mechanism unchanged. Same recommendation: leave as-is unless it gets in the way. |
| Issue 6 — repetitive Rich error handler functions | **Open.** `cli/error_handlers.py` is still 434 lines with 11 near-identical handlers; helper extraction not done. |
| Issue 7 — no full-chain error serialization integration test | **Open.** Worker-level classification tests are in great shape; the runner→CLI→JSON e2e snapshot test is still missing. |

**Worker coverage** (the Tier 1/2/3 ranking from `worker-error-handling-review.md`): all Tier 3 workers were brought up in Phase 3 (full SDK exception handling, quota/credits detection, content-policy detection where relevant). Reading `error_classification.py` is now the canonical place to see provider-specific quota/content patterns.

**Active follow-on work** (separate files):

- [error-handling-phases-0-3-completed.md](error-handling-phases-0-3-completed.md) — record of what Phases 0–3 shipped.
- [error-handling-phase-4-markdown-cli.md](error-handling-phase-4-markdown-cli.md) — markdown-default agent CLI output (run/validate/init/error).
- [error-handling-phase-5-retry-architecture.md](error-handling-phase-5-retry-architecture.md) — move retries from gateway workers to PipeRouter.
- [error-handling-phase-6-error-report-everywhere.md](error-handling-phase-6-error-report-everywhere.md) — class-level domain/user_action everywhere; eliminate dict drift.
- [error-handling-phase-7-temporal-bridge.md](error-handling-phase-7-temporal-bridge.md) — wire `error_category.is_retryable` into `TemporalError`.
- [worker-error-handling-review.md](worker-error-handling-review.md) — original tier inventory that drives the phase plans.
- [instructor-unwrap-other-workers.md](instructor-unwrap-other-workers.md) — port the Anthropic `InstructorRetryException` unwrap fix to OpenAI Completions/Responses, Mistral, Google.

---

## 1. Executive Summary

The Pipelex error handling system is **mature and well-structured**. Key strengths (unchanged):

- Single-rooted exception hierarchy (`PipelexError`, with `ToolError` now inside it) — consistent patterns.
- Clean separation between human CLI (Rich), agent CLI (JSON / markdown), and internal propagation.
- The inference layer (`CogtError` + `InferenceErrorCategory` + `ErrorReport` + per-provider `error_classification.py`) sets the standard the rest of the hierarchy is migrating toward.
- Consistent `msg = "..."; raise XError(msg) from exc` pattern.
- No bare `except:` clauses; broad `Exception` catches only at CLI entry points.

Remaining work (all tracked in active phase files):

- **Class-level error metadata for non-CogtError** exceptions is still partial (Phase 6).
- **Dict-based agent classification** still parallels `to_error_report()` (Phase 6).
- **Retry logic** is still per-worker (gateway uses tenacity); needs to move to PipeRouter (Phase 5).
- **Markdown-default agent CLI output** is still missing for `run` / `validate` / `init` (Phase 4).
- **Temporal bridge** for `error_category.is_retryable` → `non_retryable` mapping (Phase 7).

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

**Location:** `pipelex/plugins/*/` worker files.

After Phase 2 + Phase 3, **every** provider worker catches SDK-specific exceptions and transforms them into `CogtError` subclasses with:

- `error_category` (TRANSIENT / CONFIGURATION / CONTENT / CAPACITY)
- `user_action` (actionable hint with billing links where applicable)
- Model descriptor in the message
- `from exc` chaining preserved

Classification logic is centralized in `pipelex/cogt/inference/error_classification.py` (pure functions: `is_quota_exhaustion_*`, `is_content_policy_violation`, etc.). Per-provider pattern tuples live alongside.

**Assessment:** This layer is the strongest part of the system. Consistent, well-tested (parametrized classification tests + per-worker error-path tests), provider-agnostic.

**Caveat — `instructor` wrapping.** Only Anthropic currently unwraps `InstructorRetryException` to recover the underlying SDK error before classification. OpenAI Completions/Responses, Mistral, and Google still mis-classify wrapped quota/timeout/auth as `CONTENT`. Tracked in [instructor-unwrap-other-workers.md](instructor-unwrap-other-workers.md).

### 2.3 Layer 1 -> 2: Pipe Operators

**Location:** `pipelex/pipe_operators/*/`.

Pipe operators define thin wrapper exceptions (`PipeLLMFactoryError`, `PipeImgGenRunError`, etc.) and add pipe-level context (pipe_code, pipe_type, model_handle). The richest is `PipeOperatorModelAvailabilityError` at `pipe_operators/exceptions.py` — carries `run_mode`, `pipe_type`, `pipe_code`, `pipe_stack`, `model_handle`, `fallback_list`.

### 2.4 Layer 2 -> 3: Pipeline Runner

**Location:** `pipelex/pipeline/runner.py`.

The `PipelexRunner.execute_pipeline()` method catches three exception types:

| Caught | Wrapped As | Context Added |
|--------|-----------|---------------|
| `PipeRouterError` | `PipelineExecutionError` | run_mode, pipe_code, output_name, pipe_stack |
| `PipelexError` (other) | `PipelineExecutionError` | run_mode, pipe_code, output_name, pipe_stack |
| `ValidationError` (Pydantic) | `PipeExecutionError` | formatted validation message |

The original exception is always chained via `from exc`. Telemetry events tracked on failure.

### 2.5 Layer 3 -> 4: CLI Factories

**Location:** `pipelex/cli/cli_factory.py` (human) and `pipelex/cli/agent_cli/commands/agent_cli_factory.py` (agent).

These catch initialization errors from `Pipelex.make()` and route to the appropriate handler. The agent factory catches several specific exception types and sends each through `agent_error()`. The human factory delegates to dedicated `handle_*_error()` functions in `error_handlers.py`.

### 2.6 Layer 4 -> 5: CLI Entry Points -- Delivery

#### Human CLI (Rich Console)

**Location:** `pipelex/cli/error_handlers.py` (434 lines, 11 handler functions).

Each error type has a dedicated handler function with: red banner, structured fields, actionable tip, doc/Discord links, `raise typer.Exit(1) from exc`.

**Assessment:** Well-crafted, but verbose and repetitive. Helper extraction is Issue 6 / open.

#### Agent CLI (Structured JSON)

**Location:** `pipelex/cli/agent_cli/commands/agent_output.py`.

`agent_error()` now (Phase 1) prefers `cause.to_error_report()` and only falls back to the dicts when the report has no `user_action` / `retryable`. The dicts (`AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, `RETRYABLE_ERROR_TYPES`) are still the source for `error_domain` and for non-PipelexError exceptions (FileNotFoundError, JSONDecodeError, ValidationError, etc.).

Output JSON shape:

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

**Assessment:** Phase 1 cut the dual-source problem in half. Phase 6 is what eliminates the remaining dict drift by moving `error_domain` / `user_action` onto the exception classes.

#### Validation Errors (Flattened)

**Location:** `agent_output.py:extract_validation_errors`. Unchanged. Still the most structured error delivery in the codebase.

#### Markdown Output (Special Case)

`InferenceSetupRequiredError` is rendered as markdown to stdout (exit 0). Used by agent skills to display setup guidance. Phase 4 generalizes markdown delivery to `run` / `validate` / `init` and to the error path.

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
    SecurityError
    ToolError                          system/exceptions.py   (now under PipelexError)
      NestedKeyConflictError
      StorageError
      Jinja2TemplateSyntaxError
      SecretNotFoundError
      ...
    CogtError                          cogt/exceptions.py     (~50 subclasses)
    PipeExecutionError                 pipeline/exceptions.py
    PipelineExecutionError
    PipeStackOverflowError
    ConceptError                       core/concepts/exceptions.py (+ children)
    StuffError                         core/stuffs/exceptions.py (+ children)
    WorkingMemoryError                 core/memory/exceptions.py (+ children)
    LibraryError                       libraries/exceptions.py (+ children)
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
  TracebackMessageError                system/exceptions.py
    FatalError
      ConfigValidationError
      ConfigModelError (also ValueError)
```

### 3.2 Exception Module Organization

**Pattern: One `exceptions.py` per package** — followed consistently across **49 files** holding **~218 custom exception classes** (codebase has grown since the original review's "~130 across ~25 files").

### 3.3 Exception Class Patterns

Three patterns, unchanged:

- **Pattern A — Plain message-only exception** (~70%): exists for type-based catching.
- **Pattern B — Exception with structured fields** (~25%): carries context as instance attributes (e.g., `PipelineExecutionError`, `ModelChoiceNotFoundError`, `PipeValidationError`, `InferenceBackendCredentialsError`).
- **Pattern C — Non-exception structured error data** (BaseModel/dataclass): `ErrorReport`, `PipelexBundleBlueprintValidationErrorData`, `PipesAndConceptValidationErrorData`, `PipeFactoryErrorData`, `SyntaxErrorData`. These are aggregated into raised exceptions, not raised themselves.

`ErrorReport` is now a Pydantic dataclass (`base_exceptions.py:7`) with `extra="forbid"`, fields: `error_type`, `message`, `error_category`, `retryable`, `user_action`, `model`, `provider`. The `to_dict()` helper drops `None` fields.

### 3.4 Two Error Reporting Systems (still parallel)

Phase 1 wired `to_error_report()` into `agent_error()`, but the dicts in `agent_output.py` still hold:

| Mechanism | Where Used | Metadata Source |
|---|---|---|
| `to_error_report()` | All `PipelexError` (only `CogtError` subclasses currently override it with metadata) | Class-level attributes (`error_category`, `user_action`) |
| Dict lookups | `agent_output.py` — `error_domain`, hints/retryable for non-CogtError and non-PipelexError types | String-keyed dicts |

Inference errors (CogtError) now self-describe at the class level. Non-inference errors (pipeline, validation, setup, library) still depend on the dicts. Phase 6 closes the gap.

---

## 4. Centralized Error Codes Assessment

**Recommendation unchanged: not now, but keep preparing the ground.**

For Pipelex today:

- The agent CLI is the primary programmatic consumer; it already has good classification via `error_domain` + `error_category` + `error_type`.
- Class names are stable and descriptive.
- Adding error codes to ~218 exceptions is high effort for low immediate value.

Incremental steps that help and are already on the roadmap:

1. **Extend `to_error_report()` metadata to all PipelexError subclasses** — Phase 6.
2. **Move `AGENT_ERROR_HINTS` / `AGENT_ERROR_DOMAINS` into the class hierarchy** — Phase 6.
3. **Add error codes only when shipping a public API** — at that point, auto-generate from class path (e.g., `cogt.LLMCompletionError` → `COGT-001`).

---

## 5. Findings and Recommendations

### 5.1 Strengths (Keep Doing)

| # | What | Evidence |
|---|---|---|
| S1 | Single-rooted hierarchy | All custom exceptions inherit from `PipelexError` (including `ToolError` since this review was first written). |
| S2 | Consistent `from exc` chaining | Every re-raise preserves the cause chain. |
| S3 | Message-before-raise pattern | `msg = "..."; raise XError(msg) from exc` throughout. |
| S4 | No broad Exception catches in business logic | Only at CLI entry points. |
| S5 | Structured inference error classification | `InferenceErrorCategory` + per-provider classifiers + `ErrorReport`. |
| S6 | Dual CLI delivery | Rich for humans, JSON for agents — same errors, different rendering. |
| S7 | Validation error aggregation | `ValidateBundleError` collects all validation issues before reporting. |
| S8 | Worker error coverage | All inference workers (LLM/extract/img-gen/search) catch SDK exceptions and assign `error_category` after Phase 3. |

### 5.2 Open Issues — Status & Owner

#### Issue 1: `ErrorReport` is inference-only — **In progress (Phase 6)**

`PipelexError.to_error_report()` returns a bare report (`error_type`, `message`) for non-CogtError exceptions. Phase 6 adds `error_domain` and class-level `user_action` to `PipeExecutionError`, `PipelineExecutionError`, `ValidateBundleError`, `PipelexInterpreterError`, `PipelexSetupError`, `PipelexConfigError`, and the `PipelexService` family.

#### Issue 2: ~20 CogtError subclasses had no `error_category` — **Mostly resolved**

After Phase 2/3, the routing/backend/model-deck/handle/spec families now default to `CONFIGURATION`. `LLMCompletionError`, `ImgGenGenerationError`, `ExtractJobFailureError`, `SearchJobFailureError` are intentionally left dynamic (workers set per-instance). Remaining defaults to add (CONTENT-y prompt-related errors) are Phase 6.1 in [error-handling-phase-6-error-report-everywhere.md](error-handling-phase-6-error-report-everywhere.md).

#### Issue 3: Dict-based classification in `agent_output.py` is fragile — **Open (Phase 6)**

The dicts still exist (`AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, `RETRYABLE_ERROR_TYPES`). Phase 6.5 adds a drift-detection unit test; Phase 6.3/6.4 migrate the entries onto the exception classes themselves.

#### Issue 4: `ToolError` sits outside `PipelexError` — **Resolved**

`class ToolError(PipelexError)` in `pipelex/system/exceptions.py:8`. All `except PipelexError` blocks now catch `ToolError` subclasses (storage, Jinja2, secrets) too.

#### Issue 5: `TracebackMessageError` separate lifecycle — **Open (low priority)**

Still uses its own logging mechanism (`error_mode: TracebackMessageErrorMode`). No real cost; works fine for fatal startup errors.

#### Issue 6: Repetitive Rich error handler functions — **Open**

`error_handlers.py` is still 434 lines / 11 handlers / one shape repeated. Helper extraction (`display_error_panel(...)`) would cut it roughly in half. Not on a phase plan yet — would land best as a tidy-up after Phase 6.

#### Issue 7: No full-chain error serialization integration test — **Open**

Inference layer has 60+ classification tests. The runner→CLI→JSON e2e snapshot is still missing. Would cover: pipeline failure with a known inference error → assert JSON has expected `error_category`, `retryable`, `model`, `provider`, `error_source`. Not on a phase plan yet — minimal effort, high signal.

---

### 5.3 Priority Matrix (refreshed)

| # | Issue | Effort | Impact | Status / Phase |
|---|---|---|---|---|
| I2 | Defaults on remaining uncategorized CogtError subclasses | Small | Medium | Phase 6.1 |
| I3-short | Drift-detection test for agent_output dicts | Small | Medium | Phase 6.5 |
| I1 | Extend ErrorReport metadata to non-inference exceptions | Medium | High | Phase 6.2 |
| I3-medium | Move hints/domains onto exception classes | Medium | Medium | Phase 6.3 / 6.4 |
| I4 | Make ToolError inherit from PipelexError | — | — | **Done** |
| Phase 4 | Markdown-default agent CLI output | Medium | Medium | [error-handling-phase-4-markdown-cli.md](error-handling-phase-4-markdown-cli.md) |
| Phase 5 | Move retry from gateway workers to PipeRouter | Medium | High | [error-handling-phase-5-retry-architecture.md](error-handling-phase-5-retry-architecture.md) |
| Phase 7 | Temporal bridge (`error_category.is_retryable` → `non_retryable`) | Small | Medium | [error-handling-phase-7-temporal-bridge.md](error-handling-phase-7-temporal-bridge.md) — Temporal branch |
| Instructor unwrap | Port Anthropic fix to OpenAI/Mistral/Google | Small per worker | High | [instructor-unwrap-other-workers.md](instructor-unwrap-other-workers.md) |
| I6 | Extract generic Rich error display helper | Medium | Low | Open — no phase plan |
| I7 | Full-chain error serialization integration test | Small | Medium | Open — no phase plan |
| I5 | Unify TracebackMessageError with PipelexError | Small | Low | Open — no phase plan |

---

### 5.4 Maturity Assessment (refreshed)

| Dimension | Rating | Notes |
|---|---|---|
| Exception hierarchy | 9/10 | Single-rooted, well-organized; ToolError fold-in closed the last gap. |
| Error context preservation | 9/10 | Consistent `from exc`, structured fields on key exceptions. |
| Third-party error transformation | 9/10 | All inference workers covered after Phase 3; `error_classification.py` is the source of truth. Modest deduction for the unfixed `instructor` unwrap on OpenAI/Mistral/Google. |
| Human-facing error delivery | 8/10 | Rich formatting with actionable tips; verbose handlers are an aesthetic, not a correctness, problem. |
| Agent-facing error delivery | 8/10 | `to_error_report()` is now the primary source; dual-source narrows further with Phase 6. |
| Error codes / stable identifiers | 4/10 | No codes yet; correctly deferred until a public API exists. |
| Validation error aggregation | 9/10 | `ValidateBundleError` + flattened extraction unchanged and still excellent. |
| Test coverage | 7/10 | Inference layer excellent; full-chain agent-output snapshot test still missing. |
| **Overall** | **8/10** | Up from 7.5. Phase 0–3 closed real gaps; the remaining work is well-scoped in Phase 4–7. |
