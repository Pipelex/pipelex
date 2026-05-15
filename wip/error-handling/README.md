# Error Handling — Current State and Open Tracks

This directory is the current-state reference for error handling across Pipelex. It is intentionally **track-organized**, not phase-organized: each track is a self-contained concern with its own current state, gaps, and followups. Tracks are independent — there is no implied order between them.

The improvement plan lives elsewhere; the docs here describe the ground that any improvement plan must stand on.

## Status at a glance

| Track | Status | Doc |
|---|---|---|
| Error metadata model | Landed for all inference workers — inference errors self-describe via `to_error_report()`, and every LLM, img-gen, extract, and search worker raise carries structured `ProviderErrorMetadata` (status_code, request_id, retry_after_seconds, provider_error_code, body) plus `UserAction(kind, detail)` with semantic `UserActionKind` values. `InferenceErrorCategory.UNKNOWN` distinguishes unrecognized fallback paths from genuine `CONTENT`. Non-inference paths still depend on string-keyed dicts in `agent_output.py`. | [track-metadata-model.md](track-metadata-model.md) |
| Worker classification | Landed for all inference workers — every LLM, img-gen, extract, and search worker (plus AWS Bedrock LLM) maps SDK exceptions to a `CogtError` subclass with `error_category`, unwraps `InstructorRetryException` correctly on structured-gen paths, and carries the structured metadata + semantic user-action upgrades. Response-shape validation failures (non-SDK paths) carry `provider_metadata=None` plus a semantic `UserAction` for uniformity. | [track-worker-classification.md](track-worker-classification.md) |
| Extract / Classify / Render | Proposed (not started) — decomposes the per-worker pipeline into one per-provider Extract function + shared Classify + shared Render. Cuts duplication across 18+ workers. The worker-classification sweep it depended on has landed, so it is now unblocked. | [track-extract-classify-render.md](track-extract-classify-render.md) |
| Retry & resilience | Open — retry lives inside two gateway workers via `tenacity` (`gateway_extract_worker`, `gateway_search_worker`). `PipeRouter` has no retry loop yet. | [track-retry-and-resilience.md](track-retry-and-resilience.md) |
| CLI delivery | Partially landed — human CLI uses Rich and `to_error_report()`; agent CLI emits JSON. Markdown-default for `run`/`validate`/`init` and the error path is not yet implemented. Eleven near-identical handlers in `error_handlers.py` still duplicate the same Rich shape. | [track-cli-delivery.md](track-cli-delivery.md) |
| Temporal integration | Open — `TemporalError.from_message_exception()` uses the static `non_retryable_error_types` config list; it does not consult `InferenceErrorCategory.is_retryable`. No `ApplicationError.details` payload yet. | [track-temporal-integration.md](track-temporal-integration.md) |
| Testing | Partially landed — worker-level classification tests are comprehensive; full-chain runner→CLI→JSON snapshot and dict-drift detection are missing. | [track-testing.md](track-testing.md) |

Architectural reference (layer model, class hierarchy, two reporting systems) lives in [architecture.md](architecture.md).

## Suggested read order

Tracks are independent for implementation purposes, but there is a natural onramp for someone reading the directory cold:

1. [architecture.md](architecture.md) — the layer model, class hierarchy, and `ErrorReport` shape that every track refers back to.
2. [track-metadata-model.md](track-metadata-model.md) — the data contract (`error_category`, `error_domain`, `user_action`) everything downstream consumes.
3. [track-worker-classification.md](track-worker-classification.md) — Layer 0 → 1, where errors originate and pick up their category.
4. [track-extract-classify-render.md](track-extract-classify-render.md) — proposed refactor, now unblocked by the landed worker-classification sweep; decomposes the per-worker pipeline.
5. [track-cli-delivery.md](track-cli-delivery.md) — Layer 4 → 5, where the classified errors get rendered for humans and agents.
6. [track-retry-and-resilience.md](track-retry-and-resilience.md) — builds on classification and metadata to drive retry decisions.
7. [track-temporal-integration.md](track-temporal-integration.md) — extends the same model across the activity → workflow boundary.
8. [track-testing.md](track-testing.md) — cross-cutting, comes last because it verifies the others.

This is reading order, not implementation order — any track can be picked up independently.

## Cross-cutting principles (what's already true)

These are honored across the codebase today and the tracks below build on them:

- **Single-rooted hierarchy.** Every custom exception inherits from `pipelex.base_exceptions.PipelexError`. `ToolError` (`pipelex/system/exceptions.py`) is folded under it.
- **`msg = "..."; raise XError(msg) from exc`.** Message before raise; `from exc` everywhere a re-raise happens.
- **No bare `except` and no broad `except Exception` in business logic.** Broad catches only at CLI entry points and async task root handlers.
- **Workers transform SDK errors into domain errors.** Every inference worker catches the SDK's typed exceptions, attaches an `InferenceErrorCategory`, and chains the original via `from exc`.
- **`ErrorReport` is the single serialization schema.** `pipelex/base_exceptions.py` defines it; `PipelexError.to_error_report()` is the entry point; CLI JSON, Rich panels, and Temporal details all draw from it.

## Conventions used in track docs

Each `track-*.md` follows the same shape:

1. **What this track is** — the concern in one paragraph.
2. **Current state** — what is true in the code today, with verified file paths.
3. **Open gaps** — what's not done yet, restated as concerns (not phase items).
4. **Followups** — specific work items lifted from prior plans, descoped from any phase numbering.
5. **Related tracks** — cross-references.

## Historical note

This directory replaces a set of phase-numbered docs (`error-handling-review.md`, `error-handling-phase-{0..7}-*.md`, `worker-error-handling-review.md`, `instructor-unwrap-other-workers.md`) that mixed historical progress with current state. The phase framing was useful when the work was sequenced; it is not useful as a reference for the current state and for planning what's next.
