# Extract / Classify / Render — as built

**Status: landed.** Every inference worker's `except` block resolves an SDK exception through one shared three-step chain — **extract → classify → render** — instead of hand-coding metadata extraction, categorization, and error construction inline. Only the Extract step is per-provider; Classify and Render are single shared functions.

## How it works

The chain lives in `pipelex/cogt/inference/`:

- **Extract** (per-provider) — `extract_<provider>_metadata(exc) -> ProviderErrorMetadata` in `error_classification.py`, one function per provider. It pulls the structured fields out of the SDK exception — status code, request id, retry-after, provider error code, message, body — into a `ProviderErrorMetadata` (aliased `SDKErrorEnvelope`). This is the only place provider-specific attribute access lives.
- **Classify** (shared, pure) — `classify_inference_error(metadata: SDKErrorEnvelope) -> ClassificationResult` in `error_classify.py`. Provider-agnostic: it maps the envelope — status code, the computed `@property` flags `is_quota_exhaustion` / `is_content_policy_violation` / `is_network_error`, and a status-less-exception-name table — to a `ClassificationResult` carrying `category: InferenceErrorCategory`, `user_action_kind: UserActionKind`, and `is_model_not_found: bool`. Because it reads only the envelope, it is tested against synthetic envelopes with no SDK installed.
- **Render** (shared) — `render_inference_error(metadata, classification, family, model_desc, model_handle) -> CogtError` in `error_render.py`. It builds the concrete `CogtError` subclass selected by the worker `family` (`InferenceErrorFamily`: `LLM` / `IMG_GEN` / `EXTRACT` / `SEARCH`), composes the message and `UserAction`, and attaches the metadata.

A worker `except` block is three lines:

```python
except anthropic.APIError as exc:
    metadata = extract_anthropic_metadata(exc)
    classification = classify_inference_error(metadata)
    raise render_inference_error(
        metadata, classification, InferenceErrorFamily.LLM, self.inference_model.desc, model_handle,
    ) from exc
```

## What this buys

- Adding a provider — or a new SDK exception type — is an Extract-only change; Classify and Render are untouched.
- Classification rules live in one provider-agnostic function, tested exhaustively against synthetic envelopes (no SDK imports).
- Human-facing message formatting lives in one Render function rather than being duplicated per worker.

## Adding a provider

Write one `extract_<provider>_metadata` function in `error_classification.py` and wire it at the worker's `except` site. `tests/unit/pipelex/cogt/inference/test_provider_classification_parity.py` walks every `ProviderName` against the extract-function registry, so a provider added without a wired Extract function fails fast.

## Related tracks

- [track-worker-classification.md](track-worker-classification.md) — where SDK exceptions are caught; the per-worker classification this chain consolidated.
- [track-metadata-model.md](track-metadata-model.md) — the `ProviderErrorMetadata` / `error_category` / `user_action` data contract this chain produces.
- [track-retry-and-resilience.md](track-retry-and-resilience.md) — consumes the uniform `error_category` and `retry_after_seconds` for retry decisions.
- [track-testing.md](track-testing.md) — the provider-blind Classify tests and the cross-provider parity meta-test.
- [track-cli-delivery.md](track-cli-delivery.md) — Render is the single place human-facing message formatting is shaped.
