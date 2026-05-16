# Track — Temporal Integration

## What this track is

How Pipelex errors cross the Temporal boundary: activities raise Pipelex exceptions, the bridge converts them to `TemporalError(ApplicationError)`, and Temporal's retry policy uses the error type to decide whether to retry. The goal is to make Temporal's retry decision flow from the same `InferenceErrorCategory.is_retryable` signal that drives the in-process `PipeRouter` retry, instead of from a static class-name list.

This work belongs on the Temporal integration branch and is currently **open**.

## Current state

### TemporalError

`pipelex/temporal/tprl/temporal_error.py` defines `TemporalError(ApplicationError)`:

```python
class TemporalError(ApplicationError):
    def __init__(self, message: str, error_type: str | None):
        super().__init__(message=message, type=error_type)

    @classmethod
    def from_app_error(cls, exc: ApplicationError) -> Self:
        ...

    @classmethod
    def from_message_exception(cls, exc: PipelexError) -> Self:
        message = exc.message
        error_type = exc.__class__.__name__
        temporal_config = get_config().temporal
        all_non_retryable = temporal_config.worker_config.all_non_retryable_error_types(
            queue_options_by_queue=temporal_config.queue_options,
        )
        if error_type in all_non_retryable:
            workflow_log.critical(f"Non retryable error from PipelexError[{error_type}]: {message}")
        else:
            workflow_log.error(f"Retryable error from PipelexError[{error_type}]: {message}")
        return cls(message=message, error_type=error_type)
```

Both `from_app_error` and `from_message_exception` look up the union of `non_retryable_error_types` declared at the worker, per-queue, and per-handle levels (`all_non_retryable_error_types` in `pipelex/temporal/config_temporal.py`). The lookup drives log severity but **does not** consult `InferenceErrorCategory.is_retryable` and **does not** include `to_error_report()` data in `ApplicationError.details`.

### Retry policy config

`pipelex/temporal/config_temporal.py` defines a `RetryPolicyConfig` with `non_retryable_error_types: list[str]` (baseline list) and `non_retryable_error_types_extra: list[str]` (additive overrides per queue / per handle). `RetryPolicyConfig.make_retry_policy(merged_non_retryable_types)` builds the Temporal `RetryPolicy`. The `all_non_retryable_error_types` helper unions the three layers for log-severity classification.

The composition is **additive** across worker → queue → handle layers (see comments around `pipelex/temporal/config_temporal.py:502`).

## Open gaps

- **Retry decision is name-based, not category-based.** Today the Temporal retry policy decides retryability from a hard-coded list of class names. A new TRANSIENT error type (e.g. a new `LLMCompletionError` instance that happens to be transient) is not automatically retried unless someone remembers to add a name to the config. The signal already exists on the exception (`error_category.is_retryable`) but the bridge does not look at it.
- **`ApplicationError.details` is empty.** `to_error_report()` already produces a structured dict (`error_type`, `message`, `error_category`, `retryable`, `user_action`, `model`, `provider`). The bridge does not pack this into `ApplicationError.details`, so workflow code observing the error has only `message` and `type` to work with — losing `user_action`, `model`, `provider`, and the structured category.
- **`non_retryable_error_types` role is unclear.** With category-aware decisions it should be a fallback for exceptions that don't carry a category (i.e. non-`CogtError` `PipelexError` subclasses, until [track-metadata-model.md](track-metadata-model.md) extends `error_category`-or-equivalent to them). The config docs should say this explicitly.

## Followups

> **Status:** Followups 1–4 landed in Phase 6 (commit `f5176d39`). Followup 5 **landed** on branch `fix/temporal-activity-error-boundary` — see below. The wiring that makes 1–4 actually run in production is now in place.

### 1. Use `is_retryable` in `from_message_exception`

In `pipelex/temporal/tprl/temporal_error.py`, when `exc` is a `CogtError` and `exc.error_category is not None`, derive retryability from `exc.error_category.is_retryable`. When category is `None`, fall back to the existing `non_retryable_error_types` lookup.

Note: Temporal's `ApplicationError(non_retryable=True)` flag is the inverse of `is_retryable`. The bridge sets `non_retryable=not is_retryable` on the underlying `ApplicationError`.

### 2. Pack `to_error_report()` into `ApplicationError.details`

`ApplicationError` accepts a `details` payload. Serialize `exc.to_error_report().to_dict()` and pass it as a details argument. Workflow code that receives an `ApplicationError` can then read `error_category`, `user_action`, `model`, `provider` directly without parsing the message string.

