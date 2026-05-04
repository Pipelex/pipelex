# Worker Error Handling — Phase 5: Retry Architecture

> Reference: `wip/worker-error-handling-review.md` for the full review of current state.
> Completed phases (0–3) archived in `wip/error-handling-phases-0-3-completed.md`.

---

## Definition of DONE

A phase is done when **all** of the following are true:

1. **All workers catch SDK-specific exceptions** and wrap them in domain exceptions with `from exc`, model descriptor in message, and error category assigned
2. **`make agent-check` passes** (pyright, mypy, ruff)
3. **`make agent-test` passes** (full test suite green)
4. **New unit tests exist** for each changed error path — tests verify:
   - The correct custom exception type is raised
   - The error category is set correctly
   - The error message includes model descriptor
   - The `from exc` chain is preserved
   - The `to_error_report()` output matches the expected JSON schema
5. **CLI `--format json` error output** is tested with snapshot tests for representative error types
6. **Temporal compatibility verified**: `TemporalError.from_message_exception()` correctly extracts error category and maps to `non_retryable` based on category, tested with unit tests
7. **Agent CLI** `agent_error()` updated to use structured fields from exceptions rather than lookup dicts, tested

---

## Phase 5: Retry Architecture

> Move retry responsibility from workers to PipeRouter — the dispatch layer that sits between
> pipeline orchestration and pipe execution. Workers classify errors, PipeRouter retries.
>
> **Design principle — three retry layers, each with a distinct role:**
>
> | Layer | What | Retries on | Controlled by |
> |-------|------|-----------|---------------|
> | SDK transport | Connection resets, DNS, 503 | Built into OpenAI/Anthropic/Google SDKs | SDK defaults |
> | **PipeRouter (new)** | **TRANSIENT CogtErrors after SDK retries exhausted** | **Rate limits, timeouts, brief outages** | **`pipelex.toml` config** |
> | Temporal (future) | Longer failures, workflow-level retry | Service outages, cascading errors | Temporal retry policy |
>
> The PipeRouter retry is complementary to Temporal: it handles fast transients (seconds),
> Temporal handles longer failures (minutes). Without Temporal, PipeRouter retry is the only
> application-level retry — Pipelex must remain usable and resilient standalone.
>
> **Where in the code:** `PipeRouterProtocol.run()` in `pipe_run/pipe_router_protocol.py:47-67`.
> Currently catches `PipeRunError` only. The new logic adds a retry loop around
> `_run_pipe_job()` that catches `CogtError` with `is_retryable=True`.

- [ ] **5.1** Remove tenacity from gateway workers
  - `gateway_extract_worker.py`: remove `_make_retryer()`, `_is_retryable_portkey_error()`,
    `_log_retry()`, tenacity imports, and the `async for attempt in self._make_retryer()` wrapper
  - `gateway_search_worker.py`: same removal
  - Remove `TenacityConfig` from `config_cogt.py` and the `tenacity_config` field from `Cogt`
  - Remove corresponding entries from `pipelex.toml` config files
  - Remove `tenacity` from project dependencies if no longer used anywhere
  - Remove `tools/misc/tenacity_utils.py` if no longer referenced
  - Verify errors still propagate with correct `InferenceErrorCategory` (existing tests should cover)

- [ ] **5.2** Audit all workers for ad-hoc retry logic
  - Confirm no worker does business-level retries outside of SDK internals
  - Instructor's `max_retries` for structured generation is acceptable (it retries on schema
    validation failure, not transport errors) — document this with a code comment
  - Document any remaining retry behavior in a code comment at the worker level

- [ ] **5.3** Add transient retry config to `PipelineExecutionConfig`
  - Add to `PipelineExecutionConfig` in `system/configuration/configs.py`:
    ```
    max_transient_retries: int          # 0 = disabled (default for backward compat)
    transient_retry_base_wait: float    # seconds, e.g. 2.0
    transient_retry_max_wait: float     # seconds, e.g. 30.0
    transient_retry_backoff_multiplier: float  # e.g. 2.0
    ```
  - Add defaults in `pipelex/pipelex.toml` (disabled: `max_transient_retries = 0`)
  - Add commented-out overrides in `.pipelex/pipelex.toml` project config (invitation to enable)
  - Config flows through existing path: `get_config().pipelex.pipeline_execution_config`
    which is already passed to `PipelexRunner` and accessible from `PipeRouterProtocol.run()`

- [ ] **5.4** Add transient retry loop to `PipeRouterProtocol.run()`
  - Modify `pipe_run/pipe_router_protocol.py` `run()` method:
    - Wrap `_run_pipe_job()` call in a retry loop
    - Catch `CogtError` where `error_category.is_retryable` is True
    - On retryable error: log attempt number + wait duration + error category, sleep with
      exponential backoff, continue loop
    - On non-retryable error (`CONFIGURATION`, `CONTENT`, `CAPACITY`): fail immediately (no retry)
    - On max retries exhausted: raise the last error as-is (preserve the cause chain)
    - On `PipeRunError` (existing handling): no change, still wraps as `PipeRouterError`
    - `_before_run()` is called once (before the loop), not on each retry
    - `_after_failing_run()` is called once (after all retries exhausted or non-retryable)
  - The retry config comes from `PipelineExecutionConfig` — need to thread it through.
    Options: add to `PipeJob`, or access via `get_config()` directly in the protocol.

- [ ] **5.5** Thread retry config to PipeRouter
  - Decide how `PipeRouterProtocol.run()` accesses `PipelineExecutionConfig`:
    - Option A: Add `execution_config` to `PipeJob` (explicit, but changes the model)
    - Option B: Access via `get_config()` in the protocol (simple, uses existing singleton)
  - Implement the chosen approach

- [ ] **5.6** Tests for Phase 5
  - Unit test: `CogtError` with `TRANSIENT` retries up to max, then raises
  - Unit test: `CogtError` with `CONFIGURATION` fails immediately (no retry)
  - Unit test: `CogtError` with `CONTENT` fails immediately
  - Unit test: `CogtError` with `CAPACITY` fails immediately
  - Unit test: `PipeRunError` (non-CogtError) is unaffected by retry logic
  - Unit test: `max_transient_retries = 0` disables retry (backward compat)
  - Unit test: retry logging includes attempt number, wait duration, error category
  - Unit test: backoff increases with each attempt
  - Verify gateway workers raise with correct category on first failure (no silent retries)
  - Existing worker error handling tests should still pass unchanged
