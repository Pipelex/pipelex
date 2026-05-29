# TODOS — Retry & Resilience: remove the PipeRouter loop, make Tier 1 (transport retry) explicit

> **ARCHIVED — both workstreams landed.** Workstream 1 (remove the `PipeRouter` transient-retry loop) and Workstream 2 (make Tier 1 transport retry explicit and uniform, confine `instructor` to schema re-ask) are both in the code. This file is kept for its running notes and checkpoint history. The current-state description lives in [track-retry-and-resilience.md](../track-retry-and-resilience.md).

> **Type:** Implementation plan — two independent workstreams. Workstream 1 is a removal; Workstream 2 is config + factory wiring + a worker audit.
> **Source / intent:** [wip/error-handling/track-retry-and-resilience.md](wip/error-handling/track-retry-and-resilience.md) — the target-architecture doc. Where this plan and that doc differ, the doc is authoritative for *intent*; this plan is authoritative for *steps*.
> **Branch:** Workstream 2 runs on `feature/Error-handling-4` (branched off `feature/Error-handling-3`, which carries the landed Workstream 1 removal). Workstream 1 shipped as PR #909 (`feature/Error-handling-3` → `feature/Error-handling-2`); commits `bd089c2a` (removal) + `22932ae2` (CHANGELOG cleanup). `feature/Error-handling-3` carries the error-metadata model and the now-removed Phase 5 retry loop's *absence*; `main` has neither.
> **Packaging:** ship as **two PRs** — Workstream 1 (removal) landed first as PR #909. Workstream 2 (Tier 1 explicit) follows as a second PR off `feature/Error-handling-4`. The two workstreams don't conflict, but separate PRs keep each review scoped to one concern.
> **Discipline:** `make agent-check` after each step; `make agent-test` before wrapping up. After deleting test files, `make cleanderived` if collection misbehaves. After config/toml changes, `make tb` (boot test — config model and toml must stay in sync).

## Status

**Workstream 1 complete and shipped** as PR #909 (`make agent-check` clean, `make agent-test` green; see the Workstream 1 checkpoint below). **Workstream 2 complete** — all of steps 2.1–2.5 landed on `feature/Error-handling-4`; `make agent-check` clean, `make agent-test` green (see the Workstream 2 checkpoints below). Ready for the second PR.

**Cold-start for Workstream 2:** read **Cold-start context** below (the tier model and what Workstream 2 is *not*), then the **Workstream 2** section in full, then **Key files** and **Risks / gotchas**. Workstream 2 is config + SDK-factory wiring + a worker audit — it makes the provider SDKs' existing transport retry an explicit, uniform, configured policy and brings the SDK-less paths up to that floor; it does **not** build a Pipelex retry layer. The critical correction the v1 plan got wrong (`instructor`'s `max_retries` retries transport errors too, not just schema validation) is in **Cold-start context** and drives step 2.3 — do not skip it.

## Cold-start context

Pipelex's resilience story is Temporal. Direct (non-Temporal) execution makes one pipeline-level attempt on top of a transport that already retries brief blips — it should stay clean and honest about that, and not reproduce Temporal's durability. The full reasoning, the tier model, and the decisions are in the architecture doc linked above. The two concrete consequences this plan executes:

- **Remove the `PipeRouter` application-level transient-retry loop (Phase 5).** It only ever runs on the direct path — it is dead code on the Temporal path, because `_run_pipe_job` there raises `WorkflowExecutionError` / `TemporalError`, which the loop's `except (CogtError, PipeRunError)` never catches. It also re-runs at the wrong granularity and carries a per-run/global config bug (the retry budget is snapshotted from global config at router construction, so a per-run `execution_config` is silently ignored). Removing it is cleaner than fixing it for a path that is deliberately not the resilient one.
- **Make "Tier 1" — transport retry — an explicit, uniform policy.** The provider SDKs already retry transient transport failures (OpenAI / Anthropic: `max_retries = 2`, retry 408 / 409 / 429 / 5xx / connection errors, honor `Retry-After`); the worker factories inherit that silently, and workers not on a retrying SDK (the raw-`httpx` `azure_rest` image-gen path; the Mistral and Google SDKs, both of which default to **no** transport retry; the FAL submit path) don't get it. The work is to make the retry posture deliberate and uniform — set `max_retries` explicitly from config, and bring the SDK-less paths up to the same floor — **not** to build a Pipelex retry layer, which would duplicate the SDK.

