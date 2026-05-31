# Track — Worker Classification

## What this track is

Every inference worker that calls a third-party SDK must catch the SDK's typed exceptions and re-raise a `CogtError` subclass with an `InferenceErrorCategory`, a `user_action` hint, the model descriptor in the message, and `from exc` to preserve the cause chain. This is the foundation that everything downstream depends on — retry policy, agent hints, Temporal `non_retryable` decisions, human Rich panels.

The work to lift every worker to this standard **has landed across all worker kinds** (LLM, img-gen, extract, search), including the four LLM workers that previously mis-categorized `instructor`-wrapped errors. OpenAI Completions, OpenAI Responses, Mistral, and Google all now unwrap `InstructorRetryException` and dispatch through the same categorization helper their `_gen_text` paths use. Every worker additionally carries the beyond-reference upgrades: `InferenceErrorCategory.UNKNOWN` for unrecognized-underlying fallbacks (instead of mis-categorizing as `CONTENT`), structured `ProviderErrorMetadata` (status_code, request_id, retry_after_seconds, provider_error_code, body) on every raised inference error, and structured `UserAction(kind, detail)` with semantic `UserActionKind` values.

## Current state

### What every worker does

Each provider worker under `pipelex/plugins/*/` follows the same shape:

```python
except RateLimitError as exc:
    if is_quota_exhaustion_<provider>(str(exc)):
        msg = f"{provider} quota exhausted for model '{self.inference_model.desc}': {exc}"
        raise LLMCompletionError(
            message=msg,
            error_category=InferenceErrorCategory.CAPACITY,
            user_action="Your {provider} account has exceeded its quota — check your billing dashboard at {billing_url}",
        ) from exc
    msg = f"Rate limited by {provider} for model '{self.inference_model.desc}': {exc}"
    raise LLMCompletionError(
        message=msg,
        error_category=InferenceErrorCategory.TRANSIENT,
        user_action=f"Rate limited by {provider} — the system will retry automatically",
    ) from exc
```

The discriminator helpers are pure functions in `pipelex/cogt/inference/error_classification.py`:

- `is_quota_exhaustion_openai`
- `is_quota_exhaustion_anthropic`
- `is_quota_exhaustion_google`
- `is_quota_exhaustion_mistral(error_message, status_code)` — HTTP 402 is a definitive signal; 429 requires message inspection.
- `is_quota_exhaustion_aws`
- `is_quota_exhaustion_gateway(error_message, status_code)` — same 402 / 429 split.
- `is_content_policy_violation`

Per-provider message patterns are module constants alongside the helpers (`_OPENAI_QUOTA_PATTERNS`, `_ANTHROPIC_QUOTA_PATTERNS`, `_GOOGLE_QUOTA_PATTERNS`, `_MISTRAL_QUOTA_PATTERNS`, `_AWS_QUOTA_PATTERNS`, `_GATEWAY_QUOTA_PATTERNS`, `_CONTENT_POLICY_PATTERNS`).

### Per-worker coverage

All workers below catch their SDK's typed exceptions and assign `error_category`. Quota-vs-rate-limit and content-policy-vs-bad-request discriminators run where applicable.

| Worker | File |
|---|---|
| OpenAI Completions LLM | `pipelex/plugins/openai/openai_completions_llm_worker.py` |
| OpenAI Responses LLM | `pipelex/plugins/openai/openai_responses_llm_worker.py` |
| OpenAI img-gen | `pipelex/plugins/openai/openai_img_gen_worker.py` |
| OpenAI Completions img-gen | `pipelex/plugins/openai/openai_completions_img_gen_worker.py` |
| Anthropic LLM | `pipelex/plugins/anthropic/anthropic_llm_worker.py` |
| Google LLM | `pipelex/plugins/google/google_llm_worker.py` |
| Google img-gen | `pipelex/plugins/google/google_img_gen_worker.py` |
| Mistral LLM | `pipelex/plugins/mistral/mistral_llm_worker.py` |
| Mistral extract | `pipelex/plugins/mistral/mistral_extract_worker.py` |
| AWS Bedrock LLM | `pipelex/plugins/bedrock/bedrock_llm_worker.py` |
| Azure img-gen | `pipelex/plugins/azure_rest/azure_img_gen_worker.py` |
| FAL img-gen | `pipelex/plugins/fal/fal_img_gen_worker.py` |
| HuggingFace img-gen | `pipelex/plugins/huggingface/huggingface_img_gen_worker.py` |
| Docling extract | `pipelex/plugins/docling/docling_extract_worker.py` |
| Linkup extract | `pipelex/plugins/linkup/linkup_extract_worker.py` |
| Linkup search | `pipelex/plugins/linkup/linkup_search_worker.py` |
| Gateway extract | `pipelex/plugins/gateway/gateway_extract_worker.py` |
| Gateway img-gen | `pipelex/plugins/gateway/gateway_img_gen_worker.py` |
| Gateway search | `pipelex/plugins/gateway/gateway_search_worker.py` |
| pypdfium2 | `pipelex/plugins/pypdfium2/pypdfium2_worker.py` |

Each provides at minimum: catch SDK errors, classify, assign category, attach model descriptor, chain via `from exc`. The four dynamic-category exception types (`LLMCompletionError`, `ImgGenGenerationError`, `ExtractJobFailureError`, `SearchJobFailureError`) carry `error_category` per instance from the worker that raised them.

