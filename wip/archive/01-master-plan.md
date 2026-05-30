# Master Plan v2 — Next Phases (Distributed Execution)

> **Status**: Live plan — drives the remaining LibraryCrate / distributed-execution work
> **Last refreshed**: 2026-05-04
> **Predecessor**: [archive/00-master-plan.md](archive/00-master-plan.md) — Phases 0–5 + E2E coverage, all shipped.

This file tracks the **distributed execution** work that follows the LibraryCrate refactor. Worker error-handling work lives in its own files (see "Sibling work streams" below).

---

## What's left

| Item | Status | Why we still need it |
|---|---|---|
| **Phase 6a — Local cross-package dependencies in crate** | Not started | Today the crate only ships the main package's blueprints; cross-package deps still resolve via PIPELEXPATH on the worker. Removing this is the prerequisite to truly stateless workers. |
| **Phase 6b — Remote (GitHub) dependencies** | Not started | Builds on 6a; lets the crate carry deps fetched from remote addresses so workers don't need any package pre-installed. |

## Recently shipped (since 00-master-plan)

| Item | What actually shipped |
|---|---|
| **Phase 4.5 Step 6 — Cross-process tracing** | Shipped via `feature/dynamodb-tracer`, but with a different design than the originally proposed `TracingActivityInboundInterceptor`. See "Phase 4.5 Step 6 — as built" below. |

Open architectural notes and known limitations live in [deferred-items.md](../deferred-items.md). Long-term direction in [future-crate-first-architecture.md](../crate-architecture/future-crate-first-architecture.md). Tracing background (pre-implementation analysis — decisions superseded) in [distributed-tracing-and-reporting.md](distributed-tracing-and-reporting.md).

---

## Phase 4.5 Step 6 — as built

The original Step 6 plan called for a `TracingActivityInboundInterceptor` to set up an NDJSON event log per standalone activity. The team picked a different design:

- **Pluggable backends behind `EventLogProtocol`** — `pipelex/tracing/event_log_protocol.py`. Implementations:
  - `NdjsonEventLog` — local file backend (`pipelex/tracing/ndjson_event_log.py`).
  - `DynamoDBEventLog` — cloud backend (`pipelex/tracing/dynamodb_event_log.py`), schema compatible with `pipelex-api-infra`'s `TraceEventDynamoDBAdapter`. Available behind `pip install "pipelex[dynamodb]"`.
  - `BufferingEventLog` — in-memory buffer used **inside** Temporal workflow code (`pipelex/tracing/buffering_event_log.py`). Synchronous I/O is forbidden in workflow context, so workflows buffer here and flush via an activity.
  - `InMemoryEventLog` — for tests.
  - Backend chosen at runtime via `make_event_log(tracing_config)` in `pipelex/tracing/event_log_factory.py` (`TracingBackend.NDJSON | DYNAMODB | TEMPORAL_DYNAMODB`).
- **Workflow → activity flush, not interceptor.** `WfPipeRouter.run()` (`pipelex/temporal/tprl_pipe/wf_pipe_router.py`) wires a `BufferingEventLog` into the per-workflow `GraphTracerManager` and into the `ReportingManager` via `set_event_log(context_key=workflow_id, ...)`. After pipe execution, buffered events are drained and persisted by `act_flush_trace_events` (`pipelex/temporal/tprl_pipe/act_flush_trace_events.py`), which runs the synchronous boto3 / file writes off the workflow thread.
- **Per-context keying** — `ReportingManager` holds a dict of `_event_log_contexts` keyed by `graph_context.lookup_key`, so concurrent workflows don't trample each other.
- **Direct mode unchanged** — `pipeline_run_setup.py:282` calls the same `set_event_log` path, so the same `EventLogProtocol` machinery runs in-process for non-Temporal execution.

Trade-off vs the original interceptor design: this approach does not capture usage events emitted from activities running in a **separate worker process** that doesn't share the workflow's `ReportingManager`. In the current deployment shape (workflows + activities on the same Worker bundle) this is a non-issue. If we ever split activities onto standalone Workers, the interceptor pattern from the old plan becomes the natural extension — at that point reopen this as a follow-up.

Pre-implementation analysis (proposed SQLite/Redis backends, decision gates, etc.) is in [distributed-tracing-and-reporting.md](distributed-tracing-and-reporting.md), kept as historical context.

---

## Phase 6: Cross-Package Dependencies in Crate

