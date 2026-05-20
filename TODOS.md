# TODOS

No open work items. This branch (`refactor/ECR`, branched from `feature/Temporal-merge-3` via `feature/Error-handling-2`) is the Extract / Classify / Render decomposition — the final sweep of the error-handling overhaul. What follows is a guide for reviewing it.

## Reviewing this branch

The current-state reference is **`wip/error-handling/`**. Start with [`wip/error-handling/README.md`](wip/error-handling/README.md): its status table and suggested read order map every track to its doc and say what landed vs. what is still only proposed. For the shipped, user-facing version of the same material, see [`docs/under-the-hood/error-model.md`](docs/under-the-hood/error-model.md) — including its "The Uniform Shape — Extract / Classify / Render" section.

This branch is scoped to the ECR refactor. The single most relevant doc is:

- [`wip/error-handling/track-extract-classify-render.md`](wip/error-handling/track-extract-classify-render.md) — what the post-refactor code looks like, plus the design motivation that led to it.
- [`wip/error-handling/archive-extract-classify-render.md`](wip/error-handling/archive-extract-classify-render.md) — checkpoint history and the key deviations from the original design (e.g. why Classify + Render live in their own modules, why `is_quota_exhaustion` is checked early, why Azure ImgGen keeps two `AMBIGUOUS` branches).

The rest of the error-handling tracks are unchanged on this branch but provide context:

1. [`architecture.md`](wip/error-handling/architecture.md) — layer model, exception hierarchy, `ErrorReport` shape. Read first; every track refers back to it.
2. [`track-metadata-model.md`](wip/error-handling/track-metadata-model.md) — the data contract: `error_category`, `error_domain`, `user_action`, `ProviderErrorMetadata` (the type now aliased as `SDKErrorEnvelope` in ECR signatures). Key files: `pipelex/base_exceptions.py`, `pipelex/cogt/exceptions.py`.
3. [`track-worker-classification.md`](wip/error-handling/track-worker-classification.md) — the per-worker classification sweep that ECR consolidates. Key files: `pipelex/plugins/*/*_worker.py`.
4. [`track-retry-and-resilience.md`](wip/error-handling/track-retry-and-resilience.md) — explicit transport retry, removal of the `PipeRouter` retry loop, bounded `PipeBatch` fan-out.
5. [`track-cli-delivery.md`](wip/error-handling/track-cli-delivery.md) — markdown/JSON agent-CLI delivery, `error_domain` → HTTP-status mapping.
6. [`track-temporal-integration.md`](wip/error-handling/track-temporal-integration.md) — `ErrorReport` carried across the activity → workflow → submitter boundary.
7. [`track-testing.md`](wip/error-handling/track-testing.md) — cross-cutting; verifies the rest.

## Where the changes are

Production code:

- `pipelex/cogt/inference/error_classify.py`, `error_render.py`, `provider_name.py` — new modules. Classify is one pure, provider-blind function; Render picks the `CogtError` subclass from `InferenceErrorFamily` + the `is_model_not_found` flag.
- `pipelex/cogt/inference/error_classification.py` — `ProviderErrorMetadata` gains `message` + three `@property` accessors (`is_quota_exhaustion`, `is_content_policy_violation`, `is_network_error`). 12 `extract_*_metadata` functions updated to populate `message`. `_AWS_ERROR_CODE_TO_STATUS` map added for Bedrock.
- 6 LLM workers (`anthropic`, `openai_completions`, `openai_responses`, `mistral`, `google`, `bedrock`) — every `except` block collapsed to `extract → classify → raise render(...) from exc`.
- 7 img-gen workers (`openai`, `openai_completions_img_gen`, `fal`, `huggingface`, `google_img_gen`, `gateway_img_gen`, `azure_rest`) — same migration. Azure keeps two worker-specific `AMBIGUOUS` branches; see the key deviations in the archive.
- 7 extract + search workers (`mistral`, `linkup` x2, `gateway` x2, `docling`, `pypdfium2`) — same migration. Mistral + gateway-search now specialize HTTP 404 to `ExtractModelNotFoundError` / `SearchModelNotFoundError`.
- Deleted: 4 per-provider `*_error_classification.py` files (+ matching tests), `AnthropicCredentialsError`, `GatewayFactory.classify_error_category` / `make_user_action_from_portkey_error` / `make_error_summary_from_portkey_error`, and every inline `_classify_*_error` / `_raise_categorized_*` instance method that the workers used to carry.

Tests:

- `tests/unit/pipelex/cogt/inference/test_classify_inference_error.py` — provider-blind parity matrix (synthesized envelopes → expected category + user-action kind).
- `tests/unit/pipelex/cogt/inference/test_render_inference_error.py` — render correctness against synthetic envelopes + classifications.
- `tests/unit/pipelex/cogt/inference/test_provider_classification_parity.py` — meta-test that walks every `ProviderName` against the extract-fn registry and the worker-family map, so adding a new provider without wiring it fails fast.
- Per-worker classification tests were updated to the new three-line shape; most categorization assertions have moved to the parity matrix.

## What is intentionally left open

So these are not flagged as missing during review:

- **Metadata-model long tail** — a few non-inference `PipelexError` subclasses still rely on the `agent_output.py` fallback dicts for `hint` / `error_domain` instead of class-level metadata. Pre-existing; see the Followups in [`track-metadata-model.md`](wip/error-handling/track-metadata-model.md). Out of scope for ECR.
- Optional, non-blocking review notes from earlier error-handling sweeps (Temporal activity boundary, Phase 12 search workers) are collected in [`wip/error-handling/review-notes/`](wip/error-handling/review-notes/). Each entry is a deliberate non-fix recorded with a conditional trigger for when to revisit. None are ECR regressions; ECR has if anything reduced their surface by routing the same code paths through the shared parity matrix.

Completed plans are archived under `wip/error-handling/archive-*.md` — kept for their running notes, not authoritative for the current state. The ECR archive ([`archive-extract-classify-render.md`](wip/error-handling/archive-extract-classify-render.md)) is the new one this branch adds.
