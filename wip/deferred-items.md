# Deferred & Future Items

> Items explicitly out of scope for the current implementation phases.
> Collected here for roadmap visibility and to preserve design context.

---

## Architectural Direction (Future)

Long-term goals documented for vision alignment. Not planned for implementation now. See [future-crate-first-architecture.md](future-crate-first-architecture.md) for the full design rationale.

### Crate-First Architecture

**Status**: Future vision — Phase 6 is the first step on this path.

Invert the current loading-driven architecture into a crate-driven one with three cleanly separated phases: **Collect** (resolve deps, fetch remote, gather all blueprints) → **Build** (construct one crate, optionally strip to transitive closure) → **Load** (same `load_from_crate()` on submitter and worker).

### Crate Stripping (Transitive Closure)

**Status**: Future — depends on Phase 6a's blueprint collector.

From the entry pipe, walk the transitive closure of pipe and concept dependencies to determine the minimal subset needed. Strip the crate to only those concepts, pipes, and domains. Once all blueprints (main + deps) are accumulated in 6a, stripping is a pure data transform before crate construction.

### Library Fingerprint Validation

**Status**: Future — no immediate need.

Verify that the worker's base library (PIPELEXPATH) matches the API's expectation. Detect version drift between API and worker deployments.

### Cross-Worker Cache via Shared Storage

**Status**: Future — complementary to crate stripping.

Cache loaded crates in shared storage (Redis, S3) so multiple workers don't redundantly load the same crate. Keyed by fingerprint. Smaller crates from stripping make this more effective.

---

## Distributed Tracing — Deferred Items

Items related to the event log and graph tracing system (Phase 4.5). Also documented in [distributed-tracing-and-reporting.md](distributed-tracing-and-reporting.md).

### Event Log Backends

| Item | Status | Context |
|---|---|---|
| DynamoDB backend | **Deferred** — build when deploying to AWS with remote workers | Cloud-only. The `EventLogProtocol` abstraction allows swapping the backend without changing the rest of the system. |
| SQLite backend | **Deferred** — NDJSON is sufficient for local dev | SQLite could replace NDJSON if deduplication at write time or queryability becomes important. |

### Event Log Protocol Extensions

| Item | Status | Context |
|---|---|---|
| `subscribe()` on EventLogProtocol | **Deferred** — no consumer exists yet | Polling-based reads are sufficient for now; add when a real-time consumer exists. |
| Real-time progress consumer | **Deferred** — no consumer exists yet | The protocol supports it; build when needed. |
| TraceSinkProtocol abstraction | **Deferred** — EventLogProtocol is sufficient | The higher-level sink abstraction can wait for the cloud backend. |
| Large data externalization | **Deferred** — inline data is sufficient for now | Add StorageProvider offloading when traces grow too large. |

### Tracing Architecture

| Item | Status | Context |
|---|---|---|
| Unified code path (event log everywhere) | **Deferred** — two paths for now | Direct mode uses in-memory `GraphTracer` only; event log is Temporal-only. Unify if the assembler proves reliable and the dual-path maintenance cost becomes painful. |
| Auto-cleanup of traces | **Deferred** — manual cleanup is safer for now | Traces persist on disk until manually deleted. Safer for debugging and allows usage reporting to run after graph generation. |

### Known Issues

| Item | Status | Context |
|---|---|---|
| Causal event ordering in assembler | **Known limitation** — works for current topologies | `read_events()` sorts by `(workflow_id, sequence)` which groups by lexicographic workflow ID, not execution order. In parent/child workflow topologies, this can cause `_stuff_producer_map` overwrites in the wrong order during `GraphSpecAssembler.pass_one()`, producing incorrect DATA edge sources. Consider sorting by timestamp or processing events in a topology-aware order. Flagged by codex on PR #796. |
| PipeCondition SELECTED_OUTCOME wiring | **Deferred** — no production use yet | PipeCondition has no tracer calls in production code currently. If SELECTED_OUTCOME edges are needed, that's a separate change. |