### Class hierarchy snapshot

`CogtError` (`pipelex/cogt/exceptions.py`) is the inference branch root. Two notable subclasses with structured fields:

- `ModelChoiceNotFoundError` carries `model_type`, `model_choice`, `reference_kind`, `available_options`, `suggestions`, `wrong_sigil_hints`, `cross_collection_suggestions`. Builds a "Did you mean: …" message automatically.
- `InferenceBackendCredentialsError` carries `credentials_error_type`, `backend_name`, `key_name`, and declares class-level `error_category = CONFIGURATION` and `user_action = "Check that the required API key environment variable is set"`.

`ModelNotFoundError` is the parent of `LLMModelNotFoundError`, `ImgGenModelNotFoundError`, and `ModelWaterfallError`. The waterfall variant adds `fallback_list`.

### The `instructor` unwrap

`extract_underlying_sdk_exception(instructor_exc)` (shared, in `pipelex/cogt/inference/error_classification.py`) recovers the SDK exception from `failed_attempts[-1].exception`, falling back to `__cause__.last_attempt._exception` (tenacity's storage). Each LLM worker's `_gen_object` path catches `InstructorRetryException`, unwraps it through that helper, and routes the result through the same per-provider categorization helper its `_gen_text` path uses; only truly unrecognized inner exceptions keep the `UNKNOWN` fallback.

Note the interaction with the retry track: since `instructor`'s retry predicate is now confined to schema re-ask ([track-retry-and-resilience.md](track-retry-and-resilience.md)), a transport error is no longer wrapped in `InstructorRetryException` — it propagates as the raw SDK exception and is caught by the worker's SDK-exception `except` clauses directly. `InstructorRetryException` now carries only genuine schema-validation failures. The end-to-end test `tests/unit/pipelex/plugins/anthropic/test_anthropic_worker_object_error_handling.py::test_real_instructor_propagates_transport_error_raw` locks that behavior in against real `instructor.from_anthropic(...)`.

## Open gaps

The classification + beyond-reference upgrades have landed across every worker kind — LLM, img-gen, extract, and search (plus AWS Bedrock LLM). The only residual note:

- **`pydantic.ValidationError` now routes to `UNKNOWN`.** When the LLM returns JSON that doesn't match the schema, `instructor` raises `InstructorRetryException` with a `ValidationError` (or `JSONDecodeError`) at `failed_attempts[-1].exception`. The unwrap branch returns it, the per-provider SDK categorization helpers don't recognize it, and the `UNKNOWN` fallback (introduced by Phase 2's upgrade A) catches it — distinguishing schema-mismatch from genuine `CONTENT`-policy violations. If we ever want a dedicated SCHEMA_MISMATCH category, the categorization helpers can be extended to recognize `pydantic.ValidationError` explicitly. Not a regression.

## What's left

Worker classification itself is complete — there is no remaining per-worker work. The deeper **Extract / Classify / Render** refactor that consolidates the now-uniform per-worker pipeline into one per-provider Extract function plus a shared Classify + Render has also landed — see [track-extract-classify-render.md](track-extract-classify-render.md). The consistency gap noted earlier (LLM workers using `classify_*_sdk_error()` free functions while img-gen workers used inline `_raise_categorized_*` methods) is largely closed: classification is unified behind the shared `classify_inference_error()` (`pipelex/cogt/inference/error_classify.py`) and the per-provider `*_error_classification.py` files are gone. One inline categorizer survives by design: the Azure REST img-gen worker keeps `_raise_categorized_azure_status_error` (`azure_img_gen_worker.py:65`, called from its generate path at `:159`). It is not a wholesale bypass — 4xx statuses route through the shared `classify_inference_error` + `render_inference_error` — but it forces 5xx statuses to `AMBIGUOUS` rather than the classifier's verdict, because image generation is a non-idempotent POST and the operation-agnostic classifier would mark a 5xx `TRANSIENT`, letting the Temporal bridge auto-retry and duplicate a billed generation.

### Risks and gotchas (for future similar work)

- The categorization helpers expect a raw SDK exception, not the wrapped one. The unwrap step in each worker preserves this contract.
- Chain via `from instructor_exc` so the traceback shows `instructor → tenacity → SDK`. Don't chain from the bare SDK exc — it loses retry context useful for debugging.
- Real-instructor + AsyncMock'd SDK tests are slightly slow (~0.5s each) because `instructor` still does its full attempt loop. Each provider has one such test (kept as an end-to-end lock-in); the remaining categorization cases use the synthetic `wrap_in_instructor_retry` helper in `tests/helpers/instructor_test_utils.py`.

## Related tracks

- [track-metadata-model.md](track-metadata-model.md) — the `error_category` / `user_action` contract the classified errors fill in.
- [track-retry-and-resilience.md](track-retry-and-resilience.md) — once workers correctly classify TRANSIENT vs CAPACITY, the router-level retry can act on those signals.
- [track-cli-delivery.md](track-cli-delivery.md) — how Rich panels and agent JSON render the classified errors.
- [track-temporal-integration.md](track-temporal-integration.md) — uses `is_retryable` to drive Temporal's `non_retryable` flag.