> **Status**: Not started

**Goal**: Include cross-package dependency content in the LibraryCrate so that Temporal workers can execute pipelines that reference concepts and pipes from other packages — without those packages being installed on the worker. Then extend to remote dependencies fetched from GitHub.

See [future-crate-first-architecture.md](../crate-architecture/future-crate-first-architecture.md) for the full crate-first architectural vision and design rationale.

### Why

Today, cross-package dependencies (`alias->domain.ConceptCode`, `alias::domain.pipe_code`) resolve through child library lookups at loading time. The `LibraryCrate` shipped to Temporal workers does NOT include dependency content — only the main package's blueprints. This means workers must have all dependency packages pre-installed on PIPELEXPATH. Phase 6 removes this requirement: the crate becomes truly self-contained.

### Phase 6a: Local Cross-Package Dependencies

**Goal**: Dependency blueprints are included in the crate. Workers can execute pipelines with cross-package deps without having the dependency packages installed.

**Key changes**:

1. **Extract blueprint collector from `_load_single_dependency`**: Split the current method into two parts:
   - **Collect**: resolve the dependency, parse its `.mthds` files into blueprints, determine exports
   - **Load**: create child Library, load domains/concepts/pipes, register aliases
   The collector produces blueprints that accumulate into `_blueprints[library_id]` alongside the main package's blueprints.

2. **Resolve cross-package aliases in the flattened crate**: Cross-package refs use alias-based syntax (`alias->domain.ConceptCode`). In a flattened crate, there are no child libraries. Options:
   - Resolve aliases during crate building (replace `alias->domain.ConceptCode` with `domain.ConceptCode` in all blueprints)
   - Carry alias mappings in the crate (`aliases: dict[str, str]`) for runtime resolution
   Decision TBD when starting implementation.

3. **Update `load_from_crate()`**: Handle dependency content in the flat crate — register domains, concepts, and pipes from deps.

**Done when**:

- [ ] `_load_single_dependency` split into collect + load
- [ ] Dependency blueprints accumulate into `_blueprints[library_id]`
- [ ] `get_crate()` produces a crate that includes dependency content
- [ ] Cross-package aliases resolved (either at crate build time or via alias map)
- [ ] `load_from_crate()` handles dependency content correctly
- [ ] Integration test: PipeSequence referencing a cross-package concept/pipe, executed on Temporal worker without the dependency package on PIPELEXPATH
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes

### Phase 6b: Remote Dependencies (GitHub)

**Goal**: Dependencies can be fetched from remote addresses (e.g., `github.com/org/repo/package`). The crate becomes fully self-contained for cloud-native execution where workers are stateless.

**Key changes**:

1. **Remote resolution strategy**: Add a `REMOTE` resolution strategy to the blueprint collector extracted in 6a. Remote fetch clones/downloads the package from GitHub, parses its `.mthds` files into blueprints, and includes them in the collection.

2. **Dependency address format**: Define the address format for remote deps (e.g., `github.com/org/repo@version/path/to/package`). The address goes in the package manifest.

3. **Caching**: Cache fetched packages locally (content-addressed by address + version) to avoid redundant clones.

4. **Transitive deps**: Remote packages may themselves have dependencies (local or remote). The collector recurses.

**Done when**:

- [ ] Remote fetch strategy implemented (git clone or archive download)
- [ ] Dependency address format defined and parsed
- [ ] Remote package blueprints included in crate
- [ ] Local cache for fetched packages
- [ ] Transitive remote deps resolved
- [ ] Integration test: pipeline with remote dep from a GitHub repo, executed on Temporal worker
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes

---

## Dependencies between remaining items

```
Phase 6a (Local cross-package deps)    ← requires Phase 2's crate propagation (shipped)
    │
    ▼
Phase 6b (Remote deps from GitHub)     ← requires Phase 6a's blueprint collector
```

---

## Sibling work streams (not in this plan)

These tracks are tracked in their own files and ship on their own branches:

| Stream | Files | Branch |
|---|---|---|
| Worker error-handling Phases 4–7 | `error-handling-phase-{4,5,6,7}-*.md`, `error-handling-phases-0-3-completed.md`, `worker-error-handling-review.md`, `error-handling-review.md` | `refactor/Inference-error-handling` |
| Instructor-unwrap port to OpenAI/Mistral/Google workers | `instructor-unwrap-other-workers.md` | (open — Anthropic done, four workers remaining) |
