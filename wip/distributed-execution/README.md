# Distributed Execution — Plan & Track Map

The big direction: run **activities on standalone Worker pools** — separate processes from the workflow Worker pool — so workflow orchestration and inference activity execution scale independently.

This folder is the **distributed-execution track**: running MTHDS methods as Temporal workflows across separate worker processes. This README is the priority-ordered plan; the other docs are the per-topic designs and references it points to.

## Docs in this track

- [tracing-cost-reporting.md](tracing-cost-reporting.md) — as-built reference for tracing & cost reporting across workers, plus its deferred items (P0/P1 context).
- [local-cross-package-deps.md](local-cross-package-deps.md) — ship dependency blueprints inside the crate (P2).
- [remote-deps-from-github.md](remote-deps-from-github.md) — fetch dependencies from remote addresses (P3).
- [crate-first-architecture.md](crate-first-architecture.md) — the crate-first vision behind P2/P3, with deferred capabilities (stripping, fingerprint validation, cross-worker cache).
- [temporal-ids-and-naming.md](temporal-ids-and-naming.md) — implemented design for Temporal IDs, naming, and observability surfaces.
- [temporal-exception-model-revamp.md](temporal-exception-model-revamp.md) — deferred proposal to reparent workflow exceptions onto `ApplicationError`.
- [schema-reconstruction-hardening.md](schema-reconstruction-hardening.md) — deferred hardening of cross-process Pydantic-schema reconstruction.
- [unit-testing-worker-sandbox-validation.md](unit-testing-worker-sandbox-validation.md) — deferred bug: a sandboxed worker can't boot under `--is-unit-testing` because the registered test workflows fail temporalio sandbox validation.

---

## Priority order

| # | Item | Detail |
|---|---|---|
| **P0 ✓** | Tracing & cost reporting across separate-process workers | shipped — [tracing-cost-reporting.md](tracing-cost-reporting.md) |
| **P0.1** | Dry-run through activity dispatch (testing affordance) | below |
| **P0.2** | Deferred follow-ons from P0 | below |
| **P1** | Cross-worker cost report assembly wiring | depends on P0 — below |
| **P2** | Local cross-package dependencies in the crate | [local-cross-package-deps.md](local-cross-package-deps.md) |
| **P3** | Remote dependencies from GitHub | needs P2 — [remote-deps-from-github.md](remote-deps-from-github.md) |

P0/P0.1/P0.2/P1 form one chain (P0 unlocks the rest); P2/P3 are an independent chain (P2 blocks P3). [tracing-cost-reporting.md](tracing-cost-reporting.md) carries the as-built design and the open T2/T3 gaps that motivate P1.

Sibling track (separate branch, not in this plan): the error-handling work — see [`error-handling/README.md`](../error-handling/README.md).

---

## P0 — Tracing & cost reporting across separate-process workers — DONE

Shipped. The as-built design, what works today, and the open T2/T3 gaps are in [tracing-cost-reporting.md](tracing-cost-reporting.md). The remaining cross-worker read-back is P1; the explicitly-deferred follow-ons are under P0.2.

---

## P0.1 — Dry-run through activity dispatch (testing affordance)

Today `--dry-run` instantiates `ContentGeneratorDry()` directly inside the workflow body (`pipe_llm.py:515`, and similar sites in `pipe_extract.py`, `pipe_compose.py`, `pipe_img_gen.py`). The activity (`act_llm_gen_text` etc.) is never dispatched, so the cross-worker `UsageReportEvent` emission path cannot be exercised in dry-run against router+runner workers — the runner-side fallback only fires when the activity actually dispatches across processes. (Observed validating P0: `pipelex run bundle --temporal --dry-run --mock-inputs` against a router+runner topology produces only `writer_id="primary"` events; no `wf_*__w_act_*.ndjson` files.)

What's needed: a run mode that keeps activity dispatch but mocks inference *inside* the activity (use `ContentGeneratorDry` inside the activity body, not in place of dispatching it), so the cross-process surfaces — `_event_log_contexts` lookup miss, runner-side fallback, `writer_id="act_*"` emission — all fire. Concretely: a `--mock-inference` flag distinct from `--dry-run` (or redefine `--dry-run` to dispatch-and-mock-inside and rename the current behavior); equivalent mock sites in `pipe_extract.py` / `pipe_compose.py` / `pipe_img_gen.py`; and `temporal-e2e-validate` Tier 8 able to run in this mode and surface `wf_*__w_act_*.ndjson` deterministically.

Beyond P0, the same affordance unlocks dry-run e2e for any cross-process work (P1 cost report assembly, distributed graph assembly, payload codec stress testing) without real LLM spend.

---

## P0.2 — Deferred follow-ons from P0

