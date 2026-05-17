# TODOS — Retry & Resilience: remove the PipeRouter loop, build Tier 1 (Retry-After)

> **Type:** Implementation plan — two independent workstreams. Workstream 1 is a removal; Workstream 2 is a TDD build (RED → GREEN → REFACTOR).
> **Source / intent:** [wip/error-handling/track-retry-and-resilience.md](wip/error-handling/track-retry-and-resilience.md) — the target-architecture doc. Where this plan and that doc differ, the doc is authoritative for *intent*; this plan is authoritative for *steps*.
> **Branch:** off `feature/Error-handling-2` — it carries the Phase 5 retry loop being removed and the error-metadata model Tier 1 consumes; `main` has neither. One branch for both workstreams is fine; they don't conflict.
> **Discipline:** `make agent-check` after each step; `make agent-test` before wrapping up. After deleting test files, `make cleanderived` if collection misbehaves. After config/toml changes, `make tb` (boot test — config model and toml must stay in sync).

## Status

**Not started.** Both workstreams open. They are independent — either order, or in parallel.

## Cold-start context

Pipelex's resilience story is Temporal. Direct (non-Temporal) execution is a single-attempt runner and should stay clean and honest about that — it must not reproduce Temporal's durability. The full reasoning, the tier model, and the decisions are in the architecture doc linked above. The two concrete consequences this plan executes:

- **Remove the `PipeRouter` application-level transient-retry loop (Phase 5).** It only ever runs on the direct path — it is dead code on the Temporal path, because `_run_pipe_job` there raises `WorkflowExecutionError` / `TemporalError`, which the loop's `except (CogtError, PipeRunError)` never catches. It also re-runs at the wrong granularity, ignores the provider's `Retry-After`, and carries a per-run/global config bug (the retry budget is snapshotted from global config at router construction, so a per-run `execution_config` is silently ignored). Removing it is cleaner than fixing it for a path that is deliberately not the resilient one.
- **Build "Tier 1" — a thin, shared, in-worker retry that honors a provider's `Retry-After`.** Protocol fidelity, not durability: when a rate-limit error explicitly states a wait, the worker waits it and retries, small bounded count. It lives in worker code, so it serves both the direct and Temporal paths.

What stays untouched: `PipeBatch` bounded fan-out (`gather_bounded` / `max_concurrency`) — admission control, not retry. Temporal Tier 2 (activity `RetryPolicy` keyed off `InferenceErrorCategory`). The operator wrapping in `PipeLLM` / `PipeStructure` (`LLMCompletionError` → `PipeRunError`) — error-context propagation.

---

## Workstream 1 — Remove the PipeRouter transient-retry loop

A removal, not a TDD build. Delete in the order below, then verify. One small guard test is added at the end.

### 1.1 — Strip the retry loop from the protocol

- [ ] `pipelex/pipe_run/pipe_router_protocol.py` — in `run()` (around lines 54–100), remove the `while True` retry loop, the backoff `asyncio.sleep`, the retry logging, and the `find_inference_error_category_in_chain` call. The resulting `run()`: `_before_run` → one `_run_pipe_job` call → `_after_successful_run` on success; on `except (CogtError, PipeRunError)`, call `_after_failing_run`, then wrap a `PipeRunError` into `PipeRouterError` / re-raise a raw `CogtError` as-is. **Keep that handler** — it is error propagation (pipe-stack context), not retry.
- [ ] Same file — remove the `transient_retry_settings: TransientRetrySettings` attribute from `PipeRouterProtocol`.
- [ ] Let `make fix-unused-imports` clean the now-unused imports (`asyncio`, `log`, `find_inference_error_category_in_chain`, `TransientRetrySettings`).
- [ ] Leave `find_inference_error_category_in_chain` in `pipelex/cogt/exceptions.py` — Temporal still uses it (`temporal_error.py`). Only the router's *use* of it goes.

### 1.2 — Delete the retry plumbing

- [ ] Delete `pipelex/pipe_run/transient_retry.py` (`TransientRetrySettings`).
- [ ] `pipelex/pipe_run/pipe_router.py` — delete `make_transient_retry_settings()`; drop `self.transient_retry_settings` from `PipeRouter.__init__`.
- [ ] `pipelex/pipe_run/dry_pipe_router.py` — drop `transient_retry_settings` from `DryPipeRouter` (around line 13) and its import.
- [ ] `pipelex/temporal/tprl_pipe/temporal_pipe_router.py` — drop `transient_retry_settings` from `TemporalPipeRouter` (around line 54) and its import. This was dead code.

