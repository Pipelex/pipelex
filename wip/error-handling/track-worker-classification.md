# Track — Worker Classification

## What this track is

Every inference worker that calls a third-party SDK must catch the SDK's typed exceptions and re-raise a `CogtError` subclass with an `InferenceErrorCategory`, a `user_action` hint, the model descriptor in the message, and `from exc` to preserve the cause chain. This is the foundation that everything downstream depends on — retry policy, agent hints, Temporal `non_retryable` decisions, human Rich panels.

The work to lift every worker to this standard **has landed**. One residual defect remains: structured generation through `instructor` wraps the SDK exception in `InstructorRetryException`, and only the Anthropic worker currently unwraps it. OpenAI Completions, OpenAI Responses, Mistral, and Google still mis-categorize wrapped errors as `CONTENT`.

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
| Azure img-gen | `pipelex/plugins/azure/azure_img_gen_worker.py` |
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

### Anthropic `instructor` unwrap (the reference fix)

`pipelex/plugins/anthropic/anthropic_llm_worker.py` defines:

- `_extract_underlying_sdk_exception(instructor_exc)` — recovers the SDK exception from `failed_attempts[-1].exception`, falling back to `__cause__.last_attempt._exception` (tenacity's storage).
- `_raise_categorized_anthropic_sdk_error(sdk_exc, chain_from=None)` — single classification helper shared between `_gen_text` and `_gen_object`.
- `_gen_object`'s `InstructorRetryException` branch unwraps and routes through the helper; only truly unrecognized inner exceptions (e.g. `pydantic.ValidationError` from a schema mismatch) keep the `CONTENT` fallback.

The end-to-end test `tests/unit/pipelex/plugins/anthropic/test_anthropic_worker_object_error_handling.py::test_real_instructor_wraps_rate_limit_and_fix_unwraps_correctly` locks in the assumption against real `instructor.from_anthropic(...)`.

## Open gaps

### Instructor unwrap missing on four other workers

Every LLM worker that uses `instructor.from_*` and a separate top-level catch for SDK exceptions has the same defect: structured-gen failures (rate limit, timeout, auth, quota) wrap as `InstructorRetryException` and get mis-categorized as `CONTENT`.

| Worker | File | Current SDK types caught directly | Behavior on wrapped error |
|---|---|---|---|
| OpenAI Completions | `pipelex/plugins/openai/openai_completions_llm_worker.py` | `NotFoundError`, `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `BadRequestError`, `AuthenticationError` | All flatten to `CONTENT`; the quota / content-policy discriminators never run on the wrapped path. |
| OpenAI Responses | `pipelex/plugins/openai/openai_responses_llm_worker.py` | Same six, plus `LLMModelNotFoundError` from `NotFoundError` | Same flattening; `LLMModelNotFoundError`/`model_handle` plumbing only fires on the unwrapped path. |
| Mistral | `pipelex/plugins/mistral/mistral_llm_worker.py` | `MistralError` routed through `_classify_mistral_error` | Wrapped `MistralError` → `CONTENT`; `_classify_mistral_error` (which already discriminates by status code / message) never runs on the wrapped path. |
| Google Gemini | `pipelex/plugins/google/google_llm_worker.py` | `genai_errors.ServerError` → `TRANSIENT`, `genai_errors.ClientError` → `_classify_google_client_error` | Wrapped `ServerError` (should be `TRANSIENT`) → `CONTENT`. Wrapped `ClientError` → `CONTENT`. |

### Other small gaps

- **`pydantic.ValidationError` as a legitimate `CONTENT`.** When the LLM returns JSON that doesn't match the schema, `instructor` raises `InstructorRetryException` with a `ValidationError` (or `JSONDecodeError`) at `failed_attempts[-1].exception`. The unwrap branch must preserve this categorization — `_extract_underlying_sdk_exception` returns the `ValidationError`, the SDK helper doesn't recognize it, and the existing `CONTENT` fallback kicks in. The Anthropic test `test_unrecognized_underlying_falls_back_to_content` covers this and must be replicated.
- **Silent gaps if a provider adds a new SDK exception type.** If, say, OpenAI introduces an `InternalServerError`, the categorization helper returns without raising and falls through to `CONTENT`. Worth a short audit of each provider's SDK exception hierarchy while doing the unwrap work.
- **`instructor` import path.** The Anthropic worker moved from `instructor.exceptions` to `instructor.core` (the former is deprecated). The four pending workers should do the same one-line change.

## Followups

### 1. Lift `_extract_underlying_sdk_exception` to a shared module

The function is small and provider-agnostic — it only reads attributes that `InstructorRetryException` and tenacity always populate. Move it to `pipelex/cogt/inference/error_classification.py` (next to the discriminators) and have every worker import from there. Anthropic switches to the shared import. Pure refactor, zero behavior change.

Tests for the shared helper cover both the `failed_attempts` path and the `__cause__.last_attempt._exception` fallback.

### 2. Apply unwrap-and-dispatch to OpenAI Completions

Mirror the Anthropic shape. The OpenAI exception classes have identical constructor shapes to Anthropic's (httpx-based), so the test fixtures port over directly. The current `_gen_object` body has a nested `try { try { ... } except InstructorRetryException }` — collapse to a single try; replace the inner with the unwrap-and-dispatch branch; replace the six SDK clauses with a single tuple-catch that delegates to the helper. Keep `NotFoundError → LLMCompletionError(error_category=CONFIGURATION)` to match `_gen_text`.

### 3. Apply unwrap-and-dispatch to OpenAI Responses

Same pattern as Completions, but the `NotFoundError` branch raises a more specialized `LLMModelNotFoundError(message=msg, model_handle=...)`. Keep that specialization inside the categorization helper — it's a real signal worth preserving for callers that want to swap models.

### 4. Apply unwrap-and-dispatch to Mistral

Smallest change of the four — `_classify_mistral_error` is doing the right work, it just never gets called on the wrapped path:

```python
except InstructorRetryException as instructor_exc:
    underlying = _extract_underlying_sdk_exception(instructor_exc)
    if isinstance(underlying, MistralError):
        raise self._classify_mistral_error(underlying) from instructor_exc
    msg = f"Mistral structured generation failed after retries for model '{self.inference_model.desc}': {instructor_exc}"
    raise LLMCompletionError(msg, error_category=InferenceErrorCategory.CONTENT) from instructor_exc
```

### 5. Apply unwrap-and-dispatch to Google Gemini

Symmetric to Mistral:

```python
except InstructorRetryException as instructor_exc:
    underlying = _extract_underlying_sdk_exception(instructor_exc)
    if isinstance(underlying, genai_errors.ServerError):
        msg = f"Google API server error for model '{self.inference_model.desc}': {underlying}"
        raise LLMCompletionError(msg, error_category=InferenceErrorCategory.TRANSIENT) from instructor_exc
    if isinstance(underlying, genai_errors.ClientError):
        raise self._classify_google_client_error(underlying) from instructor_exc
    msg = f"Google structured generation failed after retries for model '{self.inference_model.desc}': {instructor_exc}"
    raise LLMCompletionError(msg, error_category=InferenceErrorCategory.CONTENT) from instructor_exc
```

### 6. Per-provider test plan

Mirror `tests/unit/pipelex/plugins/anthropic/test_anthropic_worker_object_error_handling.py`. The structure is reusable; only the SDK-exception factories and the patched helper paths change.

**Shared test pieces worth lifting:**

- `_wrap_in_instructor_retry(sdk_exc, *, include_failed_attempts=True)` — builds an `InstructorRetryException` matching what real `instructor` produces. Could move to `tests/helpers/instructor_test_utils.py` for reuse.
- `_DummySchema(BaseModel)` — minimal pydantic model passed as `response_model`.
- A `_make_llm_job(mocker)` skeleton — already provider-agnostic.

**Per-worker cases:**

| Case | What it proves |
|---|---|
| Wrapped rate-limit → `TRANSIENT` | The unwrap branch routes to the rate-limit handler. |
| Wrapped quota-exhaustion message → `CAPACITY` + billing `user_action` | `is_quota_exhaustion_*` runs after unwrap. |
| Wrapped timeout → `TRANSIENT` | Timeout types unwrap. |
| Wrapped connection error → `TRANSIENT` | Network errors unwrap. |
| Wrapped content-policy bad-request → `CONTENT` + safety `user_action` | `is_content_policy_violation` runs after unwrap. |
| Wrapped auth error → `CONFIGURATION` (or provider-specific credentials exception) | Auth still routes correctly. |
| Wrapped `ValueError` (non-SDK) → `CONTENT` fallback | Genuine schema/validation failures stay as `CONTENT`. |
| Real-instructor end-to-end (one per provider) | Locks in `instructor`'s actual wrapping shape so a future upgrade fails loudly here, not in production. |

**Provider-specific notes:**

- **OpenAI Completions / Responses** — construct SDK exceptions identically to Anthropic via `httpx.Response(status_code=..., request=...)`. The end-to-end test uses `instructor.from_openai(openai.AsyncOpenAI(api_key="fake"))` and patches `client.chat.completions.create` (Completions) or `client.responses.create` (Responses) with `mocker.AsyncMock(side_effect=sdk_exc)`.
- **Mistral** — `MistralError` constructor differs across SDK versions; confirm kwargs against the installed `mistralai` before writing factories. The end-to-end test patches `mistralai.Mistral.chat.complete_async` (or the current `from_mistral` adapter call).
- **Google** — `genai_errors.ServerError` / `ClientError` wrap an HTTP response object. Look at how `_classify_google_client_error` constructs them in tests (if any) before writing factories. The end-to-end test patches the `genai.Client.aio.models.generate_content`-equivalent that `instructor.from_genai` calls. If constructor shapes are awkward, prefer `_wrap_in_instructor_retry(real_sdk_exc)` for the seven categorization cases and keep only the real-instructor end-to-end test provider-specific.

### Risks and gotchas

- `_classify_mistral_error` and `_classify_google_client_error` expect a raw SDK exception, not the wrapped one. Confirm the helpers don't introspect attributes the wrapped exception lacks.
- Chain via `from instructor_exc` so the traceback shows `instructor → tenacity → SDK`. Don't chain from the bare SDK exc — it loses retry context useful for debugging.
- Real-instructor + AsyncMock'd SDK tests are slightly slow (~0.5s each) because `instructor` still does its full attempt loop. Keep one such test per provider, not one per case.

## Related tracks

- [track-metadata-model.md](track-metadata-model.md) — the `error_category` / `user_action` contract the classified errors fill in.
- [track-retry-and-resilience.md](track-retry-and-resilience.md) — once workers correctly classify TRANSIENT vs CAPACITY, the router-level retry can act on those signals.
- [track-cli-delivery.md](track-cli-delivery.md) — how Rich panels and agent JSON render the classified errors.
- [track-temporal-integration.md](track-temporal-integration.md) — uses `is_retryable` to drive Temporal's `non_retryable` flag.

## Historical snapshot (2026-04-05)

Before Phases 0–3, a tier review classified every worker as Tier 1 (gold standard), Tier 2 (partial coverage), or Tier 3 (minimal / no error handling). At the time, Google, Mistral (LLM + extract), Azure img-gen, FAL, HuggingFace, Docling, Linkup, and pypdfium2 had no SDK exception handling at all. Phases 2 and 3 closed those gaps and the tier ranking no longer reflects current reality — every worker is at the Tier 1 standard except for the residual `instructor` unwrap on OpenAI / Mistral / Google. This historical detail is preserved here so the "what motivated this work" context isn't lost.
