# Generalize the `InstructorRetryException` unwrap fix to the other LLM workers

> Drafted: 2026-05-03
> Predecessor: the Anthropic `_gen_object` fix on `refactor/Inference-error-handling`
> ([CHANGELOG entry](../CHANGELOG.md#unreleased)).

## Background — what we just fixed in Anthropic

`AnthropicLLMWorker._gen_object` runs requests through `instructor`. When the
underlying Anthropic SDK raises an exception (`RateLimitError`,
`APITimeoutError`, `APIConnectionError`, `BadRequestError`,
`PermissionDeniedError`, `AuthenticationError`), `instructor`'s tenacity-driven
retry loop catches it, exhausts retries, and re-raises wrapped in
`InstructorRetryException` with the original exception parked at
`exc.failed_attempts[-1].exception` (and reachable via
`exc.__cause__.last_attempt._exception` as a tenacity fallback).

The handler we inherited matched only the bare SDK types and treated
`InstructorRetryException` as a content/validation failure
(`InferenceErrorCategory.CONTENT`, non-retryable). End result: every quota
exhaustion, network blip, auth failure, or rate-limit on the structured-gen
path was mis-categorized as a content failure. Retry policy never kicked in,
billing / config remediation hints never fired, the user got a wall of
"content failed" for what was really an ops/transient problem.

Fix landed in `pipelex/plugins/anthropic/anthropic_llm_worker.py`:

- `_extract_underlying_sdk_exception(instructor_exc)` — recovers the SDK
  exception (`failed_attempts[-1].exception`, fallback to
  `__cause__.last_attempt._exception`).
- `_raise_categorized_anthropic_sdk_error(sdk_exc, chain_from=None)` — single
  source of truth for SDK→pipelex categorization, shared between `_gen_text`
  and `_gen_object`.
- `_gen_object` `InstructorRetryException` branch unwraps and routes through
  the helper; truly unrecognized inner exceptions (e.g. `pydantic.ValidationError`
  from a schema mismatch) keep the original `CONTENT` fallback.

End-to-end test in
`tests/unit/pipelex/plugins/anthropic/test_anthropic_worker_object_error_handling.py::test_real_instructor_wraps_rate_limit_and_fix_unwraps_correctly`
locks in the assumption against a real `instructor.from_anthropic(...)` so
this can't silently rot if `instructor`'s wrapping shape changes.

## Same bug, four more workers

Every LLM worker that uses `instructor.from_*` and a separate top-level catch
for SDK exceptions has the same defect. Empirically confirmed for OpenAI:

```text
openai: instructor.core.exceptions.InstructorRetryException, fa[0]=RateLimitError
```

(Same one-shot script used to prove the Anthropic case — a real
`instructor.from_openai` driving an `AsyncOpenAI` whose
`chat.completions.create` raises `openai.RateLimitError` produces the wrapped
shape.) Mistral and Google are structurally identical: they call
`instructor.from_mistral` / `instructor.from_genai`, then catch the bare SDK
exception types separately. Only the SDK-exception class names differ.

### Per-worker damage report

| Worker | File | SDK types currently caught | Behavior on wrapped SDK error today | Fix shape |
|---|---|---|---|---|
| OpenAI Completions | `pipelex/plugins/openai/openai_completions_llm_worker.py:215-285` | `NotFoundError`, `RateLimitError`, `APITimeoutError`, `APIConnectionError`, `BadRequestError`, `AuthenticationError` | All flatten to `CONTENT`. `is_quota_exhaustion_openai` / `is_content_policy_violation` discriminators never run. | Same as Anthropic: extract helper + unwrap branch. Almost mechanical port. |
| OpenAI Responses | `pipelex/plugins/openai/openai_responses_llm_worker.py:195-263` | Same six as above, plus `LLMModelNotFoundError` from `NotFoundError` | Same flattening. Note: `InstructorRetryException` clause is currently *first* in the except chain, but that doesn't matter — the order didn't cause the bug, the wrapping did. | Same as Anthropic. Keep the `LLMModelNotFoundError` / `model_handle` plumbing in the helper for the `NotFoundError` branch. |
| Mistral | `pipelex/plugins/mistral/mistral_llm_worker.py:208-238` | `MistralError` (single base class) routed through `_classify_mistral_error` | Wrapped `MistralError` → `CONTENT`; the existing `_classify_mistral_error` (which already discriminates by status code / message) never runs. | Smaller change: unwrap, and if the underlying is a `MistralError`, call `_classify_mistral_error` from inside the unwrap branch. |
| Google Gemini | `pipelex/plugins/google/google_llm_worker.py:283-320` | `genai_errors.ServerError` (→ `TRANSIENT`), `genai_errors.ClientError` (→ `_classify_google_client_error`) | Wrapped `ServerError` (which would have been `TRANSIENT`) → `CONTENT`. Wrapped `ClientError` → `CONTENT`. The same kind of category collapse. | Same as Mistral: unwrap, dispatch by `isinstance(underlying, ServerError | ClientError)`, fall back to `CONTENT`. |

`pipelex/plugins/anthropic/anthropic_llm_worker.py` is now the reference; the
other four should converge on the same shape.

## Recommended approach

Two viable shapes. Pick one and apply consistently.

### Option A — replicate per-worker (safe, repetitive)

For each of the four workers above, mirror the Anthropic change:

1. Extract the categorization logic into `_raise_categorized_<provider>_sdk_error(sdk_exc, chain_from=None)`. Refactor `_gen_text` (or the equivalent text-gen path) to use it so the fix doesn't bifurcate logic.
2. Add `_extract_underlying_sdk_exception(instructor_exc)` (identical across workers — copy-paste is fine for this round).
3. In the `InstructorRetryException` branch of `_gen_object`, call the extractor; if it returns one of the recognized SDK types, route through the helper with `chain_from=instructor_exc`; otherwise keep the existing `CONTENT` fallback.

Pro: smallest possible diff per worker; no cross-cutting refactor; failure of one fix doesn't impact others.
Con: ~50 lines of identical extractor code in five places.

### Option B — share the extractor

`_extract_underlying_sdk_exception` is provider-agnostic (it only reads
attributes that `InstructorRetryException` and tenacity always populate). It
can move to `pipelex/cogt/inference/error_classification.py` (next to
`is_quota_exhaustion_*` / `is_content_policy_violation`) and be imported by
every worker. The categorization helper stays per-worker because the SDK
exception types differ.

Pro: removes duplication; one place to fix if `instructor` ever changes the
attribute name.
Con: one extra dependency edge across workers; needs a small unit test for
the shared helper covering both the `failed_attempts` path and the
`__cause__.last_attempt._exception` fallback.

**Recommendation: Option B.** The function is twelve lines and has nothing
provider-specific in it. Putting it in `error_classification` matches what we
already do for the message-pattern discriminators.

## Per-worker recipe

### OpenAI Completions (`openai_completions_llm_worker.py`)

Mirror Anthropic almost verbatim. The OpenAI exception classes have identical
constructor shapes to Anthropic's (httpx-based), so the test fixtures port
over directly.

- The `_gen_object` body has a nested `try { try { ... } except InstructorRetryException }` already. Collapse to a single try; replace the inner with the unwrap-and-dispatch branch; replace the outer six SDK clauses with a single tuple-catch that delegates to the helper.
- Be careful with `NotFoundError`: it should keep going to `LLMCompletionError(error_category=CONFIGURATION)` to match `_gen_text`'s behavior.

### OpenAI Responses (`openai_responses_llm_worker.py`)

Same pattern as Completions, but the `NotFoundError` branch raises a more
specialized `LLMModelNotFoundError(message=msg, model_handle=...)`. Keep that
specialization inside the categorization helper — it's a real signal worth
preserving for callers that want to swap models.

### Mistral (`mistral_llm_worker.py`)

`_classify_mistral_error` is doing the right work — it just never gets called
on the wrapped path. Two-line fix in the `InstructorRetryException` branch:

```python
except InstructorRetryException as instructor_exc:
    underlying = _extract_underlying_sdk_exception(instructor_exc)
    if isinstance(underlying, MistralError):
        raise self._classify_mistral_error(underlying) from instructor_exc
    msg = f"Mistral structured generation failed after retries for model '{self.inference_model.desc}': {instructor_exc}"
    raise LLMCompletionError(msg, error_category=InferenceErrorCategory.CONTENT) from instructor_exc
```

(`_classify_mistral_error` returns the `LLMCompletionError` to raise — match
its existing call shape.)

### Google Gemini (`google_llm_worker.py`)

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

## Test plan

Mirror `tests/unit/pipelex/plugins/anthropic/test_anthropic_worker_object_error_handling.py` for each provider. The structure is reusable; only the SDK-exception
factories and the patched helper paths change.

### Shared test pieces (worth lifting into a shared helper module)

- `_wrap_in_instructor_retry(sdk_exc, *, include_failed_attempts=True)` — builds an `InstructorRetryException` matching what real instructor produces. Already in the Anthropic test file; could move to `tests/helpers/instructor_test_utils.py` for reuse.
- `_DummySchema(BaseModel)` — minimal pydantic model passed as `response_model`.
- A `_make_llm_job(mocker)` skeleton — already provider-agnostic.

### Per-worker cases to cover

For each of OpenAI Completions, OpenAI Responses, Mistral, Google:

| Case | What it proves |
|---|---|
| Wrapped rate-limit (or provider equivalent) → `TRANSIENT` | The unwrap branch routes to the rate-limit handler. |
| Wrapped quota-exhaustion message → `CAPACITY` + billing `user_action` | `is_quota_exhaustion_*` discriminator runs after unwrap. |
| Wrapped timeout → `TRANSIENT` | Confirms timeout types unwrap. |
| Wrapped connection error → `TRANSIENT` | Confirms network errors unwrap. |
| Wrapped content-policy bad-request → `CONTENT` + safety `user_action` | `is_content_policy_violation` discriminator runs after unwrap. |
| Wrapped auth error → `CONFIGURATION` (or provider-specific credentials exception) | Auth still routes correctly. |
| Wrapped `ValueError` (non-SDK) → `CONTENT` fallback | Genuine schema/validation failures stay as `CONTENT`. |
| Real-instructor end-to-end (one per provider) | Locks in instructor's actual wrapping shape so a future instructor upgrade fails loudly here, not in production. |

Provider-specific notes:

- **OpenAI Completions / Responses** can construct exceptions identically to Anthropic via `httpx.Response(status_code=..., request=...)`. The end-to-end test uses `instructor.from_openai(openai.AsyncOpenAI(api_key="fake"))` and patches `client.chat.completions.create` (Completions) or `client.responses.create` (Responses) with `mocker.AsyncMock(side_effect=sdk_exc)`.
- **Mistral**'s `MistralError` constructor differs across versions — confirm the kwargs in the installed `mistralai` before writing factories. The end-to-end test patches `mistralai.Mistral.chat.complete_async` (or whatever the current `from_mistral` adapter calls).
- **Google**'s `genai_errors.ServerError` / `ClientError` take a different constructor — they wrap an HTTP response object. Look at how `_classify_google_client_error` already constructs them in tests (if any) before writing factories. The end-to-end test patches the `genai.Client.aio.models.generate_content`-equivalent that `instructor.from_genai` calls.

If the Mistral / Google constructor shapes are awkward, prefer the
construct-by-hand pattern (`_wrap_in_instructor_retry(real_sdk_exc)`) for the
seven categorization cases and keep only the real-instructor end-to-end test
provider-specific.

## Risks and gotchas

- **`instructor` import path.** Anthropic's fix already moved from `instructor.exceptions` to `instructor.core` (the former is deprecated and slated for removal). Do the same in the four other workers while you're in the file — same one-line change, frees us from the deprecation warning across the suite.
- **`MistralError` and the Mistral `_classify_mistral_error` helper expect a *raw* `MistralError`,** not the wrapped one. Confirm the helper doesn't introspect attributes that the wrapped exception lacks. Same for `_classify_google_client_error`.
- **`from instructor_exc` chaining.** In every fix, `chain_from=instructor_exc` so the traceback shows `instructor → tenacity → SDK`. Don't chain from the bare SDK exc — it loses the retry context that's useful for debugging.
- **Tests that hit real instructor + AsyncMock'd SDK calls** are slightly slow (~0.5s each on Anthropic) because instructor still does its full attempt loop. Keep one such test per provider, not one per case.
- **`pydantic.ValidationError` is a legitimate `CONTENT` failure.** When the LLM returns JSON that doesn't match the schema, instructor raises `InstructorRetryException` with a `ValidationError` (or `JSONDecodeError`) at `failed_attempts[-1].exception`. The unwrap branch must keep this categorized as `CONTENT` — `_extract_underlying_sdk_exception` returns the `ValidationError`, the helper doesn't recognize it, and we fall through to the existing `CONTENT` fallback. The Anthropic test `test_unrecognized_underlying_falls_back_to_content` covers this. Replicate it everywhere.
- **Don't add a new SDK-exception type silently.** If a provider adds, say, an `InternalServerError`, the helper will return without raising and we fall through to `CONTENT`. That's a pre-existing gap, not a new one — but it's worth a short audit of each provider's SDK exception hierarchy while doing this work.

## Suggested commit shape

Two PRs:

1. **Lift `_extract_underlying_sdk_exception` to `pipelex/cogt/inference/error_classification.py`** (Option B). Update the Anthropic worker to import from the shared location instead of defining it locally. Add unit tests for the shared helper covering both extraction paths. Pure refactor, zero behavior change.
2. **Apply the unwrap-and-dispatch fix to the four remaining workers**, one commit per worker. Each commit includes the worker change + its test file. Keeps blame readable and lets `git revert` rescue any single provider if the fix turns out to have an edge case.

CHANGELOG: one entry per worker fix in `[Unreleased] → Fixed`, mirroring the
Anthropic entry already on the branch.

## Out of scope (call out, don't fix here)

- Other workers that *do not* go through `instructor` (e.g. `bedrock_llm_worker.py`, `mistral_extract_worker.py`) have their own error-handling problems documented in `wip/worker-error-handling-review.md`. Those are separate and shouldn't be bundled with this fix.
- `azure_img_gen_worker.py` raises raw `httpx.HTTPStatusError` — same overall theme (errors not categorized) but nothing to do with `instructor` wrapping.
- Image-gen workers that use `instructor` (none today, AFAIK) would need the same fix if any are added later.
