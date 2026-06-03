# Architecture — Layer Model, Class Hierarchy, Reporting

This doc is the structural reference the tracks build on. It describes the layer model errors flow through, the class hierarchy, and how structured error reporting works today.

## Layer model

```
Layer 5: CLI entry points          (catch + format for human/agent)
Layer 4: CLI factories             (catch setup errors, route to handlers)
Layer 3: Pipeline runner           (catch + wrap as PipelineExecutionError)
Layer 2: Pipe router / operators   (catch + wrap with pipe context)
Layer 1: Workers / SDK calls       (catch third-party + classify)
Layer 0: Third-party SDKs          (raw OpenAI/Anthropic/Google/etc. exceptions)
```

### Layer 0 → 1: SDK to domain

Every provider worker under `pipelex/plugins/*/` catches the SDK's typed exceptions and re-raises a `CogtError` subclass with:

- An `InferenceErrorCategory` value (TRANSIENT, CONFIGURATION, CONTENT, CAPACITY).
- An optional `user_action` hint (set per-instance, or as a class default).
- The model descriptor in the message (`self.inference_model.desc` or `model_id`).
- `from exc` to preserve the original SDK exception in the chain.

Pure classification helpers live in `pipelex/cogt/inference/error_classification.py`: `is_quota_exhaustion_openai`, `is_quota_exhaustion_anthropic`, `is_quota_exhaustion_google`, `is_quota_exhaustion_mistral`, `is_quota_exhaustion_aws`, `is_quota_exhaustion_gateway`, and `is_content_policy_violation`. Per-provider quota and content-policy patterns are defined alongside as module constants.

See [track-worker-classification.md](track-worker-classification.md) for the per-worker inventory.

### Layer 1 → 2: Pipe operators

Pipe operators define thin wrapper exceptions in `pipelex/pipe_operators/*/exceptions.py` and `pipelex/pipe_operators/exceptions.py`. The richest is `PipeOperatorModelAvailabilityError` in `pipelex/pipe_operators/exceptions.py`, which carries `run_mode`, `pipe_type`, `pipe_code`, `pipe_stack`, `model_handle`, and `fallback_list`.

### Layer 2 → 3: Pipeline runner

`PipelexRunner.execute_pipeline()` in `pipelex/pipeline/runner.py` catches:

| Caught | Wrapped as | Context attached |
|---|---|---|
| `PipeRouterError` | `PipelineExecutionError` | run_mode, pipe_code, output_name, pipe_stack |
| Other `PipelexError` | `PipelineExecutionError` | run_mode, pipe_code, output_name, pipe_stack |
| `ValidationError` (pydantic) | `PipeExecutionError` | formatted validation message |

`PipelineExecutionError` is defined at `pipelex/pipeline/exceptions.py`; the original is chained with `from exc` and telemetry events are emitted on failure.

### Layer 3 → 4: CLI factories

- Human: `pipelex/cli/cli_factory.py` catches init errors from `Pipelex.make()` and delegates to handlers in `pipelex/cli/error_handlers.py`.
- Agent: `pipelex/cli/agent_cli/commands/agent_cli_factory.py` catches the same set and sends each through `agent_error()` in `pipelex/cli/agent_cli/commands/agent_output.py`.

### Layer 4 → 5: Delivery

- **Human CLI** — Rich console; each error type has its own `handle_*` function in `error_handlers.py`, all building their panel through the shared `display_error_panel()` helper (red banner, structured fields, tip, doc/Discord links, `raise typer.Exit(1) from exc`).
- **Agent CLI** — Structured JSON or markdown via `agent_error()`, dispatched on the `--format` option (markdown default; carried by a per-invocation `ContextVar`). For `PipelexError` subclasses it reads `to_error_report()` and merges `hint` / `error_domain` / `retryable` from the lookup dicts only when not present on the report.
- **Bundle validation** — `ValidateBundleError` aggregates blueprint, factory, validation, and instantiation errors; `extract_validation_errors()` in `agent_output.py` flattens them into a list per-category.
- **Markdown special case** — `InferenceSetupRequiredError` is rendered as markdown to stdout (exit 0) for first-run guidance, independent of the `--format` option.

