# Track — Retry and Resilience (Target Architecture)

> **Both workstreams have landed.** Workstream 1 (remove the `PipeRouter` transient-retry loop) shipped as PR #909; Workstream 2 (make Tier 1 transport retry explicit and uniform, and confine `instructor` to schema re-ask) has landed on `feature/Error-handling-4`. This doc now reads as a current-state description; the status table and prose below reflect landed code.

## Premise

Resilience is Temporal's job. Pipelex integrates Temporal precisely so that durability, redelivery, and retry-under-failure are handled by a system built for it. Direct (non-Temporal) execution must **not** try to reproduce that. Direct execution should be clean and honest about what it is: it makes one pipeline-level attempt, on top of a transport that already shrugs off brief blips. The value of the direct path is simplicity and zero infrastructure — not resilience.

This track defines where retry legitimately lives, removes the layer where the direct path was over-reaching, and makes the one retry that *does* belong — transport-level — an explicit, uniform policy instead of a silent accident.

## Decisions taken

- **No application-level transient-retry loop in direct execution.** The `PipeRouter` transient-retry loop (Phase 5) is removed. Rationale: the loop only ever runs on the direct path anyway — it is dead code on the Temporal path, because `_run_pipe_job` there raises `WorkflowExecutionError` / `TemporalError`, which the loop's `except (CogtError, PipeRunError)` never catches. It also re-runs at the wrong granularity (a whole pipe, re-rendering prompts), and carries a per-run/global config bug (the retry budget is snapshotted from global config at router construction, so a per-run `execution_config` is silently ignored). Fixing all of that for a path that is deliberately the non-resilient one is not worth it. Removing it is.

- **Tier 1 — transport retry — configure the SDKs' own retry; do not build a Pipelex layer.** The provider SDKs already retry transient transport failures: the OpenAI and Anthropic SDKs default to `max_retries = 2` and retry connection errors / 408 / 409 / 429 / 5xx, honoring the `Retry-After` header. A Pipelex retry helper on top would duplicate well-tested behavior — the over-engineering the premise rules out. The work is instead to make that retry an *explicit, uniform, configured* policy (the worker factories currently inherit the SDK default silently) and to extend the same floor to the workers that do not ride a retrying SDK.

- **`instructor`'s structured-output retry — confine it to schema re-ask.** `instructor` wraps the factory-built SDK client, so Tier 1's configured `max_retries` reaches structured calls. But `instructor`'s own `max_retries`, passed as an `int`, retries **any** exception — transport errors included — so structured output today runs a second transport-retry loop nested on Tier 1. Schema re-ask on malformed output is legitimate and stays; the transport-retry behavior is not — Workstream 2 removes it by giving `instructor` a validation-only retry predicate. The worker comments asserting `instructor` retries "schema-validation only" were factually wrong and have been corrected.

- **Bounded fan-out stays.** `PipeBatch`'s `gather_bounded` / `max_concurrency` is admission control, not retry — it stops a large batch from causing a self-inflicted rate-limit storm. It is honest, cheap, and prevents a problem rather than recovering from one. It stays as-is.

## The model — where retry lives

| Layer | What it does | Scope | Owned by | Status |
|---|---|---|---|---|
| **Tier 1 — transport retry** | Retries connection errors / 408 / 409 / 429 / 5xx, honoring `Retry-After`; bounded (`cogt.transport_max_retries`, default 2) | inside the SDK / HTTP client; both paths | the provider SDKs, configured by Pipelex | landed (W2) — explicit, uniform, gaps covered |
| `instructor` structured-output retry | Re-asks the model on schema-validation failure only | structured-output path; both paths | `instructor`, configured by Pipelex | landed (W2) — confined to schema re-ask |
| **Tier 2 — Temporal durability** | Activity retry keyed off `InferenceErrorCategory.is_retryable`; workflow-level durability and redelivery | Temporal path only | platform (worker / queue config) | landed |
| ~~PipeRouter transient-retry loop~~ | ~~Re-ran a whole pipe on a transient inference error~~ | ~~direct path only~~ | — | removed (W1) |
| Bounded fan-out | Caps simultaneous branches in `PipeBatch` so a large batch does not storm the provider | both paths | platform (`max_concurrency`) | landed, stays |

