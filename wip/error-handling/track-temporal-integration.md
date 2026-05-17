# Track — Temporal Integration

## What this track is

How Pipelex errors cross the Temporal boundary: activities raise Pipelex exceptions, the bridge converts them to `TemporalError(ApplicationError)`, and Temporal's retry policy uses the error to decide whether to retry. Temporal's retry decision flows from the same `InferenceErrorCategory.is_retryable` signal that classification produces — not from a static class-name list.

The bridge is landed end-to-end: the conversion is category-aware, the full `ErrorReport` travels in `ApplicationError.details`, every in-scope activity routes through the conversion decorator, and the symmetric workflow → submitter recovery reads that report back out of `details` once the failure returns to the process that submitted the workflow. See "Submitter-side report recovery (landed)" below.

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

## Submitter-side report recovery (landed)

The bridge moves the `ErrorReport` activity → workflow, and `from_app_error` recovers it for workflow code. The symmetric workflow → submitter recovery — reading the report back out of `ApplicationError.details` once the failure returns to the process that submitted the workflow — is now landed:

- `recover_error_report` (`pipelex/temporal/tprl/temporal_error.py`) walks the failure's `__cause__` chain for an `ApplicationError`, pulls the details-packed report dict via the now-public `error_report_dict_from_details`, and rebuilds an `ErrorReport` through `ErrorReport.from_dict` (the strict inverse of `to_dict`, added in `pipelex/base_exceptions.py`). It tolerates worker/submitter version skew — unknown keys are dropped, a dict that still fails validation yields `None` — so the error path never crashes.
- `WorkflowExecutor.execute_workflow` (`pipelex/temporal/tprl/workflow_caller.py`) splits the combined handler into a dedicated `except WorkflowFailureError` clause that recovers the report and a sibling `except (WorkflowAlreadyStartedError, RPCError)` clause that stays generic. The recovered report is carried on `WorkflowExecutionError(error_report=...)`, and the original failure message replaces the generic `"Failed to execute workflow ..."`.
- `WorkflowExecutionError.to_error_report()` returns the recovered report when present; with no report it falls through to base `__cause__`-chain enrichment. `PipelineExecutionError` then inherits the classification natively, since `WorkflowExecutionError` is a `PipelexError`.

Net effect: a pipe failure on a Temporal worker now reaches every `to_error_report()` consumer — agent CLI JSON/markdown, the Rich human CLI, the `ErrorReport.http_status` mapping for HTTP adapters — with the same `error_category` / `retryable` / `model` / `provider` / `user_action` classification as the identical failure run locally.

**Design:** `WorkflowExecutionError` holds the `ErrorReport` as an optional attribute and overrides `to_error_report()` — option (a). This keeps `raise WorkflowExecutionError(msg) from exc` so the Temporal `WorkflowFailureError` stays in the traceback for free. Rejected option (b) (a `RemotePipelexError` carrier in the `__cause__` chain) for forcing a new public exception class plus manual `__cause__` wiring.

### Child-workflow boundary recovery (landed)

The child-workflow boundary (`execute_child_workflow` / `start_child_workflow` in `pipelex/temporal/tprl/workflow_caller.py`) now applies the same recovery. `ChildWorkflowError` exposes the deserialized failure via `.cause`; when that cause is an `ApplicationError`, the handler runs `recover_error_report(exc.cause)` and, on a recovered report, raises `WorkflowExecutionError(error_report.message, error_report=...)` — mirroring `execute_workflow`. A cause with no report payload, malformed details, or a non-`ApplicationError` cause all fall back to the prior generic error. These wrappers are not on Pipelex's traced execution paths (in-workflow child spawns call `workflow.execute_child_workflow` directly to stay replay-deterministic), so this closes a latent gap on the public surface.

### Deferred review followups

Two optional refinements from the activity-boundary code review are recorded in [deferred-items/temporal-activity-boundary-review-followups.md](deferred-items/temporal-activity-boundary-review-followups.md): the integration test verifies the converted payload rather than Temporal's retry-engine behavior, and `error_report_dict_from_details` identifies the report by dict shape. Both are deliberate scope choices, optional to revisit.

## Related tracks

- [track-retry-and-resilience.md](track-retry-and-resilience.md) — this is Tier 2; direct execution has no pipeline-level retry tier below it.
- [track-worker-classification.md](track-worker-classification.md) — every inference worker classifies before this bridge is meaningful.
- [track-metadata-model.md](track-metadata-model.md) — the `error_category` / `user_action` / `model` / `provider` on `to_error_report()` are what the details payload carries.
- [track-cli-delivery.md](track-cli-delivery.md) — the delivery surfaces consume `to_error_report()`; the submitter-side gap above is why that data source is degraded for a Temporal-run pipe.
