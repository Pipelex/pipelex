# Track — Retry and Resilience (Target Architecture)

> **This is a target-architecture doc, not a current-state description.** It supersedes the earlier version of this track, which described the pre-Phase-5 world plus followups that have since landed — and are now partly being reversed. The directory README's status row still reflects landed code; treat this doc as the forward plan that row will eventually be synced to.

## Premise

Resilience is Temporal's job. Pipelex integrates Temporal precisely so that durability, redelivery, and retry-under-failure are handled by a system built for it. Direct (non-Temporal) execution must **not** try to reproduce that. Direct execution should be clean and honest about what it is: a single-attempt runner. The value of the direct path is simplicity and zero infrastructure — not resilience.

This track defines where retry legitimately lives, removes the layer where the direct path was over-reaching, and keeps one small thing at the worker layer because it is protocol fidelity rather than resilience.

## Decisions taken

- **No application-level transient-retry loop in direct execution.** The `PipeRouter` transient-retry loop (Phase 5) is removed. A transient failure in direct mode surfaces immediately, on the first attempt. Rationale: the loop only ever runs on the direct path anyway — it is dead code on the Temporal path, because `_run_pipe_job` there raises `WorkflowExecutionError` / `TemporalError`, which the loop's `except (CogtError, PipeRunError)` never catches. It also re-runs at the wrong granularity (a whole pipe, re-rendering prompts), ignores the provider's `Retry-After`, and carries a per-run/global config bug (the retry budget is snapshotted from global config at router construction, so a per-run `execution_config` is silently ignored). Fixing all of that for a path that is deliberately the non-resilient one is not worth it. Removing it is.

- **A thin, shared, in-worker retry that honors the provider's `Retry-After`.** When a provider returns a rate-limit error that explicitly states a wait duration, the worker waits that long and retries, with a small bounded attempt count. Rationale: the classifier already extracts `retry_after_seconds` into `ProviderErrorMetadata` on every inference error — capturing it and never consuming it is the dishonest state. Obeying an explicit "wait N seconds" is correct API citizenship; ignoring it and retrying sooner (blind backoff, or Temporal's static backoff) wastes calls and is worse provider behavior. This is protocol fidelity, not durable resilience — it is small, bounded, and lives in worker code so it serves both paths.

- **Bounded fan-out stays.** `PipeBatch`'s `gather_bounded` / `max_concurrency` is admission control, not retry — it stops a large batch from causing a self-inflicted rate-limit storm. It is honest, cheap, and prevents a problem rather than recovering from one. It stays as-is.

## The model — where retry lives

| Layer | What it does | Scope | Owned by | Status |
|---|---|---|---|---|
| SDK transport | Connection resets, DNS, some 5xx — retried inside the OpenAI / Anthropic / Google SDKs | below Pipelex | SDK defaults | exists, not ours |
| **Tier 1 — rate-limit fidelity** | Honors a provider's explicit `Retry-After`: wait the stated time, retry, small bounded count | inside the worker; both paths | platform (worker config) | **to build** |
| **Tier 2 — Temporal durability** | Activity retry keyed off `InferenceErrorCategory.is_retryable`; workflow-level durability and redelivery | Temporal path only | platform (worker / queue config) | **landed** |
| ~~PipeRouter transient-retry loop~~ | ~~Re-ran a whole pipe on a transient inference error~~ | ~~direct path only~~ | — | **to remove** |
| Bounded fan-out | Caps simultaneous branches in `PipeBatch` so a large batch does not storm the provider | both paths | platform (`max_concurrency`) | landed, stays |

The deliberate gap: between Tier 1 and Tier 2 there is **nothing** on the direct path. That is the honest contract — direct execution attempts once (modulo the SDK's own transport retries and Tier 1's `Retry-After` obedience) and then surfaces the error.

## Current state vs target

**SDK transport.** The provider SDKs retry connection-level failures and some 5xx by default. Not ours to design; it means Tier 1 does not need to handle bare connection blips.

**Tier 1 — rate-limit fidelity.** *Missing.* The gateway workers previously had a `tenacity` retry; it was removed deliberately (it was quick-and-dirty and Portkey-specific) to be rebuilt once the resilience picture was clear — this doc is that picture. `fal_poller.py` uses `tenacity` for *polling* job status, which is not error-retry and is out of scope. `instructor`'s `max_retries` retries structured-output schema-validation failures, not transport errors — also out of scope. Net: today there is no Pipelex-owned `Retry-After` handling.

**Tier 2 — Temporal durability.** *Landed.* `TemporalError.from_message_exception()` sets `non_retryable = not InferenceErrorCategory.is_retryable`; every in-scope activity is wrapped by `@convert_pipelex_errors`; `RetryPolicyConfig` composes baseline + per-queue + per-handle `non_retryable_error_types`. This is the resilience tier and needs no change here — only a review of whether its defaults (which categories retry, attempt caps, backoff) are right for the hosted product.

**PipeRouter transient-retry loop.** *Landed, to be removed.* See decision above.

**Bounded fan-out.** *Landed, stays.* `gather_bounded` in `pipelex/tools/misc/async_utils.py`, `max_concurrency` on `PipelineExecutionConfig`, consumed by `PipeBatch`.

## What changes

Two independent workstreams — either can be done first.

### Workstream 1 — Remove the PipeRouter transient-retry loop