What stays untouched: `PipeBatch` bounded fan-out (`gather_bounded` / `max_concurrency`) — admission control, not retry. Temporal Tier 2 (activity `RetryPolicy` keyed off `InferenceErrorCategory`). The operator wrapping in `PipeLLM` / `PipeStructure` (`LLMCompletionError` → `PipeRunError`) — error-context propagation. The provider SDKs' own retry logic — Workstream 2 *configures* it, it does not replace it.

**A correction the v1 plan got wrong:** it scoped `instructor`'s `max_retries` out as "schema-validation retry, not transport." Verified false against `instructor` 1.15.1 (`instructor/core/retry.py`): passed an `int`, `instructor` retries **any** exception — transport / API errors included. The structured-output path (`PipeLLM` / `PipeStructure`) therefore already runs an application-level transport-retry loop nested on the SDK's own. Confining `instructor` to genuine schema re-ask is Workstream 2.3.

---

## Workstream 1 — Remove the PipeRouter transient-retry loop

A removal, not a TDD build. Delete in the order below, then verify. One small guard test is added at the end.

### 1.1 — Strip the retry loop from the protocol

- [x] `pipelex/pipe_run/pipe_router_protocol.py` — in `run()` (around lines 54–100), remove the `while True` retry loop, the backoff `asyncio.sleep`, the retry logging, and the `find_inference_error_category_in_chain` call. The resulting `run()`: `_before_run` → one `_run_pipe_job` call → `_after_successful_run` on success; on `except (CogtError, PipeRunError)`, call `_after_failing_run`, then wrap a `PipeRunError` into `PipeRouterError` / re-raise a raw `CogtError` as-is. **Keep that handler** — it is error propagation (pipe-stack context), not retry.
- [x] Same file — remove the `transient_retry_settings: TransientRetrySettings` attribute from `PipeRouterProtocol`.
- [x] Let `make fix-unused-imports` clean the now-unused imports (`asyncio`, `log`, `find_inference_error_category_in_chain`, `TransientRetrySettings`).
- [x] Leave `find_inference_error_category_in_chain` in `pipelex/cogt/exceptions.py` — Temporal still uses it (`temporal_error.py`). Only the router's *use* of it goes.

### 1.2 — Delete the retry plumbing

- [x] Delete `pipelex/pipe_run/transient_retry.py` (`TransientRetrySettings`).
- [x] `pipelex/pipe_run/pipe_router.py` — delete `make_transient_retry_settings()`; drop `self.transient_retry_settings` from `PipeRouter.__init__`.
- [x] `pipelex/pipe_run/dry_pipe_router.py` — drop `transient_retry_settings` from `DryPipeRouter` (around line 13) and its import.
- [x] `pipelex/temporal/tprl_pipe/temporal_pipe_router.py` — drop `transient_retry_settings` from `TemporalPipeRouter` (around line 54) and its import. This was dead code.

### 1.3 — Remove the config

- [x] `pipelex/system/configuration/configs.py` — from `PipelineExecutionConfig` (around lines 153–177) remove the transient-retry fields and the `_validate_transient_retry_timing` validator. **Keep `max_concurrency`** — it is the bounded-fan-out pillar and stays.
- [x] `pipelex/pipelex.toml` — remove the transient-retry settings (around lines 290–293).
- [x] `pipelex/kit/configs/pipelex.toml` — remove the commented-out transient-retry block (around lines 41–44).
- [x] `.pipelex/pipelex.toml` — remove the commented-out transient-retry block (around lines 40–44, including the `# Uncomment and adjust...` lead-in). It is commented so boot won't fail, but a user uncommenting `max_transient_retries` after this change would hit a config-load failure against the removed field.
- [x] `make tb` — confirm the boot sequence still loads the config (model ↔ toml in sync).