### 1.3 — Remove the config

- [ ] `pipelex/system/configuration/configs.py` — from `PipelineExecutionConfig` (around lines 153–177) remove the transient-retry fields and the `_validate_transient_retry_timing` validator. **Keep `max_concurrency`** — it is the bounded-fan-out pillar and stays.
- [ ] `pipelex/pipelex.toml` — remove the transient-retry settings (around lines 290–293).
- [ ] `pipelex/kit/configs/pipelex.toml` — remove the commented-out transient-retry block (around lines 40–44).
- [ ] `make tb` — confirm the boot sequence still loads the config (model ↔ toml in sync).

### 1.4 — Tests

- [ ] Delete `tests/unit/pipelex/pipe_run/test_pipe_router_retry.py`.
- [ ] Delete `tests/integration/pipelex/pipes/operator/test_operator_transient_retry.py`.
- [ ] `tests/unit/pipelex/system/configuration/test_pipeline_execution_config.py` — drop expectations on the removed retry fields.
- [ ] Add one small guard test: a transient `CogtError` from `_run_pipe_job` surfaces on the **first** attempt (`_run_pipe_job` called exactly once) — pins the "direct = single attempt" contract against a future re-introduction of a loop.

### 1.5 — Docs

- [ ] `CHANGELOG.md` `[Unreleased]` — record the removal (reverses the Phase 5 "application-level retry of transient inference failures" entry).
- [ ] `wip/error-handling/todos-retry-graph-trace.md` — mark resolved-by-removal (the PipeRouter loop was the sole cause of the phantom-error-node bug it describes).
- [ ] `wip/error-handling/README.md` — update the Retry & resilience status row: the loop is now removed (the row currently carries a "Superseded" pointer plus a "Landed in current code" description that becomes false here).

> **CHECKPOINT — Workstream 1 complete.** _Fill when reached:_ `make agent-check` clean, `make agent-test` green; note any deviation from the steps above; confirm `max_concurrency` and the operator wrapping were left intact; record the commit(s).

---

## Workstream 2 — Build Tier 1: Retry-After fidelity

A TDD build. Settle the design first (2.0), then RED → GREEN → REFACTOR.

### 2.0 — Design decisions (settle first, record the outcome here)

- [ ] **D1 — Helper shape.** A shared async helper under `pipelex/cogt/inference/` (e.g. `rate_limit_retry.py`). Recommended: an `async` function that runs a classified inference call, inspects the resulting `CogtError`, and loops. Confirm function-vs-decorator and the module name.
- [ ] **D2 — Trigger condition.** Retry only when the classified error is a rate-limit signal carrying an explicit wait: `error_category` is `TRANSIENT` **and** `provider_metadata.retry_after_seconds is not None`. A `TRANSIENT` error *without* `retry_after_seconds` is **not** Tier 1's business — it surfaces (direct) or Temporal handles it (hosted). Confirm this boundary.
- [ ] **D3 — Config.** A small block in `pipelex/cogt/config_cogt.py` (`Cogt`): a max attempt count and a cap on the longest `Retry-After` honored. Defaults in `pipelex/pipelex.toml`. Do not revive the removed `TenacityConfig` — this is smaller and provider-agnostic. Confirm field names and placement.
- [ ] **D4 — Application point.** Wrap at each inference worker's SDK-call / classification chokepoint, uniformly across LLM / img-gen / extract / search workers. Map the exact call sites before coding (see Key files).

### 2.1 — RED

- [ ] Write a failing test for the helper: a classified call that raises a rate-limit `CogtError` with `retry_after_seconds` set is retried after waiting that long, up to the bounded count, then surfaces; a `TRANSIENT` error with no `retry_after_seconds` is **not** retried; a non-`TRANSIENT` error is **not** retried. Mock `asyncio.sleep` so the test does not actually wait. Assert the honored wait equals `retry_after_seconds` (capped per D3).
- [ ] Confirm it fails today (no helper exists).

### 2.2 — GREEN

- [ ] Implement the helper + config per 2.0. Apply it to **one** worker family (LLM is the obvious first). Make the RED test pass.
- [ ] `make agent-check`.