- `pipelex/pipe_run/pipe_router_protocol.py` — `run()` drops the retry `while` loop and calls `_run_pipe_job()` once. The `except (CogtError, PipeRunError)` handler **stays**: wrapping a `PipeRunError` into `PipeRouterError` and re-raising a raw `CogtError` as-is is error propagation, not retry. Remove the `transient_retry_settings` Protocol attribute and the chain-walking retry classification.
- Delete `pipelex/pipe_run/transient_retry.py` (`TransientRetrySettings`).
- `pipelex/pipe_run/pipe_router.py` — delete `make_transient_retry_settings()`; `PipeRouter.__init__` no longer sets `transient_retry_settings`. Same removal in `DryPipeRouter` and `TemporalPipeRouter` (the latter's was dead code anyway).
- `pipelex/system/configuration/configs.py` — remove the transient-retry fields from `PipelineExecutionConfig` and the `_validate_transient_retry_timing` validator. Keep `max_concurrency`.
- Remove the transient-retry settings from `pipelex/pipelex.toml` and `pipelex/kit/configs/pipelex.toml`.
- Tests — delete `test_pipe_router_retry.py` and `test_operator_transient_retry.py`; update `test_pipeline_execution_config.py`.
- The operator wrapping (`PipeLLM` / `PipeStructure` catching `LLMCompletionError` and re-raising as `PipeRunError`) **stays** — it is error-context propagation. The `__cause__`-walking fix from `todos-llm-retry-loop-bypass.md` existed only to feed the retry loop; with the loop gone, that classification logic in the router goes too. The same `is_retryable` signal still drives Temporal's retry decision (Tier 2), unaffected.
- CHANGELOG — the Phase 5 "application-level retry of transient inference failures" entry is reversed.

### Workstream 2 — Build Tier 1 (Retry-After fidelity)

- A single shared async helper under `pipelex/cogt/inference/` — **one** implementation, not per-worker copies (the per-worker duplication was exactly why the old gateway retry was quick-and-dirty). It wraps a classified inference call: if the outcome is a rate-limit `CogtError` (category `TRANSIENT` carrying `provider_metadata.retry_after_seconds`) and attempts remain, sleep the stated duration (capped) and retry; otherwise raise.
- A small config block in the cogt config: a max attempt count and a cap on the longest `Retry-After` honored. Deliberately smaller than the removed `TenacityConfig`, and not Portkey-specific.
- Applied uniformly at the SDK-call / classification chokepoint across the LLM, img-gen, extract, and search workers.
- **Scope boundary — Tier 1 does exactly one thing.** It acts only on an explicit `Retry-After`. A `TRANSIENT` error without one is not Tier 1's concern: the SDK transport layer below has already had its turn, and above it Temporal handles it (hosted) or it surfaces (direct). Keeping this boundary tight is what makes Tier 1 honest rather than a creeping general retry.
- **Layering with Temporal.** Tier 1 runs inside Temporal activities too. If it exhausts its small budget the activity fails and Tier 2 retries — bounded × bounded, fine. Keep Tier 1 small precisely because Tier 2 is the real budget on the hosted path. Sleeping inside an activity holds a worker slot for the `Retry-After` duration; a later refinement could surface the delay via `ApplicationError.next_retry_delay` so Temporal reschedules without holding a slot — verify SDK support before relying on it; not needed for the first version.
- **Graph tracing is unaffected.** A worker-level retry sits below the pipe / graph-node layer, so a retried-then-succeeded call yields a single clean pipe node — none of the duplicate-node problem the removed loop had.

## The honest contract

- **Direct execution** — single attempt. The SDK retries transport blips; Tier 1 obeys an explicit `Retry-After`. Beyond that, a transient failure is a failure. No durability, no crash survival. This is intended, not a gap.
- **Temporal execution** — Tier 1 still obeys `Retry-After`; Tier 2 (activity `RetryPolicy` + workflow durability) provides retry-under-failure and crash survival. This is the resilient path.
- The product pitch stays clean: *direct for simplicity, Temporal for resilience* — with no half-measure in between pretending otherwise.

## Out of scope — dependencies, not part of this track

These are real and belong to the hosted product, but they are platform/product concerns, not the engine's retry behavior. They live in [../temporal-next/00-enterprise-readiness-analysis.md](../temporal-next/00-enterprise-readiness-analysis.md).

- **Multi-tenant admission control and per-tenant quotas / rate limits** — enterprise-readiness gap #7 / Phase 4. Tier 1 obeys a rate limit *after* hitting it; proactive pacing keyed to a provider account so you rarely hit one is separate, and is platform-global, not per-run.
- **Caller-supplied run deadline / budget** — the legitimate caller-facing lever: a ceiling on total time or spend that bounds every tier, as opposed to a retry dial. Not designed; belongs with the API submission envelope.
- **Idempotency model** — the prerequisite for any future "re-submit the whole run" feature. Not designed.
- **Circuit breaking** on a provider that is down. Not designed.

## Side effects — what removing the loop resolves

- The per-run/global config bug (retry budget snapshotted from global config, ignoring a per-run `execution_config`) — moot; the code is gone.
- [todos-retry-graph-trace.md](todos-retry-graph-trace.md) — a retried pipe leaving a phantom error node in the graph. The PipeRouter loop was the only source of that bug; it can be marked resolved-by-removal.
- The dead, misleading `transient_retry_settings` carried on `TemporalPipeRouter` — gone.

## Related tracks and docs

- [track-temporal-integration.md](track-temporal-integration.md) — Tier 2: how `InferenceErrorCategory` drives Temporal's retry decision.
- [track-worker-classification.md](track-worker-classification.md) — Tier 1 depends on workers classifying rate-limit errors and populating `retry_after_seconds`.
- [track-metadata-model.md](track-metadata-model.md) — `ProviderErrorMetadata.retry_after_seconds` is the field Tier 1 consumes.
- [../temporal-next/00-enterprise-readiness-analysis.md](../temporal-next/00-enterprise-readiness-analysis.md) — the multi-tenant / hosted concerns scoped out above.
