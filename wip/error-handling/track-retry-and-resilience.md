# Track — Retry and Resilience

## What this track is

How Pipelex recovers from **transient** failures (rate limits, brief network outages, 5xx server errors) without operator intervention, and how that retry responsibility is split across layers.

Today retry lives **inside two gateway workers** via `tenacity`. The `PipeRouter` — the dispatch layer that sits between pipeline orchestration and pipe execution — has no retry loop. The goal is to invert that: workers classify errors (already true after worker classification landed), and `PipeRouter` retries based on `InferenceErrorCategory.is_retryable`.

## Design principle — three retry layers

| Layer | What | Retries on | Controlled by |
|---|---|---|---|
| SDK transport | Connection resets, DNS failures, 503 | Built into OpenAI / Anthropic / Google SDKs | SDK defaults |
| **PipeRouter (not yet)** | **`InferenceErrorCategory.TRANSIENT` after SDK retries exhausted** | **Rate limits, timeouts, brief outages** | **`pipelex.toml` config (not yet)** |
| Temporal (future) | Longer failures, workflow-level retry | Service outages, cascading errors | Temporal retry policy |

`PipeRouter` retry is complementary to Temporal: it handles fast transients (seconds); Temporal handles longer failures (minutes). Without Temporal, `PipeRouter` retry is the only application-level retry — Pipelex must remain usable and resilient standalone.

## Current state

### Gateway workers retry with tenacity

`pipelex/plugins/gateway/gateway_extract_worker.py` and `pipelex/plugins/gateway/gateway_search_worker.py` each build a tenacity `AsyncRetrying` from `get_config().cogt.tenacity_config` (defined in `pipelex/cogt/config_cogt.py` as `TenacityConfig`). The retry predicate `_is_retryable_portkey_error` discriminates between retryable and non-retryable Portkey errors. The retry wrapper wraps the SDK call in `async for attempt in self._make_retryer():`.

### Other tenacity usage that is not ad-hoc business retry

- `pipelex/plugins/fal/fal_poller.py` uses tenacity for polling FAL job status — this is polling behavior, not retry on error, and is **not** in scope for the PipeRouter-level retry rewrite. It stays as-is.
- `instructor`'s internal `max_retries` for structured generation retries on schema-validation failure, not on transport errors. This is acceptable and stays as-is; document with a code comment if not already.

### PipeRouter has no retry loop

`PipeRouterProtocol.run()` (`pipelex/pipe_run/pipe_router_protocol.py`) currently:

```python
async def run(self, pipe_job: PipeJob) -> PipeOutput:
    await self._before_run(pipe_job)
    try:
        pipe_output = await self._run_pipe_job(pipe_job)
    except PipeRunError as exc:
        await self._after_failing_run(pipe_job, exc)
        raise PipeRouterError(
            message=exc.message,
            run_mode=pipe_job.pipe_run_params.run_mode,
            pipe_code=pipe_job.pipe.code,
            output_name=pipe_job.output_name,
            pipe_stack=pipe_job.pipe_run_params.pipe_stack,
        ) from exc
    await self._after_successful_run(pipe_job, pipe_output)
    return pipe_output
```

It only catches `PipeRunError`. There is no retry loop around `_run_pipe_job()` and no consumption of `InferenceErrorCategory.is_retryable`.

### Config

`PipelineExecutionConfig` (`pipelex/system/configuration/configs.py`) carries `is_normalize_data_urls_to_storage`, `is_mock_inputs`, `is_generate_graph`, `graph_config`. **No retry settings exist yet.** The config flows through `get_config().pipelex.pipeline_execution_config` and is already accessible from `PipeRouterProtocol.run()` via the singleton.

## Open gaps

- **PipeRouter does not retry on `TRANSIENT`.** A rate-limit or timeout from a worker propagates immediately out of the router; only the two gateway workers retry locally, and only on Portkey-specific errors.
- **Retry logic is duplicated and scoped to two workers.** `_make_retryer`, `_is_retryable_portkey_error`, `_log_retry` exist in each gateway worker; the dispatch layer remains retry-blind.
- **No standardized config for application-level retry.** `TenacityConfig` exists only for the gateway workers; there is no top-level `max_transient_retries` / backoff settings on `PipelineExecutionConfig`.

## Followups

