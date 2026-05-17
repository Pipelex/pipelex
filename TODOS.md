# TODOS

No open work items. This branch (`feature/Error-handling-2`, branched from `feature/Temporal-merge-3`) is the error-handling overhaul — what follows is a guide for reviewing it.

## Reviewing this branch

The current-state reference is **`wip/error-handling/`**. Start with [`wip/error-handling/README.md`](wip/error-handling/README.md): its status table and suggested read order map every track to its doc and say what landed vs. what is still only proposed.

Each track is a self-contained concern. Suggested review path:

1. [`architecture.md`](wip/error-handling/architecture.md) — layer model, exception hierarchy, `ErrorReport` shape. Read first; every track refers back to it.
2. [`track-metadata-model.md`](wip/error-handling/track-metadata-model.md) — the data contract: `error_category`, `error_domain`, `user_action`, `ProviderErrorMetadata`. Key files: `pipelex/base_exceptions.py`, `pipelex/cogt/exceptions.py`.
3. [`track-worker-classification.md`](wip/error-handling/track-worker-classification.md) — SDK → domain error mapping in every inference worker. Key files: `pipelex/plugins/*/`, `pipelex/cogt/inference/error_classification.py`, `pipelex/plugins/openai/openai_error_classification.py`.
4. [`track-retry-and-resilience.md`](wip/error-handling/track-retry-and-resilience.md) — explicit transport retry, removal of the `PipeRouter` retry loop, bounded `PipeBatch` fan-out. Key files: `pipelex/cogt/inference/transport_retry.py`, `pipelex/cogt/llm/instructor_retry.py`, `pipelex/pipe_controllers/batch/pipe_batch.py`, `pipelex/tools/misc/async_utils.py`.
5. [`track-cli-delivery.md`](wip/error-handling/track-cli-delivery.md) — markdown/JSON agent-CLI delivery, `error_domain` → HTTP-status mapping. Key files: `pipelex/cli/agent_cli/commands/agent_output.py`, `pipelex/cli/error_handlers.py`.
6. [`track-temporal-integration.md`](wip/error-handling/track-temporal-integration.md) — `ErrorReport` carried across the activity → workflow → submitter boundary. Key files: `pipelex/temporal/tprl/temporal_error.py`, `pipelex/temporal/tprl/activity_error_boundary.py`, `pipelex/temporal/tprl/workflow_caller.py`.
7. [`track-testing.md`](wip/error-handling/track-testing.md) — cross-cutting; verifies the rest.

## What is intentionally left open

So these are not flagged as missing during review:

- **Extract / Classify / Render decomposition** — a proposed, not-started refactor; out of scope for this branch. See [`track-extract-classify-render.md`](wip/error-handling/track-extract-classify-render.md).
- **Metadata-model long tail** — a few non-inference `PipelexError` subclasses still rely on the `agent_output.py` fallback dicts for `hint` / `error_domain` instead of class-level metadata. See the Followups in [`track-metadata-model.md`](wip/error-handling/track-metadata-model.md).
- Optional, non-blocking review followups are collected in [`wip/error-handling/deferred-items/`](wip/error-handling/deferred-items/).

Completed plans are archived under `wip/error-handling/archive-*.md` — kept for their running notes, not authoritative for the current state.