### 1.4 — Tests

- [x] Delete `tests/unit/pipelex/pipe_run/test_pipe_router_retry.py`.
- [x] Delete `tests/integration/pipelex/pipes/operator/test_operator_transient_retry.py`.
- [x] `tests/unit/pipelex/system/configuration/test_pipeline_execution_config.py` — drop expectations on the removed retry fields.
- [x] Add one small guard test pinning **both** branches of the kept handler: (a) a transient `CogtError` from `_run_pipe_job` surfaces on the **first** attempt (`_run_pipe_job` called exactly once) — pins the "direct = single pipeline-level attempt" contract against a future re-introduction of a loop; (b) a `PipeRunError` from `_run_pipe_job` surfaces as `PipeRouterError` with the pipe-stack context intact — pins the "keep the handler" contract against a future accidental handler deletion.

### 1.5 — Docs

- [x] `CHANGELOG.md` `[Unreleased]` — record the removal (reverses the Phase 5 "application-level retry of transient inference failures" entry).
- [x] `wip/error-handling/todos-retry-graph-trace.md` — mark resolved-by-removal (the PipeRouter loop was the sole cause of the phantom-error-node bug it describes).
- [x] `wip/error-handling/README.md` — update the Retry & resilience status row: the loop is now removed (the row currently carries a "Superseded" pointer plus a "Landed in current code" description that becomes false here).

> **CHECKPOINT — Workstream 1 complete.**
> - `make agent-check` clean (ruff, plxt, pyright 0 errors, mypy clean); `make tb` green (config model ↔ toml in sync); `make agent-test` green (full suite).
> - `max_concurrency` left intact in `PipelineExecutionConfig` and all three `pipelex.toml` files; the `except (CogtError, PipeRunError)` handler in `run()` kept (now without the loop); the `PipeLLM` / `PipeStructure` operator wrapping untouched; `find_inference_error_category_in_chain` left in `cogt/exceptions.py` for Temporal's use.
> - **Deviations from the steps:**
>   - 1.4 — `test_pipeline_execution_config.py` was *deleted entirely* rather than "drop expectations": both its test functions targeted only the removed `_validate_transient_retry_timing` validator, so dropping the retry expectations left an empty file.
>   - 1.4 — the guard test landed in a new file `tests/unit/pipelex/pipe_run/test_pipe_router_run.py` (`TestPipeRouterRun`), since `test_pipe_router_retry.py` was deleted.
>   - 1.5 — `CHANGELOG.md`: the "Application-level retry of transient inference failures" entry was *removed* from `[Unreleased]` rather than reversed with a "Removed" entry — it was never in a release, so a Removed line would only confuse release-notes readers. Two cross-references were also corrected: the `PipeBatch` entry ("second resilience pillar beside transient retry" → "the resilience-without-Temporal pillar") and the Temporal activity-boundary entry (dropped the "Temporal-side twin of the non-Temporal `PipeRouter` transient-retry path" sentence).
> - Not committed — left for the user / the W1 PR step.

---

## Workstream 2 — Make Tier 1 (transport retry) explicit and uniform

Not a TDD build of a new layer — the SDK-backed paths already retry transient transport failures. This makes that retry a deliberate, uniform, configured policy, closes the worker families that don't get it (the Mistral and Google SDKs default to no transport retry), and confines `instructor`'s structured-output retry to genuine schema re-ask so the SDK floor is the *only* transport-retry layer.

### 2.1 — Config