## Class hierarchy

`PipelexError` is the single root. The full top-level shape:

```
Exception
└── PipelexError                      pipelex/base_exceptions.py
    ├── PipelexUnexpectedError
    ├── PipelexConfigError
    ├── PipelexSetupError
    ├── SecurityError
    ├── ToolError                     pipelex/system/exceptions.py
    │   ├── NestedKeyConflictError
    │   ├── StorageError
    │   ├── Jinja2TemplateSyntaxError
    │   ├── SecretNotFoundError
    │   └── ...
    ├── MissingDependencyError        pipelex/system/exceptions.py
    ├── CredentialsError              pipelex/system/exceptions.py
    ├── CogtError                     pipelex/cogt/exceptions.py
    │   └── (many subclasses, see track-worker-classification.md)
    ├── PipeExecutionError            pipelex/pipeline/exceptions.py
    ├── PipelineExecutionError        pipelex/pipeline/exceptions.py
    ├── PipeStackOverflowError        pipelex/pipeline/exceptions.py
    ├── PipeRunError                  pipelex/pipe_run/exceptions.py
    │   ├── PipeRouterError
    │   ├── PipeRunParamsError
    │   └── PipeJobError
    ├── DeliveryError                 pipelex/pipe_run/exceptions.py
    ├── ConceptError                  pipelex/core/concepts/exceptions.py
    ├── StuffError                    pipelex/core/stuffs/exceptions.py
    ├── WorkingMemoryError            pipelex/core/memory/exceptions.py
    ├── LibraryError                  pipelex/libraries/exceptions.py
    ├── PipeControllerError           pipelex/pipe_controllers/exceptions.py
    ├── PipelexServiceError           pipelex/system/pipelex_service/exceptions.py
    │   ├── InferenceSetupRequiredError
    │   ├── GatewayTermsNotAcceptedError
    │   └── ...
    ├── PipelexInterpreterError       pipelex/core/interpreter/exceptions.py
    ├── GraphSpecError                pipelex/graph/exceptions.py
    └── KitError                      pipelex/kit/exceptions.py

TracebackMessageError                 pipelex/system/exceptions.py
└── FatalError
    ├── ConfigValidationError
    └── ConfigModelError              (also inherits from ValueError)
```

Notes:

- `PipelexError` lives at `pipelex/base_exceptions.py` (top-level), not under `pipelex/system/`. Several older docs reference the old location; treat any `pipelex/system/exceptions.py` reference for the root class as stale.
- Exception modules follow the **one `exceptions.py` per package** convention, with sub-packages (e.g. `pipelex/pipe_operators/llm/exceptions.py`) adding their own as needed.
- `TracebackMessageError` is the one exception type that uses a separate logging-on-construction mechanism (see "Open hierarchy issues" below).

### Three patterns for individual exceptions

- **Plain message-only exception** — used purely for type-based catching. Most subclasses.
- **Exception with structured fields** — carries context as instance attributes. Examples: `PipelineExecutionError`, `PipeOperatorModelAvailabilityError`, `ModelChoiceNotFoundError`, `InferenceBackendCredentialsError`.
- **Non-exception structured error data** — `BaseModel` / dataclass aggregated into a raised exception, not raised itself. Examples: `ErrorReport`, `PipelexBundleBlueprintValidationErrorData`, `PipeValidationErrorData`, `PipeFactoryErrorData`.

## Structured error reporting

`ErrorReport` (`pipelex/base_exceptions.py`) is a frozen `BaseModel` (`ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`) — the single source of truth for all error serialization (CLI JSON output, agent output, Temporal error details). Frozen so a cause-enrichment pass rebuilds via `model_copy` rather than mutating an outer wrapper's identity in place.

```
ErrorReport
  error_type:            str
  message:               str
  title:                 str
  type_uri:              str
  error_category:        str | None
  error_domain:          str | None
  retryable:             bool | None
  user_action:           UserAction | None
  model:                 str | None
  provider:              str | None
  provider_metadata:     ProviderErrorMetadata | None
  caller_facing_message: bool
```