Round-trip: `from_app_error` should also extract the details payload if present and surface it back as fields on the resulting `TemporalError` so the original structured data survives the activity → workflow boundary.

### 3. Document `non_retryable_error_types` as a fallback

Update the docstring of `RetryPolicyConfig.non_retryable_error_types` and `non_retryable_error_types_extra` in `pipelex/temporal/config_temporal.py` to state explicitly:

- For exceptions that carry an `InferenceErrorCategory`, retryability is decided by category, not by name.
- The class-name list applies to:
  - Non-`CogtError` `PipelexError` subclasses (until the metadata model lands across the hierarchy).
  - Any `CogtError` that happens to be raised without a category set.
  - Special cases that need to override the category default (e.g. forcing retry on an otherwise-non-retryable type for a specific queue).

### 4. Tests

- `from_message_exception` on a `CogtError` with `TRANSIENT` produces an `ApplicationError` with `non_retryable=False`.
- `from_message_exception` on a `CogtError` with `CONFIGURATION` / `CONTENT` / `CAPACITY` produces `non_retryable=True`.
- `from_message_exception` on a non-`CogtError` `PipelexError` falls back to the name list.
- `from_message_exception` on a `CogtError` with `error_category=None` falls back to the name list (no NPE).
- `ApplicationError.details` round-trips through Temporal's serialization with all `ErrorReport` fields intact.
- Log severity (critical / error) matches the retry decision in both paths.

### 5. Wire `from_message_exception` into the activity boundary (LANDED)

Phase 6 implemented `from_message_exception` (category-aware retry decision + `ErrorReport` details packing) but no activity called it, so `from_app_error` always landed in its `error_report is None` fallback branch and the category-aware retry decision never ran.

**Landed on branch `fix/temporal-activity-error-boundary`.** Rather than a per-activity `try/except`, a shared decorator `convert_pipelex_errors` (new module `pipelex/temporal/tprl/activity_error_boundary.py`) is applied beneath `@activity.defn` on every in-scope activity:

```python
@activity.defn
@convert_pipelex_errors
async def act_llm_gen_text(llm_assignment: LLMAssignment) -> str:
    return await llm_gen_text(llm_assignment=llm_assignment)
```

The decorator catches `PipelexError` only (never the generic `Exception`) and re-raises `TemporalError.from_message_exception(exc=exc) from exc`. Wired: `act_llm_gen_text` / `act_llm_gen_object` / `act_llm_gen_object_list`, `act_img_gen_images`, `act_extract_gen_extract_pages`, `act_jinja2_gen_text`, `act_render_page_views`, `act_deliver`, `act_flush_trace_events`. Deliberately **not** wired: `act_assemble_graph` — it is best-effort observability that swallows every failure and degrades to `None`, so no error ever crosses its boundary.

Also fixed under this followup: `TemporalError._log_critical` / `_log_error` now select `activity_log` vs `workflow_log` via `activity.in_activity()`, because `workflow.logger` raises `_NotInWorkflowEventLoopError` outside a workflow event loop and `from_message_exception` runs activity-side.

Tests: an integration test (`tests/integration/pipelex/temporal/test_activity_error_boundary.py`) drives a real `CogtError` from a real activity through a real worker and asserts what `from_app_error` receives on the workflow side, over both an LLM and a non-LLM activity; a decorator unit test (`tests/unit/pipelex/temporal/test_activity_error_boundary.py`) pins the `functools.wraps` invariants and the `PipelexError`-only catch.

Two non-blocking observations from the code review of `cda61bae` are recorded in [deferred-items/temporal-activity-boundary-review-followups.md](deferred-items/temporal-activity-boundary-review-followups.md): the integration test verifies the converted payload rather than Temporal's retry behavior, and `_error_report_from_details` identifies the report by dict shape. Both are deliberate scope choices, optional to revisit.

## Prerequisites

- [track-worker-classification.md](track-worker-classification.md) — every inference worker classifies before this bridge is meaningful (done, modulo the `instructor` unwrap on OpenAI / Mistral / Google).
- [track-metadata-model.md](track-metadata-model.md) — the `error_category` / `user_action` / `model` / `provider` on `to_error_report()` are what the details payload carries; the metadata-on-classes story makes that payload uniformly populated.

## Related tracks

- [track-retry-and-resilience.md](track-retry-and-resilience.md) — the in-process `PipeRouter` retry is the layer below Temporal's retry. Both should consult `is_retryable` so the two layers agree on what counts as transient.
- [track-cli-delivery.md](track-cli-delivery.md) — once `ApplicationError.details` carries the full report, the Temporal-side CLI / Web UI can render the same structured information as the agent JSON path.
