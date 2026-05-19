# Deferred — img-gen "model not found" specialization

**Surfaced during:** the LLM worker error-classification refactor on `feature/Temporal-merge-3` — extracting `classify_{anthropic,google,mistral}_sdk_error` into `pipelex/plugins/*/*_error_classification.py` and promoting an HTTP 404 to the dedicated `LLMModelNotFoundError`. Related track: [track-worker-classification.md](../track-worker-classification.md).

The LLM workers now raise the dedicated `LLMModelNotFoundError` (a `ModelNotFoundError` subclass) on an HTTP 404 instead of a generic `LLMCompletionError`. The image-generation workers should do the equivalent — raise `ImgGenModelNotFoundError` on a 404 instead of generic `ImgGenGenerationError`. The type already exists (`pipelex/cogt/exceptions.py`: `ImgGenModelNotFoundError(ModelNotFoundError)`, an empty subclass) with the same constructor as `LLMModelNotFoundError`. This was held back from the LLM follow-up as a deliberate scope boundary.

This is a type-precision change, not a behavior change — **zero downstream blast radius**. Nothing catches or branches on `ImgGenModelNotFoundError` vs `ImgGenGenerationError`; retry, the Temporal error bridge, and CLI rendering all key off `error_category`, and `ImgGenModelNotFoundError` inherits `error_category = CONFIGURATION` from `ModelNotFoundError`. The 404 branches already emit `UserActionKind.CHANGE_MODEL`. (To re-confirm before starting: `grep -rn ImgGenModelNotFoundError pipelex/` should show it raised only by the two OpenAI img-gen workers and caught nowhere outside tests.)

## Current state

The two OpenAI img-gen workers already raise `ImgGenModelNotFoundError` on a 404 — they are the in-repo reference. The remaining img-gen workers still raise generic `ImgGenGenerationError`, or (Gateway) never special-case a 404 at all.

| Worker | Classifier method | 404 today |
|---|---|---|
| `openai/openai_img_gen_worker.py` | `_raise_categorized_openai_sdk_error` (raises) | already `ImgGenModelNotFoundError` |
| `openai/openai_completions_img_gen_worker.py` | `_raise_categorized_openai_sdk_error` (raises) | already `ImgGenModelNotFoundError` |
| `google/google_img_gen_worker.py` | `_classify_google_client_error` (returns) | generic `ImgGenGenerationError`, in an `if status_code == 404` branch |
| `fal/fal_img_gen_worker.py` | `_raise_categorized_fal_http_error` (raises) | generic `ImgGenGenerationError`, in an `if status_code == 404` branch |
| `azure_rest/azure_img_gen_worker.py` | `_raise_categorized_azure_status_error` (raises) | generic `ImgGenGenerationError`, in an `if status_code == 404` branch |
| `huggingface/huggingface_img_gen_worker.py` | `_raise_categorized_hf_http_error` (raises) | generic `ImgGenGenerationError`, in an `if status_code == 404` branch |
| `gateway/gateway_img_gen_worker.py` | none — delegates to `GatewayFactory.classify_error_category()` | no 404 branch |

## Reference implementation — the target shape

`openai_img_gen_worker.py::_raise_categorized_openai_sdk_error` already does this correctly. Its 404 branch is the shape every img-gen worker's 404 should produce — copy it:

```python
if isinstance(sdk_exc, NotFoundError):
    msg = f"ImgGen model or deployment not found: {self.inference_model.desc}: {sdk_exc}"
    raise ImgGenModelNotFoundError(
        message=msg,
        model_handle=self.inference_model.name,
        error_category=InferenceErrorCategory.CONFIGURATION,
        user_action=UserAction(
            kind=UserActionKind.CHANGE_MODEL,
            detail=f"Model '{self.inference_model.model_id}' was not found — pick an available model",
        ),
        provider_metadata=metadata,
    ) from sdk_exc
```

The key constructor difference vs `ImgGenGenerationError`: `ImgGenModelNotFoundError` (via `ModelNotFoundError.__init__`) takes `message=` as a keyword and **requires** a `model_handle` argument. `ImgGenGenerationError` takes the message positionally and has no `model_handle`.