Between Tier 1 and Tier 2 there is nothing on the direct path, by design. Direct execution retries transient *transport* failures (via the SDK) and then surfaces the error — it does not retry at the pipeline level, and it does not survive a crash. That is the honest contract.

## Current state vs target

**Tier 1 — transport retry.** *Landed — explicit, uniform, gaps covered.* A `cogt.transport_max_retries` setting (default 2, matching the prior SDK default) is wired explicitly into every inference SDK client factory under `pipelex/plugins/*/` — Anthropic, OpenAI / Azure OpenAI, the Portkey-backed gateway OpenAI clients, Mistral, and Google — instead of inheriting the silent SDK default. The two families that defaulted to *no* transport retry are brought up to the floor: the Mistral client is built with a bounded-backoff `RetryConfig` (`retry_connection_errors=True`), the Google `genai` client with `HttpOptions(retry_options=...)`. The genuinely SDK-less path — the raw-`httpx` `azure_rest` image-gen worker — gets a `tenacity`-based transport-retry wrapper (`pipelex/cogt/inference/transport_retry.py`) that retries connection failures and transient HTTP statuses and honors `Retry-After`; for a non-idempotent submit-style POST it narrows the retry to failures that prove the request did no work, declining an ambiguous 5xx, a 409, and a post-delivery timeout. FAL rides the `fal_client` SDK, which has its own internal transport retry, so it is left as-is. The `portkey-ai` SDK exposes no `max_retries` knob and carries its own internal retry, so the gateway's `AsyncPortkey` client is left as-is. Out of scope and staying as-is: `fal_poller.py`'s `tenacity` (job-status *polling*, not error-retry).

**The `instructor` retry layer — structured output.** *Landed — confined to schema re-ask.* The structured-output path (`PipeLLM` / `PipeStructure`) wraps each completion with `instructor`, which wraps the *factory-built* SDK client — so Tier 1's configured retry already reaches structured calls. Previously `instructor`'s *own* `max_retries`, passed as a bare `int`, built a `tenacity` loop whose predicate retried **any** exception, re-running the whole completion on transport / API errors — a second retry loop nested on Tier 1. Each `instructor` call site now passes a `tenacity.AsyncRetrying` (built by `pipelex/cogt/llm/instructor_retry.py`) whose predicate matches only validation failures, so a transport error propagates immediately as the raw SDK exception and Tier 1 is the sole transport-retry layer. Consequence handled: the Google and Mistral structured workers gained an `httpx.TransportError` `except` clause, since those SDKs let raw connection / timeout errors propagate outside their own exception hierarchies.

**Tier 2 — Temporal durability.** *Landed.* `TemporalError.from_message_exception()` sets `non_retryable = not InferenceErrorCategory.is_retryable`; every in-scope activity is wrapped by `@convert_pipelex_errors`; `RetryPolicyConfig` composes baseline + per-queue + per-handle `non_retryable_error_types`. This is the resilience tier and needs no change here — only a review of whether its defaults (which categories retry, attempt caps, backoff) are right for the hosted product.

**PipeRouter transient-retry loop.** *Removed (Workstream 1).* See the decision above.

**Bounded fan-out.** *Landed, stays.* `gather_bounded` in `pipelex/tools/misc/async_utils.py`, `max_concurrency` on `PipelineExecutionConfig`, consumed by `PipeBatch`.

## What changed

Two independent workstreams — both landed.

### Workstream 1 — Remove the PipeRouter transient-retry loop *(landed, PR #909)*

