# TODO — Wire `from_message_exception` into the Temporal activity boundary

> **Status:** Not started — minimal stub. **Design the full plan in a fresh session** (see "How to expand" below).
> **Source:** Followup 5 of [track-temporal-integration.md](track-temporal-integration.md) — read that section first; it is the authoritative description.

---

## The gap (one paragraph)

Phase 6 (commit `f5176d39`) built `TemporalError.from_message_exception()` — category-aware retry decisions (`InferenceErrorCategory.is_retryable`) plus packing `to_error_report()` into `ApplicationError.details`. **No activity calls it.** The activity functions raise raw `CogtError` / `PipelexError`, Temporal's default failure converter auto-wraps them, and that converter neither packs our `ErrorReport` into `details` nor sets `non_retryable`. Net effect in production: `from_app_error` always hits its `error_report is None` fallback branch, and the category-aware retry decision never runs. Phase 6's logic is built but dead.

This is the Temporal-side twin of the non-Temporal `PipeRouter` retry-bypass fixed in PR #903.

## Pointers

- **Bridge methods:** `pipelex/temporal/tprl/temporal_error.py` — `from_message_exception` (~line 109), `from_app_error` (~line 82).
- **Activity entry points to convert (~8):**
  - `pipelex/temporal/tprl_content_generation/act_{extract,img_gen,jinja2,llm}_generate.py`, `act_render_page_views.py`
  - `pipelex/temporal/tprl_pipe/act_{assemble_graph,deliver,flush_trace_events}.py`
- **Existing unit test (bridge in isolation):** `tests/unit/pipelex/temporal/test_temporal_error_bridge.py` — proves a self-consistent round-trip but never crosses a real activity → workflow boundary.
- **Retry config:** `pipelex/temporal/config_temporal.py` — `RetryPolicyConfig.non_retryable_error_types` (the name-based fallback for exceptions with no category).

## Shape of the change (from the track doc)

Each activity entry point converts at its boundary:

```python
@activity.defn
async def act_llm_gen_text(llm_assignment: LLMAssignment) -> str:
    try:
        return await llm_gen_text(llm_assignment=llm_assignment)
    except PipelexError as exc:
        raise TemporalError.from_message_exception(exc=exc) from exc
```

Plus an integration test that raises a real `CogtError` from an activity and asserts what `from_app_error` receives on the workflow side.

## How to expand (do this in the new session)

1. Re-read Followup 5 in [track-temporal-integration.md](track-temporal-integration.md) in full, and the Phase 6 archive notes in [archive-error-handling-2.md](archive-error-handling-2.md).
2. Verify each activity's current `except`/raise shape — confirm whether a per-activity `try/except PipelexError` is right, or whether a shared decorator / helper is cleaner (the 8 activities may share a wrapper). Decide and record the decision.
3. Decide where the conversion belongs relative to existing error handling in each activity (don't double-wrap; respect the project's `except Exception` ban).
4. Write the plan as RED → GREEN → REFACTOR. RED = an integration test that crosses a real activity → workflow boundary and asserts `from_app_error` receives a populated `ErrorReport` + correct `non_retryable`. Confirm it fails today (fallback branch).
5. Settle the open design question: per-activity `try/except` vs. a shared `@activity.defn` wrapper. List both in the plan; recommend one.
6. Run `make agent-check` after each step, `make agent-test` before wrapping up. Temporal integration tests: see the `--temporal-server` option notes in `_tprl/CLAUDE.md`.

## Out of scope

- Changing the bridge methods themselves (Phase 6 landed them; only the wiring is missing).
- The non-Temporal `PipeRouter` retry path — that is PR #903.
