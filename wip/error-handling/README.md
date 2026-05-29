# Error Handling — Current State and Open Tracks

This directory is the current-state reference for error handling across Pipelex. It is intentionally **track-organized**, not phase-organized: each track is a self-contained concern with its own current state, gaps, and followups. Tracks are independent — there is no implied order between them.

Each `track-*.md` describes **what the code does today**. Completed implementation plans are archived (see [Archived plans](#archived-plans) below) and kept only for their running notes. What is still open is summarized in [What's still open](#whats-still-open).

## Status at a glance

| Track | Status | Doc |
|---|---|---|
| Error metadata model | Landed for all inference workers — inference errors self-describe via `to_error_report()`, and every LLM, img-gen, extract, and search worker raise carries structured `ProviderErrorMetadata` (status_code, request_id, retry_after_seconds, provider_error_code, body) plus `UserAction(kind, detail)` with semantic `UserActionKind` values. `InferenceErrorCategory.UNKNOWN` distinguishes unrecognized fallback paths from genuine `CONTENT`. Each worker family fills `model` / `provider` onto the error at its public-method chokepoint via `CogtError.fill_model_and_provider()`, so a production inference failure's `ErrorReport` is attributable to a model and a backend. A long tail of non-inference `PipelexError` subclasses still depend on string-keyed dicts in `agent_output.py` — see [track-metadata-model.md](track-metadata-model.md) Followups. | [track-metadata-model.md](track-metadata-model.md) |
| Worker classification | Landed for all inference workers — every LLM, img-gen, extract, and search worker (plus AWS Bedrock LLM) maps SDK exceptions to a `CogtError` subclass with `error_category`, unwraps `InstructorRetryException` correctly on structured-gen paths, and carries the structured metadata + semantic user-action upgrades. Response-shape validation failures (non-SDK paths) carry `provider_metadata=None` plus a semantic `UserAction` for uniformity. | [track-worker-classification.md](track-worker-classification.md) |
| Extract / Classify / Render | Landed (branch `refactor/ECR`) — every inference worker's `except` block now collapses to `extract → classify → raise render(...) from exc`. **Classify** (`pipelex/cogt/inference/error_classify.py`) and **Render** (`error_render.py`) are single shared functions; only the 12 `extract_*_metadata` functions stay per-provider. A new `tests/unit/pipelex/cogt/inference/test_provider_classification_parity.py` walks every `ProviderName` against the extract-fn registry to catch unwired providers. | [track-extract-classify-render.md](track-extract-classify-render.md) |
| Retry & resilience | Landed — direct (non-Temporal) execution is a single pipeline-level attempt with no application-level retry loop; resilience is the Temporal track's job (activity `RetryPolicy` keyed off `InferenceErrorCategory`). `PipeBatch` bounds fan-out via `gather_bounded` (chunked, `max_concurrency`, default 8) — admission control, not retry. Tier 1 (transport retry) is an explicit, uniform policy: `cogt.transport_max_retries` is wired into every inference SDK client factory, the SDK-less `azure_rest` image-gen path has a `tenacity` transport-retry floor, and `instructor`'s structured-output retry is confined to schema re-ask. | [track-retry-and-resilience.md](track-retry-and-resilience.md) |
| CLI delivery | Landed — agent CLI emits markdown by default for `run`/`validate`/`init` (and `models`/`check-model`/`doctor`), `--format json` for the structured payload; the error path follows the same option via a per-invocation `ContextVar`. `ErrorReport` carries an authoritative `error_domain` → HTTP-status mapping. `display_error_panel` collapses the field-shaped Rich handlers onto one helper. | [track-cli-delivery.md](track-cli-delivery.md) |
| Temporal integration | Landed — `TemporalError.from_message_exception()` derives retryability from `InferenceErrorCategory.is_retryable` for category-carrying `CogtError`s (the `non_retryable_error_types` list is the fallback) and packs the full `ErrorReport` into `ApplicationError.details`. Every in-scope activity is decorated with `@convert_pipelex_errors`, so the bridge runs in production. The symmetric workflow → submitter and child-workflow → parent recovery is landed: `recover_error_report` reads the report back out of `ApplicationError.details`, so a pipe failing on a Temporal worker reaches the CLI and HTTP adapters with the same classification as a local run. | [track-temporal-integration.md](track-temporal-integration.md) |
| Testing | Landed — worker-level classification tests, the `agent_output.py` dict-drift test, and the full-chain worker→runner→CLI integration test (JSON + markdown) plus Rich-panel snapshot tests are all in place. | [track-testing.md](track-testing.md) |
| API readiness (error-handling companion) | Stages 1-4 landed (PR #931) — `PipelexError.title()` / `type_uri()`, `request_id` on `JobMetadata`, `DisclosureMode` with `to_dict(disclosure_mode=)` / `to_problem_document()`, total `recover_error_report`, `ErrorReport` as a `BaseModel` threaded to the webhook, and per-class error doc pages. Stage 5 (webhook signing) is the last open item; the post-#931 `/review` follow-ups landed 2026-05-22 as TODOS Phases 1-4 — see [What's still open](#whats-still-open). | [api-companion-revisions.md](api-companion-revisions.md) |

Architectural reference (layer model, class hierarchy, two reporting systems) lives in [architecture.md](architecture.md).

## What's still open

The bulk of the error-handling work has landed. What remains:

1. **Webhook signing (Stage 5 / Item F)** — the last unshipped stage of the API-readiness companion plan. Cross-repo: the pipelex side and the API side land in lockstep. Authoritative plan: [../security/webhook-signing.md](../security/webhook-signing.md).
2. **Metadata-model long tail** — a handful of `CogtError` subclasses still carry no class-level `error_category`, and several non-inference `PipelexError` subclasses still depend on the `agent_output.py` fallback dicts for `hint` / `error_domain` rather than carrying class-level metadata. See the Followups in [track-metadata-model.md](track-metadata-model.md).

All four post-#931 `/review` follow-ups landed 2026-05-22 as Phases 1-4 of the archived `feature/API-readiness-2` ledger (`archive-todos-api-readiness-2.md`, moved to workspace `docs/history/error-handling/`): the STRICT-disclosure INPUT-domain gap (Phase 1 — see [track-strict-disclosure-input-domain-gap.md](archive/track-strict-disclosure-input-domain-gap.md)), the `request_id` log wiring (Phase 2), the webhook-payload reserved-key collision (Phase 3 — see `track-webhook-payload-collision.md`, also in workspace history), and the test-coverage backfill (Phase 4). Item 1, webhook signing, is the original plan's final stage — a separate cross-repo track that lands on its own schedule (the archived ledger's Phase 5). Item 2 is an independent long tail. Everything else is landed and described in current-state terms in the track docs below. Optional, non-blocking review notes — observations that were deliberately not acted on, each with a conditional trigger for when to revisit — are preserved in workspace `docs/history/error-handling/`.

## Suggested read order

Tracks are independent for implementation purposes, but there is a natural onramp for someone reading the directory cold:

1. [architecture.md](architecture.md) — the layer model, class hierarchy, and `ErrorReport` shape that every track refers back to.
2. [track-metadata-model.md](track-metadata-model.md) — the data contract (`error_category`, `error_domain`, `user_action`) everything downstream consumes.
3. [track-worker-classification.md](track-worker-classification.md) — Layer 0 → 1, where errors originate and pick up their category.
4. [track-extract-classify-render.md](track-extract-classify-render.md) — landed refactor: decomposes the per-worker pipeline into one shared `extract → classify → render` chain.
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

Each `track-*.md` opens with **what this track is** (the concern in one paragraph) and a **current state** section — what is true in the code today, with verified file paths. A track with unfinished work then has an **open gaps** / **what's left** section and concrete **followups**; a fully-landed track says so explicitly. Every doc closes with **related tracks** cross-references. The docs describe the current state, not the history of how it got there — that history lives in the archived plans below.

## Archived plans

This directory replaces a set of phase-numbered docs (`error-handling-review.md`, `error-handling-phase-{0..7}-*.md`, `worker-error-handling-review.md`, `instructor-unwrap-other-workers.md`) that mixed historical progress with current state. The phase framing was useful when the work was sequenced; it is not useful as a reference for the current state and for planning what's next.

Completed sweeps and plans are archived here, kept for their running notes and checkpoint history. They describe *what was done*, not the current state — the `track-*.md` docs above are authoritative for the current state.

- `archive-todos-api-readiness-2.md` (moved to workspace `docs/history/error-handling/`) — the `feature/API-readiness-2` ledger (PRs #931 + #933): post-#931 `/review` follow-ups, the `*_exceptions.py` structural refactor, and the in-repo finalization of the error-handling overhaul.
- [archive-worker-classification-sweep.md](archive/archive-worker-classification-sweep.md) — the worker-classification sweep.
- `archive-extract-classify-render.md` (moved to workspace `docs/history/error-handling/`) — the ECR decomposition (5 checkpoints on `refactor/ECR`), with the key deviations from the original design.
- [archive-error-handling-2.md](archive/archive-error-handling-2.md) — the error-handling Phase 2 sweep (broad-except hygiene, `error_domain` metadata, retry & resilience, Temporal bridge, CLI/HTTP delivery, full-chain coverage).
- `archive-temporal-activity-boundary.md` (moved to workspace `docs/history/error-handling/`) — wiring `from_message_exception` into every in-scope Temporal activity.
- [archive-temporal-submitter-boundary.md](archive/archive-temporal-submitter-boundary.md) — recovering the structured `ErrorReport` on the workflow → submitter and child-workflow → parent boundaries.
- [archive-retry-and-resilience.md](archive/archive-retry-and-resilience.md) — the retry-and-resilience plan: remove the `PipeRouter` transient-retry loop and make Tier 1 transport retry explicit and uniform.
- [archive-llm-retry-loop-bypass.md](archive-llm-retry-loop-bypass.md) — a fix so transient LLM failures reached the (then-existing) `PipeRouter` retry loop; superseded when that loop was removed.
- [archive-retry-graph-trace.md](archive/archive-retry-graph-trace.md) — a phantom-error-node graph bug; resolved by removing the retry loop that caused it.
