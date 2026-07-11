---
title: "Error Model"
description: "How Pipelex classifies, carries, and reports errors — the ErrorReport schema, inference error categories, error domains, the layer model, worker classification, and how classification survives a distributed worker boundary."
---

# Error Model

In Pipelex, an error is **data**, not a control-flow accident. Every failure is classified once — at the layer that knows the most about it — and that classification travels intact to every consumer: the human reading a Rich panel, the agent parsing JSON, a distributed worker's retry engine, and the HTTP adapter picking a status code.

This page covers the contract that makes that possible: the `ErrorReport` schema, the classification enums, how inference workers classify SDK exceptions, how classification survives every wrapping layer, and how it survives serialization across a distributed worker boundary.

---

## Design Principle

Three rules hold across the codebase, and everything else builds on them.

**Single-rooted hierarchy.** Every custom exception inherits from `PipelexError` (`pipelex/base_exceptions.py`). There is one root, so one `to_error_report()` contract covers the whole tree.

**Classify at the source, never lose it.** The layer that catches a third-party exception knows the most about it. It classifies there. Every layer above is a *wrapper* — it adds context (pipe code, stack) but inherits the classification rather than re-deriving or discarding it.

**No broad catches in business logic.** `except Exception` is allowed only at CLI entry points and async task roots. Ruff rule `BLE001` enforces this — an unexpected exception crashes loudly instead of being silently swallowed.

!!! info "Why classify, instead of just propagating the exception?"
    A raw `openai.RateLimitError` tells a Python `except` clause what to catch, but it does not tell a distributed worker's retry engine whether to retry, the HTTP adapter which status to emit, or an agent whether the failure is the user's fault. Classification turns an exception into a decision input that every consumer can act on uniformly.

---

## The Layer Model

An error rises through a series of layers. Each layer has exactly one job.

| Layer | Role | What it does with errors |
|-------|------|--------------------------|
| **5 — CLI entry points** | `pipelex` / `pipelex-agent` commands | Catch, format for human (Rich) / agent (JSON·MD) / HTTP |
| **4 — CLI factories** | `cli_factory.py`, `agent_cli_factory.py` | Catch setup errors, route to handlers |
| **3 — Pipeline runner** | `PipelexMTHDSProtocol.execute()` | Catch + wrap as `PipelineExecutionError` |
| **2 — Pipe router / operators** | `PipeRouter`, pipe operators | Catch + wrap with pipe context (`pipe_code`, `pipe_stack`) |
| **1 — Workers / SDK calls** | `pipelex/plugins/*/` | **Catch the SDK exception → classify → raise `CogtError`** |
| **0 — Third-party SDKs** | OpenAI, Anthropic, Google, … | Raise raw, untyped provider exceptions |