- [x] Add an inference-client transport-retry setting to the `cogt` config (`pipelex/cogt/config_cogt.py`). **Name it distinctly** — `transport_max_retries` (or `sdk_client_max_retries`) — **not** `max_retries`: a bare `max_retries` collides with `llm_job.job_config.max_retries`, which is `instructor`'s schema-re-ask count (`stop_after_attempt`). The two are different things — transport floor vs. schema re-ask — and must read as different. Placement: a small transport-scoped block, or `LLMConfig`. **Do not put it in `InstructorConfig`** — it configures the SDK transport client, not `instructor`. Decide whether request `timeout` joins it or stays per-provider (Anthropic already derives its own from `structured_output_timeout_seconds` — leaving timeout per-provider is fine). — **Done:** named `transport_max_retries`, `Field(ge=0, le=10)`. **Deviation:** placed directly on the `Cogt` config (not `LLMConfig`) — the SDK client factories it feeds also build image-generation clients, so a `Cogt`-level field reads honestly for both; `LLMConfig` would have been a naming smell on the img-gen path. `timeout` left per-provider.
- [x] Defaults in `pipelex/pipelex.toml` — `transport_max_retries = 2`, matching the current SDK default so behavior is unchanged until deliberately tuned. `make tb` to confirm the config loads. — **Done:** `transport_max_retries = 2` under `[cogt]`; `make tb` green.

### 2.2 — Wire the SDK client factories

- [x] Each inference client factory passes `transport_max_retries` explicitly when constructing the SDK client, from the config — instead of inheriting the silent SDK default. **Verified list of factories that actually construct a client** (the others under `pipelex/plugins/*/` are message/param helpers and build nothing):
  - `anthropic/anthropic_factory.py` — `AsyncAnthropic` (L53), `AsyncAnthropicBedrock` (L62/68). — **Done:** `max_retries=` on all three.
  - `openai/openai_client_factory.py` — `AsyncAzureOpenAI` (L55), `AsyncOpenAI` (L68). — **Done:** `max_retries=` on both.
  - `gateway/gateway_factory.py` — `AsyncPortkey` (L67) **and** the `AsyncOpenAI` clients for completions/responses (`make_portkey_openai_client_for_*`). **Note:** the gateway client is `AsyncPortkey` (the `portkey-ai` SDK), **not** `openai.AsyncOpenAI` as the track doc states. — **`AsyncPortkey` NOT wired** (see next item — became a 2.4-noted case).
  - `portkey/portkey_completions_factory.py` — `AsyncOpenAI` (L110); `portkey/portkey_responses_factory.py` — `AsyncOpenAI` (L37). — **Done:** `max_retries=` on both.
  - `mistral/mistral_factory.py` — `Mistral` (L52). — **Done:** `retry_config=` (see below).
  - `google/google_factory.py` — `GoogleGenAiClient` (L22). — **Done:** `http_options=HttpOptions(retry_options=...)`.
- [x] `AsyncOpenAI` / `AsyncAnthropic` accept `max_retries` directly. **Verify `AsyncPortkey`'s retry parameter before wiring** — the `portkey-ai` SDK may not expose `max_retries` the same way as `openai.AsyncOpenAI`; if it doesn't, the gateway path becomes a 2.4 case. For the `Mistral` SDK and the Google SDK, find the equivalent option (Speakeasy-style `retry_config`, `HttpOptions.retry_options`, etc.). — **Done & verified:** OpenAI/Anthropic `max_retries` (SDK default 2). `AsyncPortkey` exposes **no** `max_retries` knob — it builds an internal OpenAI client with a hard-coded `max_retries=1`; left as-is (it is a retrying SDK, so wrapping it would double-retry). Mistral SDK has no transport retry by default → wired a `RetryConfig` (`strategy="backoff"`, `retry_connection_errors=True`); its retry is **time-budget based, not attempt-count based**, so `transport_max_retries` acts as an on/off switch for Mistral (positive → bounded-backoff retry). Google `genai` has no retry by default → wired `HttpOptions(retry_options=HttpRetryOptions(attempts=transport_max_retries + 1))` (`attempts` counts the initial try).

