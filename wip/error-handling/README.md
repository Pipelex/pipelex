# Error Handling — Current State and Open Tracks

This directory is the current-state reference for error handling across Pipelex. It is intentionally **track-organized**, not phase-organized: each track is a self-contained concern with its own current state, gaps, and followups. Tracks are independent — there is no implied order between them.

The improvement plan lives elsewhere; the docs here describe the ground that any improvement plan must stand on.

## Status at a glance

| Track | Status | Doc |
|---|---|---|
| Error metadata model | Landed for all inference workers — inference errors self-describe via `to_error_report()`, and every LLM, img-gen, extract, and search worker raise carries structured `ProviderErrorMetadata` (status_code, request_id, retry_after_seconds, provider_error_code, body) plus `UserAction(kind, detail)` with semantic `UserActionKind` values. `InferenceErrorCategory.UNKNOWN` distinguishes unrecognized fallback paths from genuine `CONTENT`. Non-inference paths still depend on string-keyed dicts in `agent_output.py`. | [track-metadata-model.md](track-metadata-model.md) |
| Worker classification | Landed for all inference workers — every LLM, img-gen, extract, and search worker (plus AWS Bedrock LLM) maps SDK exceptions to a `CogtError` subclass with `error_category`, unwraps `InstructorRetryException` correctly on structured-gen paths, and carries the structured metadata + semantic user-action upgrades. Response-shape validation failures (non-SDK paths) carry `provider_metadata=None` plus a semantic `UserAction` for uniformity. | [track-worker-classification.md](track-worker-classification.md) |
| Extract / Classify / Render | Proposed (not started) — decomposes the per-worker pipeline into one per-provider Extract function + shared Classify + shared Render. Cuts duplication across 18+ workers. The worker-classification sweep it depended on has landed, so it is now unblocked. | [track-extract-classify-render.md](track-extract-classify-render.md) |
| Retry & resilience | Landed — `PipeRouter` retries `TRANSIENT` `CogtError`s with config-driven exponential backoff (`max_transient_retries`, default 3); `PipeBatch` bounds fan-out via `gather_bounded` (chunked, `max_concurrency`, default 8). `tenacity` retry removed from the gateway workers. Known follow-up: `PipeLLM` wraps `LLMCompletionError` into a plain `PipeRunError` before the router sees it, so the router's `except CogtError` retry branch is currently bypassed for the LLM path — see the Phase 8 notes in the archived TODOS. | [track-retry-and-resilience.md](track-retry-and-resilience.md) |
| CLI delivery | Landed — agent CLI emits markdown by default for `run`/`validate`/`init` (and `models`/`check-model`/`doctor`), `--format json` for the structured payload; the error path follows the same option via a per-invocation `ContextVar`. `ErrorReport` carries an authoritative `error_domain` → HTTP-status mapping. `display_error_panel` collapses the field-shaped Rich handlers onto one helper. | [track-cli-delivery.md](track-cli-delivery.md) |
| Temporal integration | Landed — `TemporalError.from_message_exception()` derives retryability from `InferenceErrorCategory.is_retryable` for category-carrying `CogtError`s (the `non_retryable_error_types` list is the fallback) and packs the full `ErrorReport` into `ApplicationError.details`. Known follow-up: `from_message_exception` has no production caller yet — see Followup 5 in the track doc. | [track-temporal-integration.md](track-temporal-integration.md) |
| Testing | Landed — worker-level classification tests, the `agent_output.py` dict-drift test, and the full-chain worker→runner→CLI integration test (JSON + markdown) plus Rich-panel snapshot tests are all in place. | [track-testing.md](track-testing.md) |

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
- **`ErrorReport` is the single serialization schema.** `pipelex/base_exceptions.py` defines it; `PipelexError.to_error_report()` is the entry point; CLI JSON, Rich panels, and Temporal details all draw from it. `to_error_report()` enriches from the `__cause__` chain, so a wrapper exception surfaces the inference metadata (`error_category`, `retryable`, `model`, `provider`) of the underlying `CogtError`.

## Conventions used in track docs

Each `track-*.md` follows the same shape:

1. **What this track is** — the concern in one paragraph.
2. **Current state** — what is true in the code today, with verified file paths.
3. **Open gaps** — what's not done yet, restated as concerns (not phase items).
4. **Followups** — specific work items lifted from prior plans, descoped from any phase numbering.
5. **Related tracks** — cross-references.

## Historical note

This directory replaces a set of phase-numbered docs (`error-handling-review.md`, `error-handling-phase-{0..7}-*.md`, `worker-error-handling-review.md`, `instructor-unwrap-other-workers.md`) that mixed historical progress with current state. The phase framing was useful when the work was sequenced; it is not useful as a reference for the current state and for planning what's next.

Two completed sweeps are archived here, kept for their running notes and checkpoint history:

- [archive-worker-classification-sweep.md](archive-worker-classification-sweep.md) — the worker-classification sweep.
- [archive-error-handling-2.md](archive-error-handling-2.md) — the error-handling Phase 2 sweep (broad-except hygiene, `error_domain` metadata, retry & resilience, Temporal bridge, CLI/HTTP delivery, full-chain coverage).