Classification happens once, at **Layer 1**. Layers 2–5 are wrappers: they attach context as they catch and re-raise, but the `error_category`, `error_domain`, `model`, and `provider` set at Layer 1 reach Layer 5 unchanged (see [Cause-Chain Enrichment](#cause-chain-enrichment)).

---

## ErrorReport — the Serialization Schema

`ErrorReport` (`pipelex/base_exceptions.py`) is the single source of truth for error serialization. It is a frozen Pydantic model with `extra="forbid"`.

| Field | Type | Meaning |
|-------|------|---------|
| `error_type` | `str` | The exception class name |
| `message` | `str` | Human-readable message |
| `title` | `str` | Stable human-readable summary — the RFC 7807 `title` |
| `type_uri` | `str` | Per-class documentation URI — the RFC 7807 `type` |
| `error_category` | `str \| None` | `InferenceErrorCategory` value (inference errors only) |
| `error_domain` | `str \| None` | `ErrorDomain` value — `input` / `config` / `runtime` |
| `retryable` | `bool \| None` | Whether a retry could succeed |
| `user_action` | `UserAction \| None` | Typed advice — `kind` + free-form `detail` |
| `model` | `str \| None` | Model handle, when the failure is attributable to one |
| `provider` | `str \| None` | Backend name, when attributable |
| `provider_metadata` | `ProviderErrorMetadata \| None` | SDK metadata — status code, request id, `retry_after` |
| `validation_errors` | `list[ValidationErrorItem] \| None` | Structured per-error diagnostics on a bundle-validation failure (`ValidateBundleError` only) |

`PipelexError.to_error_report()` is the entry point. `to_dict()` serializes, dropping `None` fields; `from_dict()` is its strict inverse.

### `validation_errors` — structured bundle-validation diagnostics

A bundle-validation failure (`ValidateBundleError`) aggregates per-error data across stages and projects it onto `validation_errors` as a list of typed `ValidationErrorItem`s, so the structured error report an HTTP API surfaces carries machine-mappable diagnostics (not just a single `detail` string). Each item's `category` is one of the **closed** `ValidationErrorCategory` set:

- `blueprint_validation` — interpreter / blueprint-validation faults. A blueprint-stage `PipeValidationError` raised *inside* a pydantic model validator (e.g. the PipeBatch `input_item_name` == `input_list_name` collision, or the SubPipe `batch_over` == `batch_as` collision — both `batch_item_name_collision`) is wrapped by pydantic as a `value_error`; the blueprint categorizer unwraps it (`ctx["error"]`) so the item keeps its structured `error_type` and `pipe_code` / `domain_code` locators instead of degrading to the no-`error_type` residual. The item stays in `blueprint_validation` (not `pipe_validation`) because the fault genuinely surfaced at the parse boundary, before any pipe was instantiated — only the `error_type` is recovered, not the stage. This category also serves as the **last-resort residual**: a parse-level failure (a TOML-syntax error, an empty blueprint, a bundle-elaborator failure) is raised with only a message and no categorized data, so when *nothing else* produced an item the builder projects that message as one `blueprint_validation` item (no `error_type`, no `source` — the bundle could not become a blueprint at all).
- `pipe_factory` — pipe-factory failures (e.g. a missing concept).
- `pipe_validation` — pipe/concept validation (missing input variable, type mismatch).
- `dry_run` — the **residual** dry-run failure (`DryRunError` / `PipeRunError`) with no structured locator. It is projected as one message-only item **only when no categorized error has data**. It is graph-level, so it typically carries **no `source`**.

Together the two residuals make the **structured-info invariant total**: every invalid verdict carries a non-empty `validation_errors[]`, never a bare message. The builder tries the channels in order — categorized data, then the `dry_run` residual (the more specific channel), then the `blueprint_validation` fallback — and emits exactly one residual only when no earlier channel produced an item.

Besides `category` and `message`, each item carries whatever identity fields its stage produced — `error_type`, `pipe_code`, `concept_code`, `domain_code`, `field_path`, `field_name`, `variable_names`, `missing_concept_code`, `declared_concepts`, and a `source` (the declaring file path, or the per-content source the in-memory load path was given) that hands a consumer the owning file for cross-file diagnostic placement. When the error has a deterministic remedy, the item also carries a [`suggested_fix`](#suggested_fix-structured-deterministic-fixes).

**Signatures are never an error.** An unimplemented `PipeSignature` reached during validation is a *runnability fact*, not a validation failure: the validator no longer raises on it. The assembled library's outstanding signatures ride the validation report's `pending_signatures`, and `is_runnable = not pending_signatures`. `allow_signatures` is a sweep-mechanics flag only (whether signature pipes are mock-run and listed in `validated_pipes`) — it does not change the verdict, so strict ≡ lenient in the report body. The "is this a failure?" decision moves to the consumer: the CLI exits non-zero on `not is_runnable` unless `--allow-signatures`; the HTTP caller reads `is_runnable`. (The **execute/run** path is different: running a stub still raises `PipeSignatureNotExecutableError`.)

**Host-wiring guards are programmer errors, not content verdicts.** `validate_bundle`'s "provide exactly one of `mthds_contents` / `mthds_file_path`" guard and `resolve_crate_from_contents`'s `mthds_sources`-length-mismatch guard raise `PipelexUnexpectedError` (→ 500, redacted under STRICT), not `ValidateBundleError` — a caller wiring bug must not be reported as if the submitted bundle were invalid. The empty-`mthds_contents` guard stays caller-facing (it can legitimately reflect an end user submitting no bundles).

`ValidationErrorItem` and the builder are the single source of truth across surfaces: `build_validation_error_items()` (`pipelex/pipeline/validation_errors.py`) is called by both `ValidateBundleError.to_error_report()` (the API path) and the agent CLI's `extract_validation_errors()` (the CLI JSON envelope), so the two structured shapes cannot drift. The item lives in `pipelex/base_exceptions.py` alongside `ErrorReport` — not next to the source error-data models — because `ErrorReport` references it as a typed field and the root exceptions module must not import the `pipelex.core` error modules.

`validation_errors` is one of the fields kept under STRICT disclosure (it is in `_STRICT_KEPT_FIELDS`): the items describe the caller's *own* submitted bundle, not server internals, so redacting them would gut the hosted path's diagnostics.

```python
report = exc.to_error_report()
report.to_dict()         # {"error_type": "LLMCompletionError", "message": "...", ...}
ErrorReport.from_dict(d) # strict inverse — raises ValidationError on a malformed dict
report.http_status       # 422 / 429 / 500 — for HTTP adapters
```

!!! warning "`ErrorReport` is `extra="forbid"`"
    `from_dict()` rejects unknown keys, so it is the strict inverse of `to_dict()`. A report dict that crosses a serialization boundary and fails validation on the way back is an internal contract bug — the writer and the reader share the schema within one deploy. A cross-boundary recovery helper that rebuilds a report (e.g. a distributed-worker bridge) is expected to catch that `ValidationError` and synthesize a fallback report so failure-webhook delivery stays intact while keeping the contract bug visible; any other caller of `from_dict()` should treat the validation failure as a bug to fix.

### `suggested_fix` — structured deterministic fixes

When a validation error has a deterministic remedy, its `ValidationErrorItem` carries a `suggested_fix` — a `SuggestedFix` (`pipelex/suggested_fix.py`, deliberately stdlib+pydantic-only so `pipelex.base_exceptions` can import it without a cycle; naming is brand-neutral, fixes are a language-level concept):

- `fix_code` — the kebab-case rule id (e.g. `match-sequence-output`). The planner's `KNOWN_FIX_CODES` set is the validation set for user-facing rule filters (`--select` / `--ignore`); an unknown code is rejected loudly, never lenient-ignored, because a typo'd filter selects *behavior*.
- `description` — human-readable statement of the change.
- `safety` — `safe` fixes may be auto-applied; `unsafe` ones require explicit opt-in.
- `source` — the file the ops target, when known (multi-file libraries). An applier must only apply ops to the file they target.
- `ops[]` — the fix itself, as **semantic TOML patch ops** addressed by table path (`FixOpKind`: `set_key`, `ensure_table`, `delete_key`, `delete_table`, `rename_table_key`; each op's `table_path` follows the same conventions as the items' `field_path`). The ops are the machine contract; any rendered diff or `💡 Suggested fix:` line is presentation.

The **fix planner** (`pipelex/pipeline/fixes/planner.py`) translates enriched typed error data into `SuggestedFix` payloads — pure functions keyed strictly on `error_type` + structured fields, never on message strings. Each rule fires only when its enrichment is present (set only at the raise sites that know the correct value), so the same error type raised elsewhere without enrichment is structurally suppressed. The planner runs inside `build_validation_error_items()`, so every consumer of the validation report — CLI, API, MCP — sees fixes with zero extra plumbing.

Applying fixes is the runtime's job too: the **applier** (`pipelex/pipeline/fixes/applier.py`) mutates a tomlkit DOM in place per op (guarded — an op whose target table is absent is skipped and reported, never raised) and then reflows the whole file to canonical MTHDS style, and the **convergence loop** (`pipelex/pipeline/fixes/fix_loop.py`) runs validate → apply SAFE fixes → re-validate to a fixed point, reporting non-convergence loudly. The user-facing surface is [`pipelex fix bundle`](../tools/cli/fix.md).

On the hosted API the same payload rides the wire verbatim as `validation_errors[].suggested_fix`; how it appears in HTTP error responses is documented on the API side, in `pipelex-api`'s `docs/error-responses.md` → "Suggested fixes".

---

## Classification Enums

Two `StrEnum`s drive every downstream decision.

### InferenceErrorCategory

Defined in `pipelex/cogt/exceptions.py`. Drives retry decisions — `is_retryable` is `True` only for `TRANSIENT`.

| Category | Meaning | Retryable | Typical cause |
|----------|---------|-----------|---------------|
| `TRANSIENT` | A brief, self-correcting failure | ✅ | Rate limit, 5xx, connection blip |
| `CONFIGURATION` | The setup is wrong | ❌ | Bad API key, missing backend |
| `CONTENT` | The input or prompt is wrong | ❌ | Content-policy violation, bad prompt |
| `CAPACITY` | Account quota / billing exhausted | ❌ | `insufficient_quota`, HTTP 402 |
| `AMBIGUOUS` | Outcome unknown — may have committed | ❌ | Connection dropped mid-request |
| `UNKNOWN` | Could not classify | ❌ | Unrecognized inner exception |

```python
class InferenceErrorCategory(StrEnum):
    TRANSIENT = "transient"
    # ... CONFIGURATION, CONTENT, CAPACITY, AMBIGUOUS ...
    UNKNOWN = "unknown"

    @property
    def is_retryable(self) -> bool:
        match self:
            case InferenceErrorCategory.TRANSIENT:
                return True
            case _:  # all other categories
                return False
```

!!! info "`AMBIGUOUS` vs `UNKNOWN`"
    `AMBIGUOUS` means the *error type is known* but the operation may or may not have committed — a blind retry is unsafe for a non-idempotent call. `UNKNOWN` means classification itself failed. Both are non-retryable, for different reasons.

### ErrorDomain

Defined in `pipelex/base_exceptions.py`. Set as a class-level attribute on the exception, drives HTTP status.

| Domain | Meaning | HTTP status | Who can fix it |
|--------|---------|-------------|----------------|
| `INPUT` | Caller sent something it can fix | **422** | The caller |
| `CONFIG` | Environment / configuration change needed | **500** | The operator |
| `RUNTIME` | A failure during execution | **500** | Depends on the cause |

`error_domain_to_http_status()` is the pure mapping table. `ErrorReport.http_status` layers one rule on top: a provider 429 (`provider_metadata.status_code == 429`) takes precedence over the domain, so the API can emit a `Retry-After` header.

```python
class PipelexConfigError(PipelexError):
    error_domain = ErrorDomain.CONFIG     # class-level — every instance carries it
```

---

## Worker Classification

Layer 0 → Layer 1. Every inference worker under `pipelex/plugins/*/` catches its SDK's typed exceptions and re-raises a categorized `CogtError`.

### The Uniform Shape — Extract / Classify / Render

Every inference worker's SDK-exception handler collapses to a three-step pipeline: **Extract** turns the SDK exception into a provider-blind `ProviderErrorMetadata`, **Classify** maps that metadata to a category + user-action, and **Render** picks the `CogtError` subclass to raise.

```python
except (APIError, APIConnectionError, APITimeoutError) as exc:
    metadata = extract_openai_metadata(exc)
    classification = classify_inference_error(metadata)
    raise render_llm_error(
        family=InferenceErrorFamily.LLM_COMPLETION,
        metadata=metadata,
        classification=classification,
        model_desc=self.inference_model.desc,
    ) from exc
```

The three steps live in three modules. Only the per-provider Extract functions stay plugin-local; Classify and Render are single shared functions.

| Module | Step | What it owns |
|--------|------|--------------|
| `pipelex/cogt/inference/error_classification.py` | Extract | `ProviderErrorMetadata`, `SDKErrorEnvelope`, `UserAction`, `UserActionKind`, the 12 `extract_*_metadata` functions, plus pure discriminators (`is_quota_exhaustion`, `is_content_policy_violation`, `is_network_error`) exposed as `@property` on the metadata |
| `pipelex/cogt/inference/error_classify.py` | Classify | `classify_inference_error()` — provider-blind mapping from `ProviderErrorMetadata` → `ClassificationResult(category, user_action_kind, is_model_not_found)` |
| `pipelex/cogt/inference/error_render.py` | Render | `render_llm_error()` / `render_img_gen_error()` / `render_extract_error()` / `render_search_error()` — picks the `CogtError` subclass from `InferenceErrorFamily` plus `is_model_not_found` (e.g. `LLMModelNotFoundError` vs `LLMCompletionError`) |

Provider-specific nuance is normalized away in Extract (e.g. Google's `code` becomes `status_code`; AWS Bedrock error codes are mapped to HTTP statuses), so Classify has no provider branching. HTTP status drives classification; status-less errors dispatch on the SDK exception type name. The `tests/unit/pipelex/cogt/inference/test_provider_classification_parity.py` meta-test walks every `ProviderName` against the extract-fn registry so adding a new provider without wiring it fails fast.

### ProviderErrorMetadata and UserAction

Every raised inference error carries structured SDK metadata and typed advice.

```python
class ProviderErrorMetadata(BaseModel):
    provider: str
    sdk_exception_type: str
    status_code: int | None = None
    request_id: str | None = None
    retry_after_seconds: float | None = None
    provider_error_code: str | None = None
    body: Any | None = Field(default=None, exclude=True)   # may carry secrets
```

!!! warning "`body` is excluded from serialization"
    The raw provider response `body` can carry account ids, billing details, or credential fragments. It is held in-process but `exclude`d from every serialized form — CLI JSON, agent output, and any serialized worker payload.

`UserAction` pairs a discrete `UserActionKind` (`WAIT_AND_RETRY`, `CHECK_BILLING`, `CHECK_CREDENTIALS`, `CHANGE_INPUT`, `CHANGE_MODEL`, `CONTACT_SUPPORT`, `UNKNOWN`) with a free-form `detail` string — so the CLI can render consistent guidance while keeping provider-specific text.

### The `instructor` Unwrap

On structured-generation paths, `instructor` wraps the real SDK exception in an `InstructorRetryException`. `extract_underlying_sdk_exception()` recovers it, so it routes through the same per-provider categorization as the plain-text path. A genuinely unrecognized inner exception (e.g. a `pydantic.ValidationError` from a schema mismatch) lands in `UNKNOWN` rather than being mis-labelled as a `CONTENT`-policy violation.

### Model and Provider Attribution

Inference-failure leaf errors (`LLMCompletionError`, `ImgGenGenerationError`, …) are raised deep inside a plugin and do not know which model handle invoked them. Each worker family fills that in at its public-method chokepoint:

```python
def fill_model_and_provider(self, model_handle: str | None, backend_name: str | None) -> None:
    """Fill model_handle / backend_name from the worker, only when still unset."""
```

---

## Cause-Chain Enrichment

A wrapper exception — `PipeRunError` → `PipeRouterError` → `PipelineExecutionError` — carries no `error_category` of its own. `to_error_report()` enriches the report from the `__cause__` chain, so the inference classification survives every wrapping layer.

```python
def _enrich_error_report_from_cause(self, report: ErrorReport) -> ErrorReport:
    cause = self.__cause__
    if not isinstance(cause, PipelexError):
        return report
    cause_report = cause.to_error_report()
    return ErrorReport(
        error_type=report.error_type,                                  # keep own identity
        message=report.message,
        error_category=report.error_category or cause_report.error_category,
        error_domain=report.error_domain or cause_report.error_domain,
        # ... retryable, user_action, model, provider, provider_metadata ...
    )
```

A wrapper keeps its own `error_type` and `message` but inherits every classification field it does not set itself.

!!! warning "Overrides must call the enrichment helper"
    A `to_error_report()` override on a subclass **must** end with `self._enrich_error_report_from_cause(report)`. Otherwise that subclass becomes a black hole that drops the cause's classification. A cyclic-`__cause__` guard ensures a malformed chain can never turn error reporting into a `RecursionError`.

---

## Crossing a Distributed Worker Boundary

The error model is built to survive serialization. Because `ErrorReport` round-trips through `to_dict()` / `from_dict()`, a failure that happens on a remote worker can reach the submitting process with its full classification intact — not just a message string.

The runtime itself stays transport-agnostic: the machinery that carries an error across a worker boundary ships in the **host-runtime plugin** for each distributed backend, not in core. A backend plugin is responsible for three things.

**Packing.** Convert a `PipelexError` into the transport's failure type and stash `to_error_report().to_dict()` in its details payload, so worker and submitter code keep the full classification rather than a bare message. The same step derives the transport's retry decision from `InferenceErrorCategory.is_retryable`.

**Recovering.** On the submitter side, walk the returned failure, pull the packed dict, and rebuild the `ErrorReport`. Recovery is **total**: when no report dict is found — a non-Pipelex exception, a worker crash, a timeout — the plugin synthesizes a fallback report so the recovery path always has structured classification to surface.

**A fail-safe floor.** Ensure a domain error that escapes the conversion path fails the unit of work *terminally* rather than hanging. In a durable-execution system the default for an unconverted exception might be to retry forever, so "convert all the errors we know about" is not enough — the floor must hold for the errors, and the code paths, that nobody enumerated.

**Net effect:** a pipe failing on a remote worker reaches the CLI and HTTP adapters with the *same* `error_category` / `retryable` / `model` / `provider` / `user_action` as the identical failure run locally — and a failure that escapes conversion fails loud and bounded instead of hanging.

See [Runtime Bridge & Transport](./runtime-bridge-and-transport.md) for the boundary these converters span; the per-backend converters themselves live in the host-runtime plugins.

---

## Interfaces

### CLI

The agent CLI (`pipelex-agent`) emits a structured error to **stderr**, markdown by default and JSON with `--error-format json`. When `--error-format` is omitted it **inherits the value of `--format`** (the success-output flag) — so `--format json` still flips both as it did before the split. Both exit with code 1.

| Command | Error output |
|---------|--------------|
| `run`, `validate`, `init`, `models`, `check-model`, `doctor` | Markdown (default) or JSON via `--error-format` (or via `--format`, which `--error-format` inherits) |
| `inputs`, `concept`, `pipe`, `accept-gateway-terms` | JSON only |
| `fmt`, `lint` | Native `plxt` output (subprocess passthrough); falls back to JSON only when the `plxt` binary itself is missing |

The human CLI (`pipelex`) renders a Rich error panel — red banner, structured fields, the `user_action` tip, doc/Discord links — through the shared `display_error_panel()` helper in `pipelex/cli/error_handlers.py`.

#### Validate exit-code policy (0 / 1 / 2)

The `validate` surface — both the bare `pipelex validate {bundle,method,pipe}` group and the agent CLI's `pipelex-agent validate` — exits with **three** codes that mirror the hosted `/validate` 200-verdict-vs-non-2xx-no-verdict split:

| Exit | Class | Condition |
|------|-------|-----------|
| `0` | valid | `is_valid` — including valid-but-not-runnable **with** `--allow-signatures` |
| `1` | negative verdict | a produced "no": an invalid bundle (`ValidateBundleError`), or valid-but-not-runnable **without** `--allow-signatures` (a strict signature breach) |
| `2` | no verdict | the CLI could not produce a verdict — bad args, an unresolvable target (no `.mthds` in a directory, a missing file, an unknown/ambiguous pipe code), or a setup/internal error during validate |

**The verdict lives in the structured `is_valid` field, not the exit code.** The exit code is a convenience signal for naive shell/CI/Makefile use (`set -e`, `cmd && next`, `if cmd; then`); machine consumers (hooks, the Codex hook, runners) MUST read `is_valid` (and `error_domain`) from the JSON for their block/warn decisions rather than branching on the exit code. Decoupling the verdict from the exit code is what keeps any future exit-code change non-breaking. The 1-vs-2 split is also additive for flat consumers: both stay non-zero, so anything that only tests zero-vs-non-zero is unaffected.

Implementation: the agent CLI threads `exit_code` through `agent_error(...)` (`agent_output.py`, default 1); the validate commands pass `exit_code=2` at every no-verdict site and keep the default 1 on the `ValidateBundleError` arm and the signature gate. The bare CLI sets the code directly via `typer.Exit(...)` in `cli/commands/validate/*` and via the `exit_code` parameter on `handle_model_choice_error` / `handle_model_availability_error` in `cli/error_handlers.py`. Shared boot handlers (`make_pipelex_for_cli`'s gateway/inference/telemetry/model-deck-preset paths) stay exit 1 — they are shared across `run`/`build`/`validate` and out of the validate-policy scope.

### API

`pipelex` is a library — there is no API server in the package. Downstream HTTP repos consume the `ErrorReport`:

- `error_domain_to_http_status(error_domain)` — pure domain → status table.
- `ErrorReport.http_status` — full property, layering the provider-429 passthrough on top.

A downstream FastAPI exception handler calls `ErrorReport.http_status` and is a trivial adapter — it must not redefine the mapping.

### Inputs and Outputs

**Inputs.** `to_error_report()` takes a live `PipelexError`. `ErrorReport.from_dict()` takes a `to_dict()` payload — strictly, raising `ValidationError` on drift. (A distributed-worker bridge adds a cross-boundary recovery helper that walks a returned failure's `__cause__` chain and rebuilds the report; it lives in the host-runtime plugin, not core.)

**Outputs.** `to_error_report()` returns an `ErrorReport`; `to_dict()` returns a `None`-free `dict`. Side effects: telemetry events emitted on pipeline failure at Layer 3; the agent CLI writes to stderr and raises `typer.Exit(...)` — code 1 by default, or the validate surface's 0/1/2 policy (see [Validate exit-code policy](#validate-exit-code-policy-0-1-2)).

---

## Architecture

```mermaid
flowchart TB
    SDK["Layer 0 — SDK exception<br/>(openai.RateLimitError)"]
    W["Layer 1 — Worker classifies<br/>is_quota_exhaustion_*() → CogtError<br/>+ InferenceErrorCategory + ProviderErrorMetadata"]
    WRAP["Layers 2-3 — Wrappers<br/>PipeRouterError → PipelineExecutionError<br/>(attach pipe context)"]
    REPORT["ErrorReport<br/>via to_error_report() + cause-chain enrichment"]

    SDK -->|"raise ... from exc"| W
    W -->|"raise ... from exc"| WRAP
    WRAP --> REPORT

    REPORT --> RICH["Human CLI<br/>Rich panel"]
    REPORT --> AGENT["Agent CLI<br/>JSON / Markdown"]
    REPORT --> HTTP["HTTP adapters<br/>.http_status"]

    W -.->|"pack on worker"| TEMP["Distributed worker bridge (plugin)<br/>report packed into transport details"]
    TEMP -.->|"recover on submitter"| REPORT

    classDef src fill:#fff3e0,stroke:#e65100,color:#000
    classDef cls fill:#e8eaf6,stroke:#3949ab,color:#000
    classDef out fill:#e8f5e9,stroke:#2e7d32,color:#000
    class SDK src
    class W,WRAP,REPORT,TEMP cls
    class RICH,AGENT,HTTP out
```

---

## Implementation

### Class Hierarchy

`PipelexError` is the single root. `CogtError` is the inference branch — it overrides `to_error_report()` to add `error_category`, `retryable`, `user_action`, `provider_metadata`, and reads `model_handle` / `backend_name` from the instance.

```
Exception
└── PipelexError                  base_exceptions.py — error_domain, user_action, to_error_report()
    ├── PipelexConfigError         → error_domain = CONFIG
    ├── PipelexSetupError          → error_domain = CONFIG
    ├── CogtError                  cogt/exceptions.py — error_category, provider_metadata
    │   ├── LLMCompletionError      ← per-instance category from the worker
    │   ├── ImgGenGenerationError   ← per-instance category
    │   ├── ModelNotFoundError      ← sibling family raised on provider HTTP 404
    │   │   ├── LLMModelNotFoundError / ImgGenModelNotFoundError
    │   │   └── ExtractModelNotFoundError / SearchModelNotFoundError
    │   └── ... (see worker classification) ...
    ├── PipelineExecutionError      pipeline/exceptions.py — error_domain = RUNTIME
    └── ... (one exceptions.py per package) ...
```

### Factory-time vs Runtime

| When | What carries metadata | How |
|------|----------------------|-----|
| **Class definition** | `error_domain`, `error_category` defaults, `user_action` defaults | Class-level attributes — one source of truth per exception type |
| **Raise time** | Per-instance `error_category`, `user_action`, `provider_metadata` | Constructor args — set by the worker that classified the failure |
| **Report time** | `model`, `provider`, cause-chain fields | `fill_model_and_provider()` at the worker chokepoint; `_enrich_error_report_from_cause()` on `to_error_report()` |

The "outcome" exceptions (`LLMCompletionError`, `ImgGenGenerationError`, `ExtractJobFailureError`, `SearchJobFailureError`) intentionally carry **no** class-level `error_category` — their category is genuinely per-instance, decided by the worker.

---

## Reference

### Quick-Ref

```python
# Produce a report from any PipelexError
report = exc.to_error_report()          # enriched from the __cause__ chain
payload = report.to_dict()              # None-free dict for serialization

# Consume a report
report.http_status                      # 422 / 429 / 500
report.user_action_detail()             # free-form advice text, or None
report.error_category                   # "transient" / "capacity" / ...

# Round-trip across a boundary
ErrorReport.from_dict(payload)           # strict inverse of to_dict()

# Retry decision
InferenceErrorCategory.TRANSIENT.is_retryable   # True — only TRANSIENT
```

### File → Purpose

| File | Purpose |
|------|---------|
| `pipelex/base_exceptions.py` | `PipelexError`, `ErrorReport`, `ErrorDomain`, `ValidationErrorItem`, `error_domain_to_http_status()` |
| `pipelex/pipeline/validation_errors.py` | `build_validation_error_items()` — shared CLI/API structured bundle-validation builder |
| `pipelex/cogt/exceptions.py` | `CogtError`, `InferenceErrorCategory` |
| `pipelex/cogt/inference/error_classification.py` | Extract — `ProviderErrorMetadata`, `SDKErrorEnvelope`, `UserAction`, `UserActionKind`, per-provider `extract_*_metadata` functions, pure discriminators |
| `pipelex/cogt/inference/error_classify.py` | Classify — `classify_inference_error()`, `ClassificationResult` |
| `pipelex/cogt/inference/error_render.py` | Render — `render_llm_error()` / `render_img_gen_error()` / `render_extract_error()` / `render_search_error()`, `InferenceErrorFamily` |
| `pipelex/cogt/inference/provider_name.py` | `ProviderName` enum keying the extract-fn registry |
| `pipelex/plugins/*/` | Per-provider inference workers — Layer 0 → 1 classification |
| `pipelex/pipeline/exceptions.py` | `PipelineExecutionError`, `PipeExecutionError` |
| `pipelex/cli/error_handlers.py` | Human CLI Rich panels — `display_error_panel()` |
| `pipelex/cli/agent_cli/commands/agent_output.py` | Agent CLI JSON / markdown delivery |

### Behavior Summary

| Scenario | Behavior |
|----------|----------|
| Rate limit hit | `TRANSIENT` → retryable; transport retry honors `Retry-After` |
| Quota / billing exhausted | `CAPACITY` → non-retryable; `UserAction(CHECK_BILLING)` |
| Bad API key | `CONFIGURATION` → non-retryable; `error_domain = CONFIG` → HTTP 500 |
| Model or deployment not found (provider HTTP 404) | Raises a dedicated `*ModelNotFoundError` sibling (`LLMModelNotFoundError`, `ImgGenModelNotFoundError`, `ExtractModelNotFoundError`, `SearchModelNotFoundError`); operator re-raises `PipeOperatorModelAvailabilityError` |
| Content-policy violation | `CONTENT` → non-retryable; `UserAction(CHANGE_INPUT)` |
| LLM returns schema-mismatched JSON | `instructor` re-asks; if exhausted → `UNKNOWN` |
| Connection dropped mid-request | `AMBIGUOUS` → non-retryable (outcome unknown) |
| Wrapper exception (no own category) | Inherits cause's classification via enrichment |
| Failure on a distributed worker | `ErrorReport` recovered from the transport's serialized details — same classification as local |
| Worker exception with no `ErrorReport` | Synthesized fallback report — `error_domain = RUNTIME` |

---

## Next Steps

- [Pipe Routing & Execution](./pipe-routing-and-execution.md) — the layer model errors rise through
- [Runtime Bridge & Transport](./runtime-bridge-and-transport.md) — the process boundary the error bridge spans (the per-backend error converters live in the host-runtime plugins)
- [Cogt Configuration](../configuration/config-technical/cogt-config.md) — `transport_max_retries` and the Tier 1 retry policy
- [Agent CLI](../tools/cli/agent-cli.md) — the JSON / markdown error contract