> **CHECKPOINT — SDK-backed workers explicit.** Config landed on the `Cogt` model as `transport_max_retries` (`pipelex/cogt/config_cogt.py`), default `2` in `pipelex/pipelex.toml` under `[cogt]`. `make agent-check` clean (ruff, plxt, pyright 0 errors, mypy clean); `make tb` green. SDK without a `max_retries` equivalent: `AsyncPortkey` (`portkey-ai`) — it carries its own internal retry, so it is left unwired rather than treated as an SDK-less gap; only the gateway's underlying `AsyncOpenAI` clients are wired.

### 2.3 — Confine `instructor` to schema re-ask

The structured-output path (`PipeLLM` / `PipeStructure`) wraps each completion with `instructor`. `instructor` wraps the *factory-built* SDK client (`from_openai(client=...)`, `from_anthropic(...)`, `from_mistral(...)`, `from_genai(...)`), so 2.2's factory `max_retries` does reach structured calls. But `instructor`'s own `max_retries`, passed as an `int` (`llm_job.job_config.max_retries`, default 3), builds a `tenacity` loop whose default predicate retries **any** exception — so it re-runs the whole completion on transport / API errors too, a second retry loop nested on the SDK floor (worst case ≈ `job_config.max_retries × (cogt.max_retries + 1)` attempts). This is the layer the v1 plan wrongly scoped out as "schema-validation only."

- [x] Add a shared helper returning a `tenacity.AsyncRetrying` whose `retry=` predicate is `retry_if_exception_type((pydantic.ValidationError, json.JSONDecodeError))` and whose `stop` is `stop_after_attempt(job_config.max_retries)`. `instructor.core.retry.initialize_retrying()` accepts a pre-built `AsyncRetrying` and uses it as-is. — **Done:** new module `pipelex/cogt/llm/instructor_retry.py`, `make_instructor_schema_retrying(max_attempts)`. **Deviation:** the predicate also lists `instructor`'s own `ValidationError` / `AsyncValidationError` — verified (research) that those are **not** subclasses of `pydantic.ValidationError`, so a `(pydantic.ValidationError, json.JSONDecodeError)`-only predicate would miss genuine schema failures `instructor` surfaces as its own types. The full tuple mirrors `instructor.core.retry.retry_async`'s own validation `except`.
- [x] In the four `instructor` call sites — `openai_completions_llm_worker.py`, `openai_responses_llm_worker.py`, `anthropic_llm_worker.py`, `google_llm_worker.py` — replace `max_retries=llm_job.job_config.max_retries` (the bare `int`) with that `AsyncRetrying`. `mistral_llm_worker.py` passes no `max_retries` today (so `instructor` defaults to 1 — no re-ask; and the Mistral SDK has no transport retry either): give it the same `AsyncRetrying` so structured Mistral gets schema re-ask. — **Done:** all five wired. `openai_responses` needed a `# type: ignore[arg-type]` — instructor's `responses` path is stub-typed `int | Retrying` (no `AsyncRetrying`), though `initialize_retrying` accepts and the async path needs an `AsyncRetrying`.
- [x] **Behavior change to handle:** with a validation-only predicate a transport error is no longer retried by `instructor` and no longer wrapped in `InstructorRetryException` — it propagates as the raw SDK exception. ... The task is therefore **verify-coverage, not add-catch** ... — **Done & verified:** OpenAI/Anthropic — `anthropic.APITimeoutError` ⊂ `APIConnectionError` and `openai.APITimeoutError` ⊂ `APIConnectionError`; every status error ⊂ `APIStatusError`; so `except (APIStatusError, APIConnectionError)` is exhaustive for transport types — **no widening needed**. (`APIResponseValidationError` is under `APIError` only, not a transport error — out of scope.) Google & Mistral — **widening needed and done:** both SDKs let raw `httpx` connection/timeout errors propagate **outside** their `ServerError`/`ClientError` / `MistralError` hierarchies, so `_gen_object` **and** `_gen_text` gained an `except httpx.TransportError` clause classifying as TRANSIENT (`_raise_categorized_google_sdk_error` extended; new `_classify_mistral_transport_error` helper).
- [x] Update the worker comments at the `max_retries=` call sites — they were corrected during this plan markup to describe *current* (retries-everything) behavior; once this step lands, update them to the new (re-ask-only) behavior. — **Done:** all five call-site comments rewritten to the schema-re-ask-only behavior.
- [x] `CHANGELOG.md` `[Unreleased]` — record that `instructor`'s structured-output retry no longer re-runs completions on transport errors; transport retry is solely the SDK floor. — **Done:** `### Changed` entry added.

