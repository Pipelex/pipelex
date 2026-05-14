# Track — Error Metadata Model

## What this track is

The contract for **what every exception carries** so it can be rendered identically to humans, agents, and Temporal: `error_type`, `message`, `error_category` (TRANSIENT / CONFIGURATION / CONTENT / CAPACITY), `error_domain` (input / config / runtime), `user_action`, `retryable`, optional `model` and `provider`. The goal is to push this metadata onto the exception class itself so there is a single source of truth.

Today the metadata model is **partially landed**: inference errors (`CogtError` and subclasses) self-describe via class-level attributes, but non-inference exceptions still depend on string-keyed dicts in `pipelex/cli/agent_cli/commands/agent_output.py` (`AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, `RETRYABLE_ERROR_TYPES`).

## Current state

### What every error already exposes

`ErrorReport` (`pipelex/base_exceptions.py`) is the serialization schema. It is a frozen pydantic dataclass with `extra="forbid"` and fields: `error_type`, `message`, `error_category`, `retryable`, `user_action`, `model`, `provider`. `to_dict()` drops `None` fields.

`PipelexError.to_error_report()` returns a bare report (`error_type`, `message`) for any subclass that doesn't override it.

`CogtError.to_error_report()` (`pipelex/cogt/exceptions.py`) overrides it to include `error_category`, `retryable` (derived from category via `InferenceErrorCategory.is_retryable`), `user_action`, and reads `model_handle` / `backend_name` from the instance when present.

### Inference categories

`InferenceErrorCategory` (`pipelex/cogt/exceptions.py`) is a `StrEnum` with values `TRANSIENT`, `CONFIGURATION`, `CONTENT`, `CAPACITY` and an `is_retryable` property — `True` only for `TRANSIENT`. Implemented with `match/case` per the project's enum style.

### Class-level defaults already set

Many `CogtError` subclasses now declare `error_category` as a class attribute (defaults to `CONFIGURATION` for most of them):

- Routing / backend / model-deck families: `RoutingProfileDisabledBackendError`, `InferenceBackendCredentialsError`, `LLMSettingsValidationError`, `ImgGenSettingsValidationError`, `ModelDeckValidatonError`, `ModelDeckPresetValidatonError`, `ModelNotFoundError` (and `LLMModelNotFoundError`, `ImgGenModelNotFoundError`, `ModelWaterfallError` via inheritance).
- Handle-not-found family: `LLMHandleNotFoundError`, `ImgGenHandleNotFoundError`, `ExtractHandleNotFoundError`, `SearchHandleNotFoundError`.
- Capability errors: `LLMCapabilityError`, `ExtractCapabilityError`.
- Choice errors: `ModelChoiceNotFoundError`.
- Config error: `LLMConfigError`.

`InferenceBackendCredentialsError` also declares a class-level `user_action` (`"Check that the required API key environment variable is set"`) — the canonical pattern for the rest of the metadata to follow.

### What is intentionally left dynamic

The four "outcome" exceptions are uncategorized at the class level and set their category per-instance from the worker that raised them (so the same exception type can carry TRANSIENT / CONFIGURATION / CONTENT / CAPACITY depending on the underlying SDK error):

- `LLMCompletionError`
- `ImgGenGenerationError`
- `ExtractJobFailureError`
- `SearchJobFailureError`

### What is uncategorized and unintentional

Still uncategorized at the class level (likely `CONTENT` once decided): `LLMPromptSpecError`, `LLMPromptTemplateInputsError`, `LLMPromptParameterError`, `PromptImageFactoryError`, `PromptImageFormatError`, `PromptDocumentFactoryError`, `ImgGenPromptError`, `ImgGenParameterError`.

Case-by-case: `ImageContentError`, `CostRegistryError`, `ReportingManagerError`, `SdkTypeError`, `ExtractOutputError`, `GeneratedImageError`, `LLMAssignmentError`, `InferenceBackendLibraryError`.

### How `agent_error()` consumes this today

In `pipelex/cli/agent_cli/commands/agent_output.py`, `agent_error()` does the right thing for `PipelexError` already:

- Calls `cause.to_error_report()` when `cause` is a `PipelexError`.
- Pulls `user_action`, `retryable`, `error_category`, `model`, `provider` from the report.
- Falls back to `AGENT_ERROR_HINTS.get(error_type)` for `hint` when the report has none.
- Reads `RETRYABLE_ERROR_TYPES` only when the report didn't say.
- Reads `AGENT_ERROR_DOMAINS.get(error_type)` for `error_domain` **unconditionally** — the report has no `error_domain` field yet, so the dict is the only source.

### How `error_handlers.py` consumes this today

Each Rich handler in `pipelex/cli/error_handlers.py` builds the panel from a mix of instance attributes and `report = exc.to_error_report()` (using `report.user_action` as the tip). The Phase 1 wiring landed; the eleven near-identical handler bodies are a separate concern, addressed in [track-cli-delivery.md](track-cli-delivery.md).

## Open gaps

- **No `error_domain` on `PipelexError`.** `ErrorReport` has no `error_domain` field; `to_error_report()` doesn't carry it; `agent_error()` reads it only from the dict. As long as `error_domain` lives only in the dict, every new `PipelexError` subclass risks shipping without an entry.
- **`user_action` for non-inference exceptions lives only in the dict.** `PipelineExecutionError`, `PipeExecutionError`, `ValidateBundleError`, `PipelexInterpreterError`, `PipelexSetupError`, `PipelexConfigError`, and the `PipelexService` family all return a bare `ErrorReport`. Hints come from `AGENT_ERROR_HINTS`.
- **Some `CogtError` subclasses still have `error_category = None`.** Listed above. When raised without an instance-level override they produce empty reports.
- **Dict drift.** `AGENT_ERROR_HINTS`, `AGENT_ERROR_DOMAINS`, and `RETRYABLE_ERROR_TYPES` are string-keyed by class name. Renaming an exception silently breaks the lookup; adding a new exception silently leaves agents without a hint or domain.

## Followups

The work below closes the gap. It can be tackled in any order — there are no hard ordering constraints.

1. **Add `error_domain` to `PipelexError` and `ErrorReport`.** Optional class-level attribute (values: `"input"`, `"config"`, `"runtime"`). Update `PipelexError.to_error_report()` to include it. Modify `pipelex/base_exceptions.py`.
2. **Set class-level `error_domain` and `user_action` on key non-`CogtError` exceptions.** Targets and proposed values:
   - `PipelineExecutionError` (`pipelex/pipeline/exceptions.py`): domain=`"runtime"`, user_action=`"Check pipe_stack to identify which pipe failed"`.
   - `PipeExecutionError` (`pipelex/pipeline/exceptions.py`): domain=`"runtime"`.
   - `ValidateBundleError` (`pipelex/pipeline/validate_bundle.py`): domain=`"input"`, user_action=`"Check the validation_errors array for specific issues"`.
   - `PipelexInterpreterError` (`pipelex/core/interpreter/exceptions.py`): domain=`"input"`.
   - `PipelexSetupError`, `PipelexConfigError` (`pipelex/base_exceptions.py`): domain=`"config"`.
   - Service errors (`pipelex/system/pipelex_service/exceptions.py`): domain=`"config"`.
3. **Set defaults on uncategorized `CogtError` subclasses.** `LLMPromptSpecError`, `LLMPromptTemplateInputsError`, `LLMPromptParameterError`, `PromptImageFactoryError`, `PromptImageFormatError`, `PromptDocumentFactoryError`, `ImgGenPromptError`, `ImgGenParameterError` → `CONTENT`. Decide case-by-case for `ImageContentError`, `CostRegistryError`, `ReportingManagerError`, `SdkTypeError`, `ExtractOutputError`, `GeneratedImageError`, `LLMAssignmentError`, `InferenceBackendLibraryError`. Leave `LLMCompletionError` / `ImgGenGenerationError` / `ExtractJobFailureError` / `SearchJobFailureError` as None — workers set them per-instance.
4. **Migrate `AGENT_ERROR_HINTS` entries for `PipelexError` types onto the classes as `user_action`.** Keep dict entries only for built-in / non-`PipelexError` types (`FileNotFoundError`, `JSONDecodeError`, `ValidationError`, etc.) since attributes can't be added to those.
5. **Migrate `AGENT_ERROR_DOMAINS` entries for `PipelexError` types onto the classes as `error_domain`.** Same exception as above — built-ins stay in the dict.
6. **`agent_error()` reads class metadata first, dict as fallback only.** The `report.user_action` and `report.error_domain` (new) become the primary source; the dicts are touched only for non-`PipelexError` types.

The drift-detection unit test that guards the dicts lives in [track-testing.md](track-testing.md).

## Related tracks

- [track-worker-classification.md](track-worker-classification.md) — where per-instance `error_category` and `user_action` are set on `LLMCompletionError` / `ImgGenGenerationError` / `ExtractJobFailureError` / `SearchJobFailureError`.
- [track-cli-delivery.md](track-cli-delivery.md) — how the human Rich handlers and the agent JSON path consume `to_error_report()`.
- [track-testing.md](track-testing.md) — drift-detection test that ensures every `PipelexError` either has class-level metadata or appears in the fallback dicts.
- [track-temporal-integration.md](track-temporal-integration.md) — packing `to_error_report()` into `ApplicationError.details`.