Each is independently scoped and not blocking. Pick up individually as signals dictate.

- **`tracing_config.strict_mode: bool`** — opt-in flag that raises (instead of WARNING + drop) when the runner-side emit path fails. For compliance/audit deployments where missing trace data is a hard error.
- **DynamoDB `BatchWriteItem` for runner emission** — the current path does one `PutItem` per usage event; `BatchWriteItem` batches up to 25. Defer until throughput shows it matters.
- **NDJSON shared-filesystem invariant enforcement** — the NDJSON backend assumes `traces_dir` is visible to all writer processes (router pool + runner pool + `act_flush_trace_events`); multi-host deployments need NFS/EFS. Add a startup check that warns if `traces_dir` looks local-only on a multi-worker deployment.
- **Per-thread `writer_id` for activity event log** — the surgical lock closes the duplicate-sequence race on `next_sequence()`; a per-thread writer namespace would eliminate the contention entirely and align with how Temporal's worker pool partitions activities (dedup drops to per-thread, no hot-path lock).
- **Project-wide migration of `JobMetadata.started_at` to timezone-aware datetimes** — the landed patch builds the synthetic `now` with the incoming `started_at`'s `tzinfo`, removing the immediate `TypeError` but not the underlying inconsistency: the default factory is naive (`datetime.now`) while several callers (e.g. `pipe_abstract.py:428`) construct aware datetimes. A clean migration standardizes on `datetime.now(timezone.utc)`, documents the tz contract on `JobMetadata`, and lets `duration` subtract without per-site tzinfo matching.

---

## P1 — Cross-worker cost report assembly wiring

### Why this is second, not first

Even with P0 shipped, the events still need to be turned into a cost report. The read-back path exists for the **graph** (`assemble_graph_on_output` / `act_assemble_graph` → `GraphSpecAssembler`) but not for **usage**. The pieces all exist on the manager side:

- `UsageAggregator.aggregate(events) → list[AnyTokensUsage]` (`pipelex/tracing/usage_aggregator.py`).
- `ReportingManager.inject_tokens_usages(pipeline_run_id, tokens_usages)` (`reporting_manager.py:223`) — docstring: *"Used after assembling usage data from distributed trace events, so that generate_report() can produce a complete cost report across all workers."*
- `ReportingManager.generate_report(pipeline_run_id)` (`reporting_manager.py:365`).

`generate_report()` has a runtime caller — the CLI run path invokes it at `_run_core.py:224` — but that path reports only from the **local, in-process** usage registries; it never reads back the distributed trace events. `UsageAggregator.aggregate()` and `inject_tokens_usages()` still have zero runtime callers, so `UsageReportEvent`s emitted by runner/worker processes sit in the backend and never get assembled into the cost report. The missing piece is the cross-worker read-back, not `generate_report` itself.

### The work

Read events for `pipeline_run_id` → `UsageAggregator.aggregate()` → `ReportingManager.inject_tokens_usages()` → `generate_report()`, wired in both direct mode (`pipelex/pipeline/runner.py`) and Temporal mode (alongside or inside the existing graph-assembly hook) — the same place that calls the graph assembler can call the usage aggregator and inject the result before `generate_report` runs. Verify the cross-worker case: parent workflow on Worker A, child on Worker B, activity on Worker C → one end-of-run cost report carrying usage from all three. Once the read-back lands, revisit the local-only registry fallback (`_get_registry_strict` at `reporting_manager.py:115`, `_try_add_to_registry` at `:137`), whose local-only behaviour stands until the cross-worker path is wired.

---

## P2 — Local cross-package dependencies in the crate

Detailed plan: [local-cross-package-deps.md](local-cross-package-deps.md).

In one line: ship dependency blueprints inside the `LibraryCrate` so workers don't need the dependency packages on PIPELEXPATH. Prerequisite for P3.

---

## P3 — Remote dependencies from GitHub

Detailed plan: [remote-deps-from-github.md](remote-deps-from-github.md).

In one line: extend the blueprint collector from P2 with a remote (GitHub) resolver so the crate can carry deps fetched from external addresses, making workers fully stateless.

---

## Dependencies between items

```
P0 (Tracing across separate workers)
   │
   ├─► P0.1 (Dry-run through activity dispatch — testing affordance)
   ├─► P0.2 (Deferred follow-ons — independent, pick up individually)
   │
   ▼
P1 (Cross-worker cost report assembly)

P2 (Local cross-package deps)
   │
   ▼
P3 (Remote deps from GitHub)
```

P0/P0.1/P0.2/P1 and P2/P3 are independent tracks; P0 unlocks P0.1, P0.2, and P1; P2 blocks P3. P0.1 is a parallel testing affordance that raises confidence in P0 / P1 / future cross-process work.