### 2.4 — Cover the non-SDK / weak-SDK workers

- [x] Audit the workers that do not ride a retrying SDK and verify the rest:
  - `pipelex/plugins/azure_rest/azure_img_gen_worker.py` — raw `httpx.AsyncClient`, **no** retry layer. Genuinely SDK-less — **gets the retry floor.**
  - FAL — `fal/fal_img_gen_worker.py` submits via the **`fal_client` SDK** (`AsyncClient.submit()`). **Verified (research):** `fal_client` has its **own internal transport retry** (`MAX_ATTEMPTS`, exponential backoff, retries timeouts/transport errors/transient statuses) — so FAL is **left as-is**, not brought to the floor. `fal_poller.py`'s `tenacity` is job-status polling — left as-is.
  - Mistral / Google — **verified (research):** Mistral SDK has **no** transport retry by default, Google `genai` defaults to a never-retry stop strategy — both wired in 2.2 (`RetryConfig` / `HttpOptions.retry_options`).
- [x] Bring each genuine gap up to the same floor ... For the SDK-less paths, build the floor on **`tenacity`** ... — **Done:** the one genuine SDK-less gap is the `azure_rest` image-gen worker. New module `pipelex/cogt/inference/transport_retry.py` — `request_with_transport_retry(send_request, max_retries, retry_on_ambiguous_failure=True)` built on `tenacity`: retry predicate on `httpx.TransportError` + transient statuses (408/409/429/5xx), a `wait` callable honoring `Retry-After` (capped 60s, else exponential backoff), `stop_after_attempt(max_retries + 1)`. **Deviation:** `stop_after_attempt(max_retries + 1)` (not the plan's literal `stop_after_attempt(transport_max_retries)`) — `transport_max_retries` counts retries beyond the initial attempt (the OpenAI/Anthropic semantics), so `+ 1` keeps the SDK-less floor consistent with the SDK-backed ones. The wrapper carries the idempotency caveat as `retry_on_ambiguous_failure` (False → no retry on an ambiguous 5xx); `azure_img_gen_worker.py` passes `retry_on_ambiguous_failure=False` — image generation is a billable, non-idempotent POST, so an ambiguous 5xx (Azure may have already generated and billed the image) is not retried; only connection errors and 408/409/429 are.

### 2.5 — Tests + docs

- [x] Test that each factory builds its client with the configured `transport_max_retries` (a construction test — do not try to unit-test SDK retry over the network). — **Done:** `tests/unit/pipelex/plugins/test_transport_retry_wiring.py` — `TestTransportRetryWiring`, one method per factory (patches the SDK client constructor, asserts the configured value reaches it).
- [x] Test the `instructor` retrying helper (2.3): a transport-style exception is **not** retried (the predicate excludes it) and propagates raw; a `pydantic.ValidationError` **is** retried up to `stop_after_attempt`. — **Done:** `tests/unit/pipelex/cogt/llm/test_instructor_retry.py`.
- [x] **CRITICAL — regression coverage for the 2.3 behavior change.** ... Add, **per worker** ... a test that a raw SDK transport exception raised from `create_with_completion` is classified into the correct `InferenceErrorCategory` ... — **Done:** added `test_raw_sdk_transport_error_is_classified` (parametrized) to each of the five `test_*_object_error_handling.py` files; google/mistral cases include raw `httpx` connection/timeout errors. Also **updated the five `test_real_instructor_wraps_*` end-to-end tests** — they asserted the *old* behavior (instructor wraps the SDK exception in `InstructorRetryException`); renamed to `test_real_instructor_propagates_transport_error_raw` and re-pointed at the new behavior (raw SDK exception propagates, `__cause__ is sdk_exc`).
- [x] Test the new `tenacity`-based SDK-less retry wrapper (2.4): mock the `httpx` transport, assert it retries the transient statuses and honors `Retry-After`, mock `asyncio.sleep`; assert a submit-style call is **not** retried on an ambiguous 5xx (idempotency caveat). — **Done:** `tests/unit/pipelex/cogt/inference/test_transport_retry.py`.
- [x] `CHANGELOG.md` `[Unreleased]` — record that inference-client transient retry is now an explicit, uniform policy. — **Done:** `### Added` entry.
- [x] `wip/error-handling/README.md` + `track-retry-and-resilience.md` — flip Tier 1 status to landed. — **Done.**
- [x] `make agent-test`. — **Done: green.**

> **CHECKPOINT — Workstream 2 complete.**
> - `make agent-check` clean (ruff, plxt, pyright 0 errors, mypy clean); `make tb` green; `make agent-test` green (full suite).
> - Every inference worker family now has a defined, explicit transport-retry floor: OpenAI / Anthropic / gateway-OpenAI / Mistral / Google via their SDKs (configured from `cogt.transport_max_retries`); the SDK-less `azure_rest` image-gen path via the `tenacity` wrapper; FAL via its own `fal_client` SDK retry; the gateway `AsyncPortkey` via the `portkey-ai` SDK's own internal retry. `instructor`'s structured-output retry is confined to schema re-ask, so transport retry is the SDK / wrapper floor alone.
> - **Deviations from the steps** (each explained inline above): config placed on `Cogt` not `LLMConfig`; `instructor` predicate also lists instructor's own validation-error types; `AsyncPortkey` left unwired (no `max_retries` knob, has internal retry); SDK-less wrapper uses `stop_after_attempt(transport_max_retries + 1)`; Mistral retry is on/off (time-budget SDK); the five `test_real_instructor_wraps_*` tests were renamed and re-pointed at the inverted behavior; `openai_responses` needed one `# type: ignore[arg-type]`.
> - New modules: `pipelex/cogt/llm/instructor_retry.py`, `pipelex/cogt/inference/transport_retry.py`. New tests: `test_transport_retry_wiring.py`, `test_instructor_retry.py`, `test_transport_retry.py`, plus methods added to the five `test_*_object_error_handling.py` files.
> - Not committed — left for the user / the W2 PR step.

---

## Key files

**Workstream 1 (remove):**

- `pipelex/pipe_run/pipe_router_protocol.py` — `run()`, the loop.
- `pipelex/pipe_run/pipe_router.py`, `pipelex/pipe_run/dry_pipe_router.py`, `pipelex/pipe_run/transient_retry.py`; `pipelex/temporal/tprl_pipe/temporal_pipe_router.py`.
- `pipelex/system/configuration/configs.py` — `PipelineExecutionConfig`.
- `pipelex/pipelex.toml`, `pipelex/kit/configs/pipelex.toml`.
- Tests: `tests/unit/pipelex/pipe_run/test_pipe_router_retry.py`, `tests/integration/pipelex/pipes/operator/test_operator_transient_retry.py`, `tests/unit/pipelex/system/configuration/test_pipeline_execution_config.py`.

**Workstream 2 (make Tier 1 explicit):**

- `pipelex/cogt/config_cogt.py` — `Cogt` config; the new `transport_max_retries` setting goes here (not in `InstructorConfig`). `pipelex/pipelex.toml` — its default.
- SDK client factories (verified — those that construct a client): `pipelex/plugins/anthropic/anthropic_factory.py`, `pipelex/plugins/openai/openai_client_factory.py`, `pipelex/plugins/gateway/gateway_factory.py` (`AsyncPortkey` + the gateway `AsyncOpenAI` clients), `pipelex/plugins/portkey/portkey_completions_factory.py` + `portkey_responses_factory.py`, `pipelex/plugins/mistral/mistral_factory.py`, `pipelex/plugins/google/google_factory.py`.
- Non-SDK / weak-SDK workers: `pipelex/plugins/azure_rest/azure_img_gen_worker.py`, the FAL submit path, plus Mistral / Google verification.
- `instructor` call sites (2.3): `pipelex/plugins/openai/openai_completions_llm_worker.py`, `openai/openai_responses_llm_worker.py`, `anthropic/anthropic_llm_worker.py`, `google/google_llm_worker.py`, `mistral/mistral_llm_worker.py`. `instructor`'s retry implementation: `.venv/.../instructor/core/retry.py` (`initialize_retrying`, `retry_async`).
- Reference for what "transient" means: `pipelex/cogt/inference/error_classification.py` and `InferenceErrorCategory` in `pipelex/cogt/exceptions.py`. The installed SDKs' retry logic is in `.venv/.../openai/_base_client.py` and `.venv/.../anthropic/_base_client.py` (`DEFAULT_MAX_RETRIES`, `_should_retry`).

## Out of scope

- Multi-tenant rate pacing / quotas, caller run deadline/budget, idempotency model, circuit breaking — platform/product concerns; see [wip/temporal-next/00-enterprise-readiness-analysis.md](wip/temporal-next/00-enterprise-readiness-analysis.md).
- Temporal Tier 2 changes — only a review of whether its `RetryPolicy` defaults are right for the hosted product; not this plan.
- `fal_poller.py`'s `tenacity` (job-status polling) — not transport-error retry; stays as-is. (`instructor`'s `max_retries` was listed here in the v1 plan — wrongly; it retries transport errors too and is now Workstream 2.3.)

