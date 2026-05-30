# Post-tidy code fixes — forward plan

> Surfaced by the `_docs/wip/` documentation tidy (see [`../TODOS.md`](../TODOS.md) for the completed tidy record). These are the *runtime code* follow-ups the tidy verified as real but did not act on. They change `pipelex/` (not docs), so they need `make agent-check` + tests and a fresh branch off `main` — **not** the docs-only `docs/Tidy` branch this tidy ran on.

## Branch & gate — read before starting

- **Branch:** create a fresh branch off `main` from the parent pipelex checkout at `/Users/lchoquel/repos/Pipelex/pipelex/` — do **not** write runtime code on the `docs/Tidy` worktree.
- **Per-fix gate:** `make agent-check`, then the targeted tests for the touched area (see `tests/CLAUDE.md` source→test mapping).
- **Before any push:** full `make agent-test`.
- Verdict evidence for both items is in [`../BUG-VERIFICATION.md`](../BUG-VERIFICATION.md); the consolidated deferred backlog is in [`../DEFERRED-BACKLOG.md`](../DEFERRED-BACKLOG.md).

## Fixes

### 4a — `request_id` on delivery failure messages (`[REAL]`, low, S)

Append the already-in-scope `request_id_suffix` to the `StorageDeliveryError` failure message and to both `WebhookDeliveryError` branches in `pipelex/pipe_run/delivery_executor.py`, mirroring the success paths; add unit assertions that the messages carry `request_id=`. Full analysis — exact sites, the case for/against, and a sketch commit — lives in the track doc: [`error-handling/track-delivery-error-path-request-id.md`](error-handling/track-delivery-error-path-request-id.md).

### 4b — cross-worker cost report assembly wiring (`[REAL]`, medium, M)

The single genuine functional gap from the tracing work: wire `UsageAggregator.aggregate(events)` → `ReportingManager.inject_tokens_usages(...)` → `generate_report` into the post-run readback, parallel to the existing graph readback, for both direct mode (`pipe_run/pipe_run.py` / `graph_assembly.py`) and Temporal (`act_assemble_graph` / post-workflow). Add a cross-worker test. This is its own scoped piece of work — consider a dedicated plan. Tracked as **P1** in [`02-master-plan.md`](02-master-plan.md); the as-built context and the open T2/T3 gaps are in [`tracing-cost-reporting-as-built.md`](tracing-cost-reporting-as-built.md).

## Deferred / out of scope — pick up individually if prioritized

Consolidated in [`../DEFERRED-BACKLOG.md`](../DEFERRED-BACKLOG.md) and the per-topic deferred indexes ([`deferred-items.md`](deferred-items.md), [`text-then-object/deferred-items.md`](text-then-object/deferred-items.md)):

- `[REAL]` GraphSpec causal ordering for parent/child topologies (medium, observability-only).
- `[REAL]` kajson class-registry race under pytest-xdist (low, test-hygiene; needs runtime repro).
- `[REAL — deferred]` `get_config()` replay-determinism — the cheap parts (a `docs/distributed-execution` note on the config-edit-while-in-flight constraint, plus a Replayer regression test) are file-able; the full fix is Worker Versioning (large).
- Pre-existing broken links in the relocated historical archive docs (the absolute-style `wip/...`-from-inside-`wip/` pattern, and wrong relative paths in the master-plan archives). These left `wip/` when the finished archive docs were retired; optional sweep, not introduced by this cleanup.