These can be done in either order, but inverting (router-first) means the gateway workers stop retrying earlier than they do today during a brief overlap. The order below assumes router-first with retry disabled by default for backward compatibility, then removing the gateway worker tenacity in a second step.

### 1. Add retry config to `PipelineExecutionConfig`

In `pipelex/system/configuration/configs.py` add:

```
max_transient_retries: int                  # 0 = disabled (default)
transient_retry_base_wait: float            # seconds, e.g. 2.0
transient_retry_max_wait: float             # seconds, e.g. 30.0
transient_retry_backoff_multiplier: float   # e.g. 2.0
```

Per project rules, do not set defaults in the class body. Put the defaults in `pipelex/pipelex.toml` with `max_transient_retries = 0` so behavior is unchanged for existing installs. Add commented-out overrides in `.pipelex/pipelex.toml` as an invitation to enable.

### 2. Add retry loop to `PipeRouterProtocol.run()`

Modify `pipelex/pipe_run/pipe_router_protocol.py`:

- Wrap the `_run_pipe_job()` call in a retry loop.
- Catch `CogtError` where `error_category is not None and error_category.is_retryable` is `True`.
- On retryable error: log attempt number + wait duration + error category, sleep with exponential backoff, continue loop.
- On non-retryable error (`CONFIGURATION`, `CONTENT`, `CAPACITY`): fail immediately (no retry).
- On max retries exhausted: re-raise the last error as-is (preserve the cause chain).
- On `PipeRunError` (existing path): unchanged — still wraps as `PipeRouterError`.
- `_before_run()` is called once (before the loop), not on each retry.
- `_after_failing_run()` is called once (after all retries exhausted or non-retryable).

### 3. Thread the retry config to the router

Two options:

- **Option A** — add `execution_config` to `PipeJob`. Explicit, but changes the model.
- **Option B** — access via `get_config()` directly inside the protocol. Simple, uses the existing singleton; consistent with how `pipeline_execution_config` is already accessed elsewhere.

Option B is the lower-friction choice unless `PipeJob` already has a natural slot for it.

### 4. Remove `tenacity` from gateway workers

After the router-level retry is in place and verified:

- Remove `_make_retryer()`, `_is_retryable_portkey_error()`, `_log_retry()`, tenacity imports, and the `async for attempt in self._make_retryer():` wrapper from `pipelex/plugins/gateway/gateway_extract_worker.py` and `pipelex/plugins/gateway/gateway_search_worker.py`.
- Remove `TenacityConfig` from `pipelex/cogt/config_cogt.py` and the `tenacity_config` field from `Cogt`.
- Remove corresponding entries from `pipelex/pipelex.toml`.
- Remove `tenacity` from project dependencies if no longer used (note that `pipelex/plugins/fal/fal_poller.py` still uses it for polling — confirm before removing the dependency).
- Remove `pipelex/tools/misc/tenacity_utils.py` if no longer referenced anywhere (FAL still references `log_retry` from it).
- Verify errors still propagate with the correct `InferenceErrorCategory` (existing classification tests should cover this).

### 5. Audit workers for ad-hoc retry

Confirm no worker does business-level retries outside of SDK internals. `instructor`'s `max_retries` for schema-validation retries on the structured-gen path is acceptable — add a one-line code comment at the call site documenting why.

### 6. Tests

- `CogtError` with `TRANSIENT` retries up to max, then raises.
- `CogtError` with `CONFIGURATION` / `CONTENT` / `CAPACITY` fails immediately.
- `PipeRunError` (non-`CogtError`) is unaffected by retry logic.
- `max_transient_retries = 0` disables retry (backward compatibility).
- Retry log includes attempt number, wait duration, error category.
- Backoff increases with each attempt.
- Gateway workers raise with correct category on first failure (no silent retries).
- Existing worker error-handling tests still pass unchanged.

## Related tracks

- [track-worker-classification.md](track-worker-classification.md) — workers must classify before the router can act on the signal. The instructor unwrap gap means structured-gen TRANSIENT errors are currently mis-categorized as `CONTENT` and would not retry; fix that first or in parallel.
- [track-temporal-integration.md](track-temporal-integration.md) — Temporal's retry policy is the third layer; the router-level retry feeds into it (Temporal sees a non-retryable error only after the router has exhausted its retries, or for non-`TRANSIENT` categories).
- [track-metadata-model.md](track-metadata-model.md) — `is_retryable` is the property of `InferenceErrorCategory` that drives the router decision.