## Risks / gotchas

- **Keep the `except (CogtError, PipeRunError)` handler in `run()`** — only the loop is removed. Deleting the handler would drop error propagation (the `PipeRouterError` wrap, pipe-stack context).
- **Do not touch `gather_bounded` / `max_concurrency`** — easy to over-delete when removing "resilience" config; it is the bounded-fan-out pillar and stays.
- **Do not revert the operator wrapping** (`PipeLLM` / `PipeStructure` catching `LLMCompletionError` → `PipeRunError`) — propagation, not retry.
- **`make tb` after config/toml edits** — the config model and every `pipelex.toml` must stay structurally in sync or boot fails.
- **Configure the SDK retry; do not replace it.** Disabling SDK retries (`max_retries = 0`) to hand-roll a Pipelex retry would re-implement well-tested SDK behavior (status classification, `Retry-After` parsing, backoff) — over-engineering. Only the genuinely SDK-less paths (Workstream 2.3) get a Pipelex `httpx`-level retry.
- **`Retry-After` is the SDK's job.** The OpenAI / Anthropic SDKs honor `Retry-After` only when ≤ 60s, else exponential backoff — accept that boundary; a longer wait is the Temporal line, not something to chase in direct mode.
- **`instructor` is a second transport-retry loop.** Passed an `int`, `instructor`'s `max_retries` retries any exception, transport included (Workstream 2.3). Making Tier 1 "explicit" by touching only the factories and leaving `instructor` as an `int` leaves the structured-output floor non-uniform (`job_config.max_retries × cogt.transport_max_retries`) and unmeasured — do not skip 2.3.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 7 issues + 1 regression, all resolved into the plan |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | not applicable (backend/infra) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **UNRESOLVED:** 0
- **VERDICT:** ENG CLEARED — plan amended, ready to implement. Ship as two PRs (W1 then W2).