- `pipelex/pipe_run/pipe_router_protocol.py` — `run()` drops the retry `while` loop and calls `_run_pipe_job()` once. The `except (CogtError, PipeRunError)` handler **stays**: wrapping a `PipeRunError` into `PipeRouterError` and re-raising a raw `CogtError` as-is is error propagation, not retry. Remove the `transient_retry_settings` Protocol attribute and the chain-walking retry classification.
- Delete `pipelex/pipe_run/transient_retry.py` (`TransientRetrySettings`).
- `pipelex/pipe_run/pipe_router.py` — delete `make_transient_retry_settings()`; `PipeRouter.__init__` no longer sets `transient_retry_settings`. Same removal in `DryPipeRouter` and `TemporalPipeRouter` (the latter's was dead code anyway).
- `pipelex/system/configuration/configs.py` — remove the transient-retry fields from `PipelineExecutionConfig` and the `_validate_transient_retry_timing` validator. Keep `max_concurrency`.
- Remove the transient-retry settings from `pipelex/pipelex.toml` and `pipelex/kit/configs/pipelex.toml`.
- Tests — delete `test_pipe_router_retry.py` and `test_operator_transient_retry.py`; update `test_pipeline_execution_config.py`.
- The operator wrapping (`PipeLLM` / `PipeStructure` catching `LLMCompletionError` and re-raising as `PipeRunError`) **stays** — it is error-context propagation. The `__cause__`-walking fix from `todos-llm-retry-loop-bypass.md` existed only to feed the retry loop; with the loop gone, that classification logic in the router goes too. The same `is_retryable` signal still drives Temporal's retry decision (Tier 2), unaffected.
- CHANGELOG — the Phase 5 "application-level retry of transient inference failures" entry is reversed.

### Workstream 2 — Make Tier 1 explicit and uniform *(landed)*

Not a new retry layer — the SDKs already retry. The work made that retry a deliberate, uniform, configured policy.

- Added `cogt.transport_max_retries` (default 2, matching the prior SDK default so behavior is unchanged until deliberately tuned); each SDK client factory under `pipelex/plugins/*/` now passes it explicitly at construction instead of inheriting the silent default. It is named distinctly from `llm_job.job_config.max_retries` (`instructor`'s schema re-ask count) — the two are different concerns.
- Confined `instructor`'s structured-output retry to schema re-ask: each call site passes a `tenacity.AsyncRetrying` whose predicate matches only validation failures (`pydantic.ValidationError`, `json.JSONDecodeError`, and `instructor`'s own validation-error types) instead of a bare `int`, so transport / API errors fall straight through to the Tier 1 floor. Consequence handled: transport errors now surface as raw SDK exceptions, not wrapped in `InstructorRetryException`, so the Google and Mistral structured workers gained an `httpx.TransportError` `except` clause to catch the raw connection / timeout errors those SDKs let propagate.
- Covered the worker families that do not ride a retrying SDK: the raw-`httpx` `azure_rest` image-gen path gets a `tenacity`-based `httpx` retry wrapper at the configured budget. FAL rides the `fal_client` SDK (internal transport retry), and the `portkey-ai` gateway SDK carries its own internal retry — neither gets a wrapper layered on top.
- `Retry-After` honoring stays the SDK / HTTP-client's job; the SDK-less wrapper parses it directly because there is no SDK to do it.
- `retry_after_seconds` stays captured in `ProviderErrorMetadata` for the error report; that is a reporting use, not a retry consumer.

## The honest contract

- **Direct execution** — retries transient *transport* failures via the provider SDK (bounded, `Retry-After` honored), then surfaces the error. Structured-output calls additionally re-ask the model on schema-validation failure (`instructor`) — output-shaping, not resilience; once Workstream 2 lands, that re-ask no longer retries transport errors. No pipeline-level retry, no durability, no crash survival. Intended, not a gap.
- **Temporal execution** — the same transport retry, plus Tier 2 (activity `RetryPolicy` + workflow durability) for retry-under-failure and crash survival. The resilient path.
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
- [track-metadata-model.md](track-metadata-model.md) — `ProviderErrorMetadata` carries `retry_after_seconds` for the error report; the SDK does its own `Retry-After` handling for retries.
- [../temporal-next/00-enterprise-readiness-analysis.md](../temporal-next/00-enterprise-readiness-analysis.md) — the multi-tenant / hosted concerns scoped out above.
