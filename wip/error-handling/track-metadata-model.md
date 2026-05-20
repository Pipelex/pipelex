# Track — Error Metadata Model

## What this track is

The contract for **what every exception carries** so it can be rendered identically to humans, agents, and Temporal: `error_type`, `message`, `error_category` (TRANSIENT / CONFIGURATION / CONTENT / CAPACITY / UNKNOWN), `error_domain` (input / config / runtime), `user_action`, `retryable`, optional `model`, `provider`, and `provider_metadata`. The metadata lives on the exception class itself so there is a single source of truth.

The model is **landed for inference errors and the major pipeline/interpreter/service exceptions** — they self-describe via class-level attributes consumed through `to_error_report()`. The remaining work is closing the long tail: a handful of `CogtError` subclasses still carry no class-level `error_category`, and several `PipelexError` subclasses still depend on the fallback dicts in `agent_output.py` rather than carrying their own `error_domain` / `user_action`.

## Current state

### `ErrorReport` — the serialization schema

`ErrorReport` (`pipelex/base_exceptions.py`) is a frozen pydantic dataclass with `extra="forbid"`:

```
ErrorReport
  error_type:        str
  message:           str
  error_category:    str | None
  error_domain:      str | None
  retryable:         bool | None
  user_action:       UserAction | None
  model:             str | None
  provider:          str | None
  provider_metadata: ProviderErrorMetadata | None
```

`to_dict()` drops `None` fields. `http_status` maps the report to an HTTP status for downstream API adapters (see [track-cli-delivery.md](track-cli-delivery.md)).

`PipelexError.to_error_report()` returns `error_type`, `message`, and the class-level `error_domain`. `CogtError.to_error_report()` overrides it to add `error_category`, `retryable` (derived from category via `InferenceErrorCategory.is_retryable`), `user_action`, `provider_metadata`, and reads `model_handle` / `backend_name` from the instance when present. `to_error_report()` also enriches from the `__cause__` chain, so a wrapper exception surfaces the inference metadata of the underlying `CogtError`.

### Inference categories

`InferenceErrorCategory` (`pipelex/cogt/exceptions.py`) is a `StrEnum` with values `TRANSIENT`, `CONFIGURATION`, `CONTENT`, `CAPACITY`, `UNKNOWN` and an `is_retryable` property — `True` only for `TRANSIENT`. Implemented with `match/case` per the project's enum style.

### Error domains

`ErrorDomain` (`StrEnum`) has values `INPUT`, `CONFIG`, `RUNTIME`. `PipelexError` declares an optional class-level `error_domain: ErrorDomain | None`. Class-level domains are set on:

- `PipelexSetupError`, `PipelexConfigError` (`pipelex/base_exceptions.py`) → `CONFIG`.
- `PipeExecutionError` (`pipelex/pipeline/exceptions.py`) → `RUNTIME`; `PipelineExecutionError` injects `RUNTIME` + a `user_action` in its `to_error_report()` override.
- `ValidateBundleError` (`pipelex/pipeline/validate_bundle.py`) → `INPUT` + a `user_action`.
- `PipelexInterpreterError` (`pipelex/core/interpreter/exceptions.py`) → `INPUT`.
- `PipelexServiceError` and its subclasses (`pipelex/system/pipelex_service/exceptions.py`) → `CONFIG`.

### Inference class-level defaults

Many `CogtError` subclasses declare `error_category` as a class attribute:

- Routing / backend / model-deck families default to `CONFIGURATION` (e.g. `RoutingProfileDisabledBackendError`, `InferenceBackendCredentialsError`, `LLMSettingsValidationError`, `ModelNotFoundError` and its subclasses).
- Handle-not-found family (`LLMHandleNotFoundError`, etc.), capability errors, choice errors, `LLMConfigError`, `SdkTypeError`, `InferenceBackendLibraryError` — all categorized.
- The prompt / parameter family (`LLMPromptSpecError`, `LLMPromptTemplateInputsError`, `LLMPromptParameterError`, `PromptImageFactoryError`, `PromptImageFormatError`, `PromptDocumentFactoryError`, `ImgGenPromptError`, `ImgGenParameterError`, `ImageContentError`) → `CONTENT`.

`InferenceBackendCredentialsError` also declares a class-level `user_action` — the canonical pattern.

The four "outcome" exceptions stay **intentionally** uncategorized at the class level and take their category per-instance from the worker that raised them: `LLMCompletionError`, `ImgGenGenerationError`, `ExtractJobFailureError`, `SearchJobFailureError`.

### How delivery consumes this

`agent_error()` (`pipelex/cli/agent_cli/commands/agent_output.py`) calls `cause.to_error_report()` when `cause` is a `PipelexError` and reads `user_action`, `retryable`, `error_category`, `error_domain`, `model`, `provider` from the report **first**; the string-keyed dicts (`AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, `RETRYABLE_ERROR_TYPES`) are a fallback only. The Rich handlers in `error_handlers.py` likewise build panels from `report.user_action`. The `agent_output.py` dicts are guarded by a drift-detection test (see [track-testing.md](track-testing.md)).

## Open gaps

These are the genuine remainder — the metadata model is otherwise landed.

- **A few `CogtError` subclasses still have no class-level `error_category`.** `CostRegistryError`, `ReportingManagerError`, `ExtractOutputError`, `GeneratedImageError`, `LLMAssignmentError`, and parts of the routing / model-deck family (`RoutingProfileLibraryError`, `ModelManagerError`, `ModelDeckNotFoundError`, `ModelDeckValidationError`, and similar). When raised without an instance-level override they produce an `error_category`-less report. Decide a default per class.
- **Several `PipelexError` subclasses still depend on the fallback dicts.** Types caught by the agent CLI — `PipeOperatorModelChoiceError`, `ModelDeckPresetValidatonError`, the gateway-config family, `PipelexInterpreterError`'s hint, etc. — have their `hint` (and sometimes `error_domain`) only in `AGENT_ERROR_HINTS` / `AGENT_ERROR_DOMAINS`, not as class-level `user_action` / `error_domain`. The migration moves those onto the classes; the dicts then keep only built-in / third-party types (`FileNotFoundError`, `JSONDecodeError`, `ValidationError`, …) that can't carry attributes.

## Followups

The work below closes the two gaps. Either can be tackled independently.

1. **Finish class-level `error_category` on the uncategorized `CogtError` subclasses** listed above. Leave the four outcome exceptions (`LLMCompletionError` / `ImgGenGenerationError` / `ExtractJobFailureError` / `SearchJobFailureError`) as `None` — workers set them per-instance.
2. **Migrate the remaining `PipelexError`-keyed dict entries onto the classes** as class-level `user_action` (from `AGENT_ERROR_HINTS`) and `error_domain` (from `AGENT_ERROR_DOMAINS`). Keep dict entries only for non-`PipelexError` types. The drift-detection test ([track-testing.md](track-testing.md)) already enforces that every `PipelexError` subclass is covered one way or the other.

## Related tracks

- [track-worker-classification.md](track-worker-classification.md) — where per-instance `error_category` and `user_action` are set on the four outcome exceptions.
- [track-cli-delivery.md](track-cli-delivery.md) — how the human Rich handlers and the agent JSON/markdown path consume `to_error_report()`.
- [track-testing.md](track-testing.md) — the drift-detection test that keeps the dicts and the class-level metadata in sync.
- [track-temporal-integration.md](track-temporal-integration.md) — packs `to_error_report()` into `ApplicationError.details`.
