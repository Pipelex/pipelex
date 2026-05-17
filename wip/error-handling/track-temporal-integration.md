# Track — Temporal Integration

## What this track is

How Pipelex errors cross the Temporal boundary: activities raise Pipelex exceptions, the bridge converts them to `TemporalError(ApplicationError)`, and Temporal's retry policy uses the error to decide whether to retry. Temporal's retry decision flows from the same `InferenceErrorCategory.is_retryable` signal that classification produces — not from a static class-name list.

This is landed end-to-end: the bridge is category-aware, the full `ErrorReport` travels in `ApplicationError.details`, and every in-scope activity routes through the conversion decorator.

## Current state

### TemporalError

`pipelex/temporal/tprl/temporal_error.py` defines `TemporalError(ApplicationError)`. Two things travel with the error across the activity → workflow boundary:

- **`non_retryable`** — for a `CogtError` carrying an `InferenceErrorCategory`, the flag is derived from `category.is_retryable` (`non_retryable = not is_retryable`). For category-less exceptions the bridge falls back to the configured `non_retryable_error_types` class-name list — the union of the worker, per-queue, and per-handle levels (`all_non_retryable_error_types` in `pipelex/temporal/config_temporal.py`).
- **`error_report`** — `exc.to_error_report().to_dict()` is packed into `ApplicationError.details`, so workflow code keeps `error_category`, `error_domain`, `user_action`, `model`, and `provider` rather than just the message string.

`from_message_exception` converts a `PipelexError` raised inside an activity; `from_app_error` re-wraps an `ApplicationError` observed in workflow code, recovering the `non_retryable` flag and the details payload the activity-side bridge set. `_log_critical` / `_log_error` select `activity_log` vs `workflow_log` via `activity.in_activity()`, since the two entry points run on opposite sides of the boundary (`workflow.logger` raises outside a workflow event loop).

### Activity error boundary

A shared decorator `convert_pipelex_errors` (`pipelex/temporal/tprl/activity_error_boundary.py`) is applied beneath `@activity.defn` on every in-scope activity:

```python
@activity.defn
@convert_pipelex_errors
async def act_llm_gen_text(llm_assignment: LLMAssignment) -> str:
    return await llm_gen_text(llm_assignment=llm_assignment)
```

The decorator catches `PipelexError` only (never the generic `Exception`) and re-raises `TemporalError.from_message_exception(exc=exc) from exc`. Wired on `act_llm_gen_text` / `act_llm_gen_object` / `act_llm_gen_object_list`, `act_img_gen_images`, `act_extract_gen_extract_pages`, `act_jinja2_gen_text`, `act_render_page_views`, `act_deliver`, `act_flush_trace_events`. Deliberately **not** wired on `act_assemble_graph` — it is best-effort observability that swallows every failure and degrades to `None`, so no error crosses its boundary.

### Retry policy config

`pipelex/temporal/config_temporal.py` defines `RetryPolicyConfig` with `non_retryable_error_types: list[str]` (baseline list) and `non_retryable_error_types_extra: list[str]` (additive overrides per queue / per handle). `RetryPolicyConfig.make_retry_policy(merged_non_retryable_types)` builds the Temporal `RetryPolicy`. The `all_non_retryable_error_types` helper unions the three layers for the fallback retry decision (category-less exceptions) and the matching log severity. The composition is **additive** across worker → queue → handle layers.

The class-name list is documented as a **fallback only**: a `CogtError` carrying an `InferenceErrorCategory` is decided by category; the list applies to non-`CogtError` `PipelexError` subclasses, a `CogtError` raised without a category, and per-queue overrides.

## Open gaps

None. Two optional refinements from the activity-boundary code review are recorded in [deferred-items/temporal-activity-boundary-review-followups.md](deferred-items/temporal-activity-boundary-review-followups.md): the integration test verifies the converted payload rather than Temporal's retry-engine behavior, and `_error_report_from_details` identifies the report by dict shape. Both are deliberate scope choices, optional to revisit.

## Related tracks

- [track-retry-and-resilience.md](track-retry-and-resilience.md) — this is Tier 2; direct execution has no pipeline-level retry tier below it.
- [track-worker-classification.md](track-worker-classification.md) — every inference worker classifies before this bridge is meaningful.
- [track-metadata-model.md](track-metadata-model.md) — the `error_category` / `user_action` / `model` / `provider` on `to_error_report()` are what the details payload carries.
- [track-cli-delivery.md](track-cli-delivery.md) — once `ApplicationError.details` carries the full report, the Temporal-side CLI / Web UI can render the same structured information as the agent JSON path.
