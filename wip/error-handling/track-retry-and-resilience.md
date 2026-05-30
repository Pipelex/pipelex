# Track — Retry and Resilience

## What this track is

Where retry legitimately lives in Pipelex, and how the direct (non-Temporal) path stays honest about being the non-resilient one.

Resilience is Temporal's job. Pipelex integrates Temporal precisely so that durability, redelivery, and retry-under-failure are handled by a system built for it. Direct execution does **not** reproduce that — it makes one pipeline-level attempt, on top of a transport that already shrugs off brief blips. The value of the direct path is simplicity and zero infrastructure, not resilience.

This track is landed. The state below is what the code does today.

## Decisions

- **No application-level transient-retry loop in direct execution.** There is no `PipeRouter` retry loop. Direct execution makes a single pipeline-level attempt. (An earlier loop existed; it only ever ran on the direct path, re-ran at the wrong granularity, and carried a per-run/global config bug — it was removed rather than fixed for a path that is deliberately not the resilient one.)

- **Tier 1 — transport retry — is the provider SDKs' own retry, configured by Pipelex.** The provider SDKs retry transient transport failures (connection errors / 408 / 409 / 429 / 5xx, honoring `Retry-After`). Pipelex makes that an explicit, uniform, configured policy via `cogt.transport_max_retries` instead of inheriting each SDK's silent default — and extends the same floor to the workers that do not ride a retrying SDK. It does **not** add a Pipelex retry layer on top, which would duplicate well-tested SDK behavior.

- **`instructor`'s structured-output retry is confined to schema re-ask.** `instructor` wraps the factory-built SDK client, so Tier 1's configured retry already reaches structured calls. `instructor`'s *own* retry is given a validation-only predicate, so it re-asks the model on a malformed-output failure but does **not** re-run the completion on transport errors — Tier 1 is the sole transport-retry layer.

- **Bounded fan-out stays.** `PipeBatch`'s `gather_bounded` / `max_concurrency` is admission control, not retry — it stops a large batch from causing a self-inflicted rate-limit storm. It stays as-is.

## The model — where retry lives

| Layer | What it does | Scope | Owned by |
|---|---|---|---|
| **Tier 1 — transport retry** | Retries connection errors / 408 / 409 / 429 / 5xx, honoring `Retry-After`; bounded (`cogt.transport_max_retries`, default 2) | inside the SDK / HTTP client; both paths | the provider SDKs, configured by Pipelex |
| `instructor` structured-output retry | Re-asks the model on schema-validation failure only | structured-output path; both paths | `instructor`, configured by Pipelex |
| **Tier 2 — Temporal durability** | Activity retry keyed off `InferenceErrorCategory.is_retryable`; workflow-level durability and redelivery | Temporal path only | platform (worker / queue config) |
| Bounded fan-out | Caps simultaneous branches in `PipeBatch` so a large batch does not storm the provider | both paths | platform (`max_concurrency`) |

Between Tier 1 and Tier 2 there is nothing on the direct path, by design. Direct execution retries transient *transport* failures (via the SDK) and then surfaces the error — it does not retry at the pipeline level, and it does not survive a crash. That is the honest contract.

## Current state

**Tier 1 — transport retry.** `cogt.transport_max_retries` (default 2) is wired explicitly into every inference SDK client factory under `pipelex/plugins/*/` — Anthropic, OpenAI / Azure OpenAI, the Portkey-backed gateway OpenAI clients, Mistral, and Google. The two families that defaulted to *no* transport retry are brought up to the floor: the Mistral client is built with a bounded-backoff `RetryConfig` (`retry_connection_errors=True`), the Google `genai` client with `HttpOptions(retry_options=...)`. The genuinely SDK-less path — the raw-`httpx` `azure_rest` image-gen worker — uses a `tenacity`-based transport-retry wrapper (`pipelex/cogt/inference/transport_retry.py`) that retries connection failures and transient HTTP statuses and honors `Retry-After`; for a non-idempotent submit-style POST it narrows the retry to failures that prove the request did no work (declining an ambiguous 5xx, a 409, and a post-delivery timeout). FAL rides the `fal_client` SDK, which has its own internal transport retry; the `portkey-ai` gateway SDK exposes no `max_retries` knob and carries its own internal retry — both are left as-is. `fal_poller.py`'s `tenacity` is job-status *polling*, not error-retry, and is also left as-is.

**`instructor` structured-output retry.** Each `instructor` call site passes a `tenacity.AsyncRetrying` built by `pipelex/cogt/llm/instructor_retry.py`, whose predicate matches only validation failures (`pydantic.ValidationError`, `json.JSONDecodeError`, and `instructor`'s own validation-error types). A transport error therefore propagates immediately as the raw SDK exception rather than being wrapped in `InstructorRetryException`. Consequence handled: the Google and Mistral structured workers carry an `httpx.TransportError` `except` clause, since those SDKs let raw connection / timeout errors propagate outside their own exception hierarchies.

**Tier 2 — Temporal durability.** `TemporalError.from_message_exception()` sets `non_retryable = not InferenceErrorCategory.is_retryable`; every in-scope activity is wrapped by `@convert_pipelex_errors`; `RetryPolicyConfig` composes baseline + per-queue + per-handle `non_retryable_error_types`. See [track-temporal-integration.md](track-temporal-integration.md).

**Bounded fan-out.** `gather_bounded` in `pipelex/tools/misc/async_utils.py`, `max_concurrency` on `PipelineExecutionConfig`, consumed by `PipeBatch`.

## The honest contract

- **Direct execution** — retries transient *transport* failures via the provider SDK (bounded, `Retry-After` honored), then surfaces the error. Structured-output calls additionally re-ask the model on schema-validation failure (`instructor`) — output-shaping, not resilience. No pipeline-level retry, no durability, no crash survival. Intended, not a gap.
- **Temporal execution** — the same transport retry, plus Tier 2 (activity `RetryPolicy` + workflow durability) for retry-under-failure and crash survival. The resilient path.
- The product pitch stays clean: *direct for simplicity, Temporal for resilience* — with no half-measure in between pretending otherwise.

## Open gaps

None for this track. The one open-ended item is a review (not a change) of whether Temporal's Tier 2 defaults — which categories retry, attempt caps, backoff — are right for the hosted product.

## Out of scope — dependencies, not part of this track

These are real and belong to the hosted product, but they are platform/product concerns, not the engine's retry behavior. They are tracked in the internal enterprise-readiness plans.

- **Multi-tenant admission control and per-tenant quotas / rate limits.** Tier 1 obeys a rate limit *after* hitting it; proactive pacing keyed to a provider account is separate and platform-global, not per-run.
- **Caller-supplied run deadline / budget** — a ceiling on total time or spend that bounds every tier. Belongs with the API submission envelope.
- **Idempotency model** — the prerequisite for any future "re-submit the whole run" feature.
- **Circuit breaking** on a provider that is down.

## Related tracks and docs

- [track-temporal-integration.md](track-temporal-integration.md) — Tier 2: how `InferenceErrorCategory` drives Temporal's retry decision.
- [track-metadata-model.md](track-metadata-model.md) — `ProviderErrorMetadata` carries `retry_after_seconds` for the error report; the SDK does its own `Retry-After` handling for retries.
