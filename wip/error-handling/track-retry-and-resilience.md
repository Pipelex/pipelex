# Track — Retry and Resilience (Target Architecture)

> **This is a target-architecture doc, not a current-state description.** It supersedes the earlier version of this track, which described the pre-Phase-5 world plus followups that have since landed — and are now partly being reversed. The directory README's status row still reflects landed code; treat this doc as the forward plan that row will eventually be synced to.

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
| **Tier 1 — transport retry** | Retries connection errors / 408 / 409 / 429 / 5xx, honoring `Retry-After`; bounded (SDK default `max_retries` = 2) | inside the SDK / HTTP client; both paths | the provider SDKs, configured by Pipelex | exists for SDK-backed workers — make explicit, cover the gaps |
| `instructor` structured-output retry | Re-asks the model on schema-validation failure. **Today also** re-runs the completion on transport / API errors (any exception) — a second retry loop nested on Tier 1 | structured-output path; both paths | `instructor`, configured by Pipelex | confine to schema re-ask only — Workstream 2 |
| **Tier 2 — Temporal durability** | Activity retry keyed off `InferenceErrorCategory.is_retryable`; workflow-level durability and redelivery | Temporal path only | platform (worker / queue config) | landed |
| ~~PipeRouter transient-retry loop~~ | ~~Re-ran a whole pipe on a transient inference error~~ | ~~direct path only~~ | — | to remove |
| Bounded fan-out | Caps simultaneous branches in `PipeBatch` so a large batch does not storm the provider | both paths | platform (`max_concurrency`) | landed, stays |

Between Tier 1 and Tier 2 there is nothing on the direct path, by design. Direct execution retries transient *transport* failures (via the SDK) and then surfaces the error — it does not retry at the pipeline level, and it does not survive a crash. That is the honest contract.

## Current state vs target

**Tier 1 — transport retry.** *Exists for the SDK-backed workers; not uniform, not explicit.* The OpenAI and Anthropic SDKs default to `max_retries = 2` and retry 408 / 409 / 429 / 5xx / connection errors, honoring `Retry-After` (`retry-after` / `retry-after-ms`; the SDKs honor the header value when it is ≤ 60s, else fall back to exponential backoff). The client factories under `pipelex/plugins/*/` construct the clients **without** passing `max_retries`, so the retry is live but inherited as a silent third-party default. The Portkey gateway client is itself an `openai.AsyncOpenAI`, so the gateway extract / search / img-gen `.post()` calls are covered. Not covered: the raw-`httpx` `azure_rest` image-gen worker (no SDK retry layer), the Mistral SDK (retry is off unless a `RetryConfig` is passed — the factory passes none), and the Google `genai` SDK (defaults to a never-retry stop strategy unless `HttpOptions.retry_options` is set). Out of scope and staying as-is: `fal_poller.py`'s `tenacity` (job-status *polling*, not error-retry). The previously-removed gateway `tenacity` sat on top of the openai client's own retry and was redundant — its removal was correct.

**The `instructor` retry layer — structured output.** *A second transport-retry loop, not just schema re-ask.* The structured-output path (`PipeLLM` / `PipeStructure` — the dominant path) wraps each completion with `instructor`. `instructor` wraps the *factory-built* SDK client (`from_openai(client=...)`, `from_anthropic(...)`, `from_mistral(...)`, `from_genai(...)`), so Tier 1's configured `max_retries` does reach structured calls — good. But `instructor`'s *own* `max_retries`, passed as an `int` (`llm_job.job_config.max_retries`, default 3), builds a `tenacity` loop whose default predicate retries **any** exception. When the SDK exhausts its transport retries and raises (`RateLimitError`, `APIConnectionError`, 5xx), `instructor` catches it and re-runs the whole completion — an application-level transport-retry loop, `job_config.max_retries` deep, nested on Tier 1, with no `Retry-After` between attempts. Worst case ≈ `job_config.max_retries × (max_retries + 1)` attempts per structured call. Verified against `instructor` 1.15.1 (`instructor/core/retry.py`); the worker comments that called this "schema-validation only" were wrong. Workstream 2 confines `instructor` to genuine schema re-ask.

**Tier 2 — Temporal durability.** *Landed.* `TemporalError.from_message_exception()` sets `non_retryable = not InferenceErrorCategory.is_retryable`; every in-scope activity is wrapped by `@convert_pipelex_errors`; `RetryPolicyConfig` composes baseline + per-queue + per-handle `non_retryable_error_types`. This is the resilience tier and needs no change here — only a review of whether its defaults (which categories retry, attempt caps, backoff) are right for the hosted product.

**PipeRouter transient-retry loop.** *Landed, to be removed.* See the decision above.

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

### Workstream 2 — Make Tier 1 explicit and uniform

Not a new retry layer — the SDKs already retry. The work makes that retry a deliberate, uniform, configured policy.

- Add a small inference-client retry setting to the `cogt` config (`max_retries`, default matching today's SDK default of 2 so behavior is unchanged until deliberately tuned); each SDK client factory under `pipelex/plugins/*/` passes it explicitly at construction instead of inheriting the silent default.
- Confine `instructor`'s structured-output retry to schema re-ask: pass it a `tenacity.AsyncRetrying` with a `retry_if_exception_type((ValidationError, JSONDecodeError))` predicate instead of a bare `int`, so transport / API errors fall straight through to the Tier 1 floor instead of being re-run as whole completions (`instructor` accepts a pre-built retrying object). Consequence to handle: transport errors then surface as raw SDK exceptions, not wrapped in `InstructorRetryException` — the workers' error classification must catch the raw SDK types directly.
- Audit the worker families that do not ride a retrying SDK — the raw-`httpx` `azure_rest` image-gen path, and the Mistral / Google / FAL paths — and bring them to the same floor: the configured `max_retries`, retrying transient transport failures and honoring `Retry-After`. A small `httpx`-level retry is fine for the paths that genuinely lack SDK retry; do not add one on top of a retrying SDK.
- Keep `Retry-After` honoring as the SDK / HTTP-client's job — do not hand-roll it.
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