> **CHECKPOINT — Tier 1 helper proven on one worker.** _Fill when reached:_ record D1–D4 as decided; confirm the RED test is green; note the helper's final signature. The rest is mechanical replication.

### 2.3 — Apply to the remaining workers

- [ ] Apply the helper to the remaining inference worker families (img-gen, extract, search), uniformly.
- [ ] Extend the test to cover at least one non-LLM worker, proving the helper is not LLM-specific.

### 2.4 — REFACTOR + docs

- [ ] One shared implementation, no per-worker copies (per-worker duplication is what made the old gateway `tenacity` quick-and-dirty).
- [ ] Code comment at the helper: it honors an explicit `Retry-After` only; it is protocol fidelity, not durable resilience; on the Temporal path it runs inside the activity and is deliberately small because Temporal Tier 2 is the real budget.
- [ ] `CHANGELOG.md` `[Unreleased]` — record the new behavior.
- [ ] `wip/error-handling/README.md` + `track-retry-and-resilience.md` — flip Tier 1 from "to build" to landed.
- [ ] `make agent-test`.

> **CHECKPOINT — Workstream 2 complete.** _Fill when reached:_ `make agent-test` green; confirm uniform application across worker families; record commit(s).

---

## Key files

**Workstream 1 (remove):**

- `pipelex/pipe_run/pipe_router_protocol.py` — `run()`, the loop.
- `pipelex/pipe_run/pipe_router.py`, `pipelex/pipe_run/dry_pipe_router.py`, `pipelex/pipe_run/transient_retry.py`; `pipelex/temporal/tprl_pipe/temporal_pipe_router.py`.
- `pipelex/system/configuration/configs.py` — `PipelineExecutionConfig`.
- `pipelex/pipelex.toml`, `pipelex/kit/configs/pipelex.toml`.
- Tests: `tests/unit/pipelex/pipe_run/test_pipe_router_retry.py`, `tests/integration/pipelex/pipes/operator/test_operator_transient_retry.py`, `tests/unit/pipelex/system/configuration/test_pipeline_execution_config.py`.

**Workstream 2 (build Tier 1):**

- `pipelex/cogt/inference/error_classification.py` — where SDK errors are classified and `retry_after_seconds` is extracted into `ProviderErrorMetadata`.
- `pipelex/cogt/exceptions.py` — `InferenceErrorCategory`, `CogtError`, `ProviderErrorMetadata`.
- `pipelex/cogt/config_cogt.py` — `Cogt` config; where `TenacityConfig` used to live before removal — the new small config goes here.
- Example worker for the call+classify pattern: `pipelex/plugins/anthropic/anthropic_llm_worker.py`. The gateway workers `pipelex/plugins/gateway/gateway_extract_worker.py` / `gateway_search_worker.py` once carried the `tenacity` retry — `git log` for its removal shows where worker-level retry used to attach.

## Out of scope

- Multi-tenant rate pacing / quotas, caller run deadline/budget, idempotency model, circuit breaking — platform/product concerns; see [wip/temporal-next/00-enterprise-readiness-analysis.md](wip/temporal-next/00-enterprise-readiness-analysis.md).
- Temporal Tier 2 changes — only a review of whether its `RetryPolicy` defaults are right for the hosted product; not this plan.
- The `ApplicationError.next_retry_delay` refinement (let Temporal reschedule on the provider's `Retry-After` instead of sleeping inside the activity) — a known later refinement; verify SDK support if picked up.

## Risks / gotchas

- **Keep the `except (CogtError, PipeRunError)` handler in `run()`** — only the loop is removed. Deleting the handler would drop error propagation (the `PipeRouterError` wrap, pipe-stack context).
- **Do not touch `gather_bounded` / `max_concurrency`** — easy to over-delete when removing "resilience" config; it is the bounded-fan-out pillar and stays.
- **Do not revert the operator wrapping** (`PipeLLM` / `PipeStructure` catching `LLMCompletionError` → `PipeRunError`) — propagation, not retry.
- **`make tb` after config/toml edits** — the config model and every `pipelex.toml` must stay structurally in sync or boot fails.
- **Tier 1 patch target in tests** — patch where the *worker module* imports the SDK call, not the source module (a recurring mocking gotcha).
- **Tier 1 stays small** — it honors one explicit `Retry-After`, bounded. It must not grow into a general transient-retry; that pulls the direct path back toward pretending to be resilient.