## Scope

### Worker changes — Google, FAL, Azure, HuggingFace

Each already has an `if status_code == 404:` branch raising/returning `ImgGenGenerationError` with `error_category=CONFIGURATION` and `UserActionKind.CHANGE_MODEL`. The change is identical in all four — only the constructed type and its argument form. Example, `fal_img_gen_worker.py`:

Before:

```python
if status_code == 404:
    msg = f"FAL model not found for '{self.inference_model.desc}': {exc}"
    raise ImgGenGenerationError(
        msg,
        error_category=InferenceErrorCategory.CONFIGURATION,
        user_action=UserAction(
            kind=UserActionKind.CHANGE_MODEL,
            detail=f"Model '{self.inference_model.model_id}' was not found — pick an available model",
        ),
        provider_metadata=metadata,
    ) from exc
```

After:

```python
if status_code == 404:
    msg = f"FAL model not found for '{self.inference_model.desc}': {exc}"
    raise ImgGenModelNotFoundError(
        message=msg,
        model_handle=self.inference_model.name,
        error_category=InferenceErrorCategory.CONFIGURATION,
        user_action=UserAction(
            kind=UserActionKind.CHANGE_MODEL,
            detail=f"Model '{self.inference_model.model_id}' was not found — pick an available model",
        ),
        provider_metadata=metadata,
    ) from exc
```

Per worker:

- Add `ImgGenModelNotFoundError` to the existing `from pipelex.cogt.exceptions import ...` line.
- In the 404 branch: `ImgGenGenerationError(msg,` → `ImgGenModelNotFoundError(message=msg, model_handle=self.inference_model.name,`. Leave `error_category`, `user_action`, `provider_metadata`, and the `from exc` chaining unchanged.
- `azure_img_gen_worker.py` is the same change — note its `detail` text says "Deployment" not "Model"; leave that wording as-is.
- `google_img_gen_worker.py` differs only in that `_classify_google_client_error` **returns** the error (`return ImgGenGenerationError(...)` → `return ImgGenModelNotFoundError(...)`). Two extra steps there: widen the method's return annotation from `-> ImgGenGenerationError` to `-> ImgGenGenerationError | ImgGenModelNotFoundError`, and delete the comment in the 404 branch that says the `ImgGenModelNotFoundError` specialization is "intentionally out of scope here" — it ceases to be true.

### Worker change — Gateway

`gateway_img_gen_worker.py` has no 404 branch; it raises a generic `ImgGenGenerationError` assembled from `GatewayFactory` helpers (`make_error_summary_from_portkey_error`, `classify_error_category`, `make_user_action_from_portkey_error`) inside `except portkey_exceptions.APIError as exc:`. Add an explicit 404 check before that generic raise — the Portkey `APIError` exposes `.status_code` (`extract_gateway_metadata` already reads it):

```python
if exc.status_code == 404:
    msg = f"Gateway model not found for '{self.inference_model.desc}': {exc}"
    raise ImgGenModelNotFoundError(
        message=msg,
        model_handle=self.inference_model.name,
        error_category=InferenceErrorCategory.CONFIGURATION,
        user_action=UserAction(
            kind=UserActionKind.CHANGE_MODEL,
            detail=f"Model '{self.inference_model.model_id}' was not found — pick an available model",
        ),
        provider_metadata=extract_gateway_metadata(exc),
    ) from exc
```

This is the one item that is a new branch rather than a type swap. Consider placing the 404 detection in `GatewayFactory` so a future Gateway-side fix can reuse it.

### Tests

The pattern to copy is `tests/unit/pipelex/plugins/openai/test_openai_img_gen_worker_error_handling.py`, which already has a `404 → ImgGenModelNotFoundError` test (constructs an SDK exception, drives `_gen_image`, asserts `pytest.raises(ImgGenModelNotFoundError)`, `error_category is CONFIGURATION`, `user_action.kind is CHANGE_MODEL`).

