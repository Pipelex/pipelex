# Review note — Temporal activity error boundary follow-ups

**Surfaced during:** code review of `cda61bae` "feat: category-aware error boundary on all Temporal activities" (Followup 5 of [track-temporal-integration.md](../track-temporal-integration.md), `_tprl/TODOS.md`).

Two minor, non-blocking observations from the code review. Neither is a regression — each is a deliberate scope choice that is worth recording so a future reader does not mistake it for an oversight.

---

## 1. Integration test verifies the converted payload, not Temporal's retry behavior

Both probe workflows in `tests/integration/pipelex/temporal/test_activity_error_boundary.py` pin `RetryPolicy(maximum_attempts=1)`. That is mandatory — without it, a retryable case would loop until timeout and hang the test (see the "Retry loop hang" gotcha in the TODOS). The consequence: the test asserts what `from_app_error` *receives* (the `non_retryable` flag, the structured `ErrorReport`) but never asserts that Temporal *acts* on `non_retryable` — i.e. that a non-retryable error stops the activity retrying while a retryable one does retry.

This gap is acceptable: honoring `non_retryable` is Temporal's own retry-engine behavior, not Pipelex code, and the bridge unit tests (`test_temporal_error_bridge.py`) fully pin the flag derivation. Verifying the engine would mean testing the framework.

**Resolution:** optional — if a regression ever appears, add a probe that lets the activity retry (a retry policy with `maximum_attempts > 1` plus a short `start_to_close_timeout`) and asserts the observed attempt count differs between a `TRANSIENT` and a `CONFIGURATION` `CogtError`.

**Affected file:**

- `tests/integration/pipelex/temporal/test_activity_error_boundary.py`

---

## 2. `_error_report_from_details` identifies the report by dict shape

`TemporalError._error_report_from_details` (`pipelex/temporal/tprl/temporal_error.py`) recovers the `ErrorReport` from `ApplicationError.details` by scanning for the first entry that is a `dict` carrying both `error_type` and `message` keys. After Temporal serialization the packed `to_error_report().to_dict()` comes back as a plain mapping with no type tag, so a shape heuristic is the available signal — and the function docstring already says so.

The theoretical false positive: an unrelated `ApplicationError` that never went through this bridge but happens to carry a details dict with both keys would be misread as an error report. Risk is low in practice — `ApplicationError.details` is not otherwise populated in this codebase, and every in-scope activity now routes through `convert_pipelex_errors`.

**Resolution:** optional — if `ApplicationError.details` ever gains other structured payloads, tag the report explicitly (e.g. a `"_pipelex_error_report": true` marker key written by the bridge and checked here) instead of duck-typing on field presence.

**Affected file:**

- `pipelex/temporal/tprl/temporal_error.py`
