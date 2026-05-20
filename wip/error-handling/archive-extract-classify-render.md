# Archive — Extract / Classify / Render (ECR) Decomposition

> **Archived 2026-05-20.** This is the completed ECR refactor — all 5 checkpoints landed on branch `refactor/ECR`. It is kept for the running notes, checkpoint table, and the key design deviations, which have reference value when reading the post-refactor code.

> **Source of truth (current state):** [track-extract-classify-render.md](track-extract-classify-render.md).
> **Original plan with full per-checkpoint notes:** [`~/.claude/plans/ok-let-s-do-ecr-reflective-dahl.md`](file:///Users/lchoquel/.claude/plans/ok-let-s-do-ecr-reflective-dahl.md) (local-only, not in repo).
> **Implementation references:** `pipelex/cogt/inference/error_classify.py`, `pipelex/cogt/inference/error_render.py`, `pipelex/cogt/inference/error_classification.py`, `pipelex/cogt/inference/provider_name.py`.
> **Parity meta-test:** `tests/unit/pipelex/cogt/inference/test_provider_classification_parity.py`.

---

## Checkpoint summary

| CP | Scope | Landed in |
|---|---|---|
| 1 | New `provider_name.py`, `error_classify.py`, `error_render.py`; `ProviderErrorMetadata` gains `message` + three `@property` accessors (`is_quota_exhaustion`, `is_content_policy_violation`, `is_network_error`); 12 `extract_*` functions updated to populate `message`. | `6c9415de` |
| 2 | 6 LLM workers migrated (`anthropic`, `openai_completions`, `openai_responses`, `mistral`, `google`, `bedrock`); bedrock instance-method classifier deleted. | `6c9415de` |
| 3 | 7 img-gen workers migrated (`openai`, `openai_completions_img_gen`, `fal`, `huggingface`, `azure_rest`, `google`, `gateway`). Azure keeps two `AMBIGUOUS` branches (non-idempotent 5xx + post-flight transport errors). Statusless map gains `MissingCredentialsError` + `FalClientError`. | `6c9415de` |
| 4 | 7 extract + search workers migrated (`mistral`, `linkup` x2, `gateway` x2, `docling`, `pypdfium2`). All `_classify_*_error` instance methods + inline `GatewayFactory.*_from_portkey_error` calls deleted from worker bodies. Statusless map gains the remaining Linkup typed exceptions. Mistral + gateway-search now specialize HTTP 404 to `ExtractModelNotFoundError` / `SearchModelNotFoundError`. | `9c7a6ee1` |
| 5 | Deleted the per-provider `*_error_classification.py` files (+ matching tests) and `AnthropicCredentialsError`. Deleted `GatewayFactory.classify_error_category` / `make_user_action_from_portkey_error` / `make_error_summary_from_portkey_error` and their direct tests. Privatized quota helpers (`_is_quota_exhaustion_*`, `_is_content_policy_violation`) and rewrote `test_error_classification.py` to exercise the public `ProviderErrorMetadata` properties. New parity meta-test (`test_provider_classification_parity.py`) walks every `ProviderName` against the extract-fn registry. | `aaf6acdf` |

---

## Key deviations from the original design

These are the design decisions that diverged from what was sketched in [track-extract-classify-render.md](track-extract-classify-render.md). They are recorded here because the post-refactor code reflects them, and a future reader of the track doc should not be surprised.

1. **Classify + Render live in new modules, not `error_classification.py`.** `exceptions.py` already imports `error_classification.py`, so putting `classify_inference_error` (which needs `InferenceErrorCategory` from `exceptions.py`) into the same module would create a circular import. Resolution: `error_classify.py` (Classify) and `error_render.py` (Render) are separate modules. Import DAG: `error_classification` → `exceptions` → `error_classify` → `error_render`.
2. **`ProviderErrorMetadata.message` defaults to `""`**, not required. A required field would break ~35 existing direct test constructions for no gain; all 12 `extract_*` functions populate it; the CP5 parity meta-test asserts population.
3. **`classify_inference_error` checks `is_quota_exhaustion` early** (right after the statusless branch, before the per-status branches). Reason: AWS surfaces quota exhaustion at HTTP 400, not 429 — a pure status ladder would misclassify it. The `is_quota_exhaustion` property is the quota authority.
4. **`extract_bedrock_metadata` derives HTTP status from the AWS error code** (via `_AWS_ERROR_CODE_TO_STATUS`) when `ResponseMetadata.HTTPStatusCode` is absent. Bedrock's canonical signal is the error-code string; this is legitimate Extract-layer normalization (same spirit as Google's `code` → `status_code`).
5. **`_classify_statusless` is provider-aware.** Two maps: `_STATUSLESS_BY_TYPE_NAME` (global — pydantic `ValidationError`, uniquely-named Linkup typed exceptions, FAL `MissingCredentialsError` / `FalClientError`) and `_LOCAL_EXTRACT_BY_TYPE_NAME` (builtins `FileNotFoundError` / `ValueError` / `RuntimeError` / `OSError`, applied only when `metadata.provider.is_local_file_extractor`). A bare `ValueError` from an SDK provider → `UNKNOWN`; from docling / pypdfium2 → `CONTENT`.
6. **HTTP 422 → CONFIGURATION** (unrecognized-4xx bucket), not `CONTENT` — matches the pre-refactor per-provider behavior. Only HTTP 400 → `CONTENT`.
7. **`SDKErrorEnvelope` is a real `TypeAlias` of `ProviderErrorMetadata`** rather than a renamed class. The shape was already correct; aliasing keeps the existing tests and call sites intact while signaling the Extract → Classify → Render role at the type-annotation level.
8. **`UserAction.detail` text is now provider-agnostic** (e.g. "Transient provider error — the system will retry automatically" rather than "Rate limited by OpenAI — …"). This is an intended ECR trade-off; the provider name still lives in `provider_metadata` and in the rendered message.
9. **Azure ImgGen keeps two `AMBIGUOUS` branches** outside the shared classifier — non-idempotent 5xx (server reached, may have generated and billed) and post-flight `httpx` transport errors (`ReadTimeout` / `WriteTimeout` / generic `TransportError`). These encode operation idempotency, not error nature, so they cannot be expressed in the provider-blind Classify. Pre-flight transport (`ConnectError` / `ConnectTimeout` / `PoolTimeout`) still routes through ECR (`TRANSIENT`). The dual-path lives in `_raise_categorized_azure_status_error` (4xx → ECR; 5xx → AMBIGUOUS) plus per-clause `except` blocks in `_gen_image_list`. No equivalent for FAL because `fal_client` submits async to a queue first; a 5xx during submit is pre-acceptance.
10. **`AnthropicCredentialsError` deletion deferred from CP2 to CP5.** CP2 stopped the anthropic worker from raising it (auth → generic `LLMCompletionError` with `CONFIGURATION` + `CHECK_CREDENTIALS`); the class and the four `classify_*_sdk_error` files still existed and were deleted in CP5 once nothing referenced them.
11. **Gateway-search SDK-error path raises `SearchJobFailureError` (or `SearchModelNotFoundError`)** instead of `GatewaySearchResponseError`. `GatewaySearchResponseError` is kept for the downstream parsing errors in `_extract_content` where it remains the right class — those are not SDK errors.

---

## Net code impact

Cleanup numbers from CP5: -1605 / +45 lines (across deletions of per-provider classifier files, dead Portkey helpers, and the matching test files; partially offset by the new parity meta-test).

Worker `except` blocks now all share the same three-line shape:

```python
metadata = extract_<provider>_metadata(sdk_exc)
classification = classify_inference_error(metadata)
raise render_inference_error(
    metadata=metadata,
    classification=classification,
    family=InferenceErrorFamily.<X>,
    model_desc=self.inference_model.desc,
    model_handle=self.inference_model.name,
) from sdk_exc
```

Adding a provider now requires only one new `extract_*_metadata` function plus a `ProviderName` enum value; the Classify and Render code does not move. The parity meta-test fails fast if a provider is added without an extract-fn entry.