- `tests/unit/pipelex/plugins/google/test_google_img_gen_worker_error_handling.py` — its 404 test asserts `ImgGenGenerationError`; flip it to `ImgGenModelNotFoundError` (the test fails until updated).
- `tests/unit/pipelex/plugins/azure_rest/test_azure_img_gen_worker_error_handling.py` — exists but has no 404 case; add one.
- FAL, HuggingFace, and Gateway img-gen have no error-handling test file (only `_semantic` tests) — add a new `test_<provider>_img_gen_worker_error_handling.py` for each with a `404 → ImgGenModelNotFoundError` test. This also closes a pre-existing gap: those workers' error categorization is currently untested.
- The two OpenAI img-gen workers already test `404 → ImgGenModelNotFoundError`; no change.

Unlike the LLM follow-up, there are no extracted img-gen classifier modules and therefore no `classify_*` free functions to unit-test in isolation — worker-level error-handling tests are the full coverage.

## Verification

From the repo root (`_tprl/`):

- `make agent-check` — ruff + pyright + mypy. Watch for: a pyright return-type error on `google_img_gen_worker._classify_google_client_error` if its annotation was not widened (step above); and unused-import if `ImgGenModelNotFoundError` was imported into a worker but the branch edit was missed.
- Targeted tests (per [../../../tests/CLAUDE.md](../../../tests/CLAUDE.md), source area `pipelex/plugins/`):

  ```bash
  .venv/bin/pytest -n auto \
    -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" \
    -o log_level=WARNING --tb=short -q \
    tests/unit/pipelex/plugins/ tests/integration/pipelex/plugins/
  ```

Expect zero failures once the Google 404 test is flipped; the worker error-handling tests are mock-based (no real inference) so they run under the marker filter above.

## Effort & risk

Roughly one sitting. The type-swap workers (Google, FAL, Azure, HuggingFace) are mechanical; only Gateway needs a new branch. The bulk of the work is the new FAL / HuggingFace / Gateway error-handling test files. Risk is low: zero behavioral blast radius (see the intro), and the OpenAI img-gen workers already demonstrate the target shape.

## Explicitly not in this scope

- **Structural extraction.** The img-gen workers still classify errors via inline `_raise_categorized_*` instance methods that *raise* directly (and `google_img_gen_worker._classify_google_client_error` *returns*, inconsistent even within img-gen). They never received the LLM side's refactor into `classify_*` free functions that *return* a categorized error. Bringing img-gen to that structure is a separate, larger consistency pass, and is not required for the `ImgGenModelNotFoundError` specialization.
- **Remaining LLM workers.** The LLM model-not-found specialization now covers the OpenAI, Anthropic, Google, and Mistral LLM workers. Any LLM worker outside that set — notably AWS Bedrock LLM (`pipelex/plugins/bedrock/bedrock_llm_worker.py`) — has not been audited for whether it specializes a 404. A quick parallel check, separate from this img-gen follow-up.

## Affected files

Workers:

- `pipelex/plugins/google/google_img_gen_worker.py`
- `pipelex/plugins/fal/fal_img_gen_worker.py`
- `pipelex/plugins/azure_rest/azure_img_gen_worker.py`
- `pipelex/plugins/huggingface/huggingface_img_gen_worker.py`
- `pipelex/plugins/gateway/gateway_img_gen_worker.py` (and possibly `pipelex/plugins/gateway/gateway_factory.py`)

Tests:

- `tests/unit/pipelex/plugins/google/test_google_img_gen_worker_error_handling.py`
- `tests/unit/pipelex/plugins/azure_rest/test_azure_img_gen_worker_error_handling.py`
- new error-handling test files for the FAL, HuggingFace, and Gateway img-gen workers under `tests/unit/pipelex/plugins/{fal,huggingface,gateway}/`

Reference (no change): `pipelex/plugins/openai/openai_img_gen_worker.py`, `pipelex/plugins/openai/openai_completions_img_gen_worker.py`, `pipelex/cogt/exceptions.py`.