`title` / `type_uri` are the stable identity pair surfaced to consumers — every `PipelexError` populates them automatically via `PipelexError.title()` / `PipelexError.type_uri()` (auto-derived from the class name unless a subclass declares `_declared_title` / `_declared_type_uri`), so consumers never humanize or kebab-case a class name themselves.

Serialization goes through `to_dict(disclosure_mode=DisclosureMode.VERBOSE)`, not a plain dump. `DisclosureMode` has two values:

- `VERBOSE` — every populated (non-`None`) field; the strict inverse of `from_dict`, so it round-trips. Use on internal-trust boundaries (webhook payloads, internal RPCs) that need round-trip fidelity.
- `STRICT` — a lossy projection for untrusted external surfaces: `provider` / `model` are always dropped, `provider_metadata` is reduced to a curated subset (`status_code`, `retry_after_seconds`), and unless the report sets `caller_facing_message` its `message` is replaced with a generic placeholder and `user_action` dropped — leaving only the stable identifiers. `caller_facing_message` flags reports whose `message` is genuinely caller-facing copy (e.g. a `.mthds` syntax error from `PipelexInterpreterError`), so STRICT keeps it. STRICT keys on message *provenance*, not on `error_domain` (which is inherited up the `__cause__` chain).

`PipelexError.to_error_report()` returns `error_type`, `message`, `title`, `type_uri`, the class-level `error_domain`, `user_action`, and `caller_facing_message`. `CogtError.to_error_report()` overrides to add `error_category`, `retryable` (derived from category), `provider_metadata`, and reads `model_handle` / `backend_name` when present on the instance. `to_error_report()` enriches from the `__cause__` chain, so a wrapper exception surfaces the inference metadata of the underlying `CogtError` — but `title` / `type_uri` are *wrapper-wins* (enrichment never overwrites the outermost wrapper's identity).

`error_category` carries an `InferenceErrorCategory` value (`pipelex/cogt/exceptions.py`). Only `TRANSIENT` is retryable; `CONFIGURATION` / `CONTENT` / `CAPACITY` / `AMBIGUOUS` / `UNKNOWN` are not. The `AMBIGUOUS` / `UNKNOWN` split is deliberate: `AMBIGUOUS` means the error type is known but the outcome is not (e.g. a connection dropped mid-request, so a non-idempotent operation may or may not have committed) — a blind retry is unsafe, so it is non-retryable by design; `UNKNOWN` means classification failed outright. Keeping them separate lets a non-idempotent worker (e.g. `azure_img_gen_worker.py`) pick `AMBIGUOUS` rather than the looser `UNKNOWN`.

See [track-metadata-model.md](track-metadata-model.md) for the remaining gap: `error_domain` is now a class-level attribute and inference errors fully self-describe, but a long tail of non-inference `PipelexError` subclasses still depend on the lookup dicts in `pipelex/cli/agent_cli/commands/agent_output.py` for their `hint` / `error_domain`.

## Open hierarchy issues

Tracked here because they don't fit cleanly into a track:

- **`TracebackMessageError` separate lifecycle.** `TracebackMessageError` (`pipelex/system/exceptions.py`) logs its message on construction and chooses between `logger.error` and `logger.exception` based on a `ClassVar` `error_mode`. It is rooted under `PipelexError` but doesn't participate in `to_error_report()` enrichment. No real cost today — it works fine for fatal startup errors. Low priority.

## Related tracks

- [track-metadata-model.md](track-metadata-model.md) — `ErrorReport`, `error_category`, `error_domain`, `user_action`, dict drift.
- [track-worker-classification.md](track-worker-classification.md) — Layer 0 → 1 details.
- [track-cli-delivery.md](track-cli-delivery.md) — Layer 4 → 5 details.
- [track-temporal-integration.md](track-temporal-integration.md) — how the layer model extends into Temporal workflows.
