# Master Plan v3 — Distributed Workers

> **Status**: Live plan — drives the next round of distributed-execution work.
> **Date**: 2026-05-04
> **Predecessors**: the Phase 0–5 master plan (shipped) and the interim plan that was split into per-topic files — both now retired.

The big direction now is to actually run **activities on standalone Worker pools** — separate processes from the workflow Worker pool — so we can scale workflow orchestration and inference activity execution independently. Today's tracing / cost-reporting design was built for the single-bundle-per-Worker case and breaks the moment activities move off-process. That has to be fixed before anything else.

---

## Priority order

| # | Item | Status | Owner file |
|---|---|---|---|
| **P0** | **Tracing & cost reporting across separate-process workers** | Done — see [tracing-cost-reporting-as-built.md](tracing-cost-reporting-as-built.md) (T1 marked fixed) | this file (problem statement) |
| **P0.1** | **Dry-run through activity dispatch (testing affordance)** | Not started — surfaced during P0 Phase 6 validation | this file (problem statement) |
| **P0.2** | **Deferred follow-ons from P0** | Not started — surfaced during P0 eng review | this file (problem statement) |
| **P1** | **Cross-worker cost report assembly wiring** | Not started — depends on P0 design | this file (problem statement) |
| **P2** | Phase 6a — Local cross-package dependencies in crate | Not started | [phase6a-local-cross-package-deps.md](phase6a-local-cross-package-deps.md) |
| **P3** | Phase 6b — Remote dependencies from GitHub | Not started — needs P2 | [phase6b-remote-deps-from-github.md](phase6b-remote-deps-from-github.md) |

What's already shipped on this front: see [tracing-cost-reporting-as-built.md](tracing-cost-reporting-as-built.md). It also enumerates the open issues (T1, T2, T3) that motivate P0 and P1.

Sibling tracks (separate branches, not in this plan): the error-handling work — see [`error-handling/README.md`](error-handling/README.md).

---

## P0 — Tracing & cost reporting across separate-process workers — DONE

Shipped. The current state is summarized in [tracing-cost-reporting-as-built.md](tracing-cost-reporting-as-built.md). The architectural notes below are kept for context. Follow-ons that were explicitly deferred during implementation are tracked under §P0.2.

### Why this is top priority

The whole point of the distributed-execution work is to allow **activities on standalone Worker pools** (separate processes from the workflow Worker pool). The current tracing implementation cannot serve that topology — it relies on the activity sharing the workflow's process so the singleton `ReportingManager` already has `set_event_log` configured. Until P0 is solved, splitting activities off is a regression on observability and cost reporting, not a feature.

### Problems with the current implementation

(All concretely enumerated in [tracing-cost-reporting-as-built.md](tracing-cost-reporting-as-built.md). Summarized here so the priority is legible.)

1. **Standalone activity workers lose usage events.** When an activity runs on a process that never executed `WfPipeRouter.run()`, that process's `ReportingManager._event_log_contexts` is empty for the workflow's `lookup_key`. `_emit_usage_event` misses the fast path and routes to the runner-side fallback (`_emit_usage_event_runner_fallback`, `reporting_manager.py:285`) that P0 added, so the `UsageReportEvent` still lands in the shared backend partition — the feared drop is closed on the emit side. What stays unwired is the cross-worker *read-back* of those events into the cost report (the P1 gap below).
2. **`BufferingEventLog` + `act_flush_trace_events` is workflow-scoped.** Both pieces are tied to the workflow lifecycle (buffer in workflow context, flush after pipe execution). They cannot serve a standalone activity Worker that has no enclosing workflow process.
3. **`set_event_log` lives on a process-singleton `ReportingManager`.** The per-context `_event_log_contexts` dict pattern relies on the activity emitting from the same process that configured the event log. The moment activity execution moves off-process, the activity has no way to discover its event log without something flowing in via request data (`JobMetadata` / a new `TracingContext`) instead of via a process-local dict.

### Design discussion (deferred)

We're not designing the fix yet — that comes when we pick up P0. The two natural starting points are (a) the original Phase 4.5 Step 6 `TracingActivityInboundInterceptor` design (from the now-retired master plan), and (b) plumbing tracing config + workflow id through `JobMetadata` so each activity can construct its own event log directly. Either way the activity needs request-scoped tracing data, not process-scoped state.

### Acceptance criteria — all met

- [x] Activities deployed on standalone Worker pools (separate process from workflow Workers) emit `UsageReportEvent`s that land in the same backend partition as the rest of the run.
- [x] No reliance on `WfPipeRouter` having executed in the activity's process.
- [x] No silent drops — if tracing is enabled, an activity that fails to emit raises or logs explicitly.
- [x] Direct mode and the current single-bundle Worker mode keep working unchanged.
- [x] Tests covering: standalone activity Worker, mixed worker pool, tracing disabled, NDJSON backend, DynamoDB backend (unit-level via stubbed boto3; full DDB e2e gated on `pytest -m dynamodb`).

---

## P0.1 — Dry-run through activity dispatch (testing affordance)

Today, `--dry-run` instantiates `ContentGeneratorDry()` directly inside the workflow body (`pipe_llm.py:515`, and similar sites in `pipe_extract.py`, `pipe_compose.py`, `pipe_img_gen.py`). The activity (`act_llm_gen_text` etc.) is never dispatched. As a result, the cross-worker `UsageReportEvent` emission path that P0 ships cannot be exercised in dry-run mode against router+runner workers — the runner-side fallback only fires when the activity actually dispatches across processes.

This was discovered while validating P0 Phase 6.1: a vanilla `pipelex run bundle --temporal --dry-run --mock-inputs` against a 2-worker (router+runner) topology produces only `writer_id="primary"` events; no `wf_*__w_act_*.ndjson` files appear. The Phase 4 integration test (`TestSplitWorkerUsageEmission`) works around this by substituting `act_llm_gen_text` with a wrapper that synthesizes an `LLMJob` server-side, but that's test-internal scaffolding, not a general-purpose mode.

### What's needed

A run mode that combines "no real LLM call" with "still go through the activity dispatch path", so a `pipelex run bundle` against router+runner workers exercises the same code path as live mode, just with mocked inference inside the activity. Concretely:

- `act_llm_gen_text` is dispatched to the runner as in live mode.
- Inside the activity, the inference is mocked (use `ContentGeneratorDry` *inside* the activity body, not in place of dispatching it).
- All cross-process surfaces — `_event_log_contexts` lookup miss, runner-side fallback, `writer_id="act_*"` emission — fire normally.

### Why this matters beyond P0

Same affordance unlocks dry-run e2e for any future cross-process work (P1 cost report assembly, distributed graph assembly, payload codec stress testing, etc.) without needing real LLM spend.

### Acceptance criteria (sketch)

- [ ] A `--mock-inference` (or similar) flag — distinct from `--dry-run` — that keeps activity dispatch but mocks inside the activity. Or: redefine `--dry-run` to mean "dispatch activities, mock inside" and rename the current behavior.
- [ ] `temporal-e2e-validate` Tier 8 can run in this mode and surface `wf_*__w_act_*.ndjson` files deterministically.
- [ ] Equivalent mocking sites in `pipe_extract.py`, `pipe_compose.py`, `pipe_img_gen.py` updated.

---

## P0.2 — Deferred follow-ons from P0

Items surfaced during the P0 eng review and the post-merge review. Each is independently scoped and not blocking for P0.1 / P1 / P2 / P3. Pick up individually as priorities and signals dictate.

### From eng review (logged at the time of P0 implementation)

- [ ] **`tracing_config.strict_mode: bool`** — opt-in flag that raises (instead of WARNING + drop) when the runner-side emit path fails. Useful for compliance/audit deployments where missing trace data is a hard error. (Eng review R6.)
- [ ] **DynamoDB `BatchWriteItem` for runner emission** — current path does one `PutItem` per usage event. At high-concurrency runners that's one boto3 call per emit; `BatchWriteItem` batches up to 25. Defer until actual throughput shows it matters. (Eng review R3.)
- [ ] **NDJSON shared-filesystem invariant enforcement** — the NDJSON backend assumes `traces_dir` is visible to all writer processes (router pool + runner pool + `act_flush_trace_events`). For multi-host deployments this needs NFS/EFS or equivalent. Follow-up: a startup check that warns if `traces_dir` looks like a local-only path on a multi-worker deployment. (Eng review TODO-2.)

### Post-merge review follow-ons

- [ ] **Per-thread `writer_id` for activity event log** — the surgical lock fix closes the duplicate-sequence race on `next_sequence()`, but a per-thread writer_id would eliminate the contention entirely and align the design with how Temporal's worker pool already partitions activities. Each thread would emit into its own writer namespace; dedup naturally drops to per-thread, no lock needed in the hot path.
- [ ] **Project-wide migration of `JobMetadata.started_at` to timezone-aware datetimes** — the landed patch builds the synthetic `now` with the same `tzinfo` as the incoming `started_at`, which removes the immediate `TypeError` crash but doesn't fix the underlying inconsistency: `JobMetadata.started_at` default factory is naive (`datetime.now`) while several callers (e.g. `pipe_abstract.py:428`) construct aware datetimes (`datetime.now(timezone.utc)`). A clean migration would standardize on `datetime.now(timezone.utc)` everywhere, document the tz contract on `JobMetadata`, and let `duration` subtract without defensive tzinfo matching at every site.

---

## P1 — Cross-worker cost report assembly wiring

### Why this is second, not first

Even if P0 ships, the events still need to be turned into a cost report. Today the read-back path exists for the **graph** (`assemble_graph_on_output` / `act_assemble_graph` → `GraphSpecAssembler`) but not for **usage**. The pieces all exist on the manager side:

- `UsageAggregator.aggregate(events) → list[AnyTokensUsage]` (`pipelex/tracing/usage_aggregator.py`).
- `ReportingManager.inject_tokens_usages(pipeline_run_id, tokens_usages)` (`reporting_manager.py:223`) — docstring: *"Used after assembling usage data from distributed trace events, so that generate_report() can produce a complete cost report across all workers."*
- `ReportingManager.generate_report(pipeline_run_id)` (`reporting_manager.py:365`).

`generate_report()` itself now has a runtime caller — the CLI run path invokes it at `_run_core.py:224`. But that path only reports from the **local, in-process** usage registries; it never reads back the distributed trace events. `UsageAggregator.aggregate()` and `inject_tokens_usages()` still have zero runtime callers, so `UsageReportEvent`s emitted by runner/worker processes sit in the backend and never get assembled into the cost report. The missing piece is the cross-worker read-back, not `generate_report` itself.

This is a small piece of plumbing once P0's design is settled — the same place that calls the graph assembler can call the usage aggregator and inject the result into the report delegate before `generate_report` runs.

### Acceptance criteria (sketch)

- [ ] Runtime path: read events for `pipeline_run_id` → `UsageAggregator.aggregate()` → `ReportingManager.inject_tokens_usages()` → `generate_report()`.
- [ ] Wired in both direct mode (in `pipelex/pipeline/runner.py`) and Temporal mode (alongside or inside the existing graph-assembly hook).
- [ ] Cross-worker case verified: parent workflow on Worker A, child workflow on Worker B, activity on Worker C — single end-of-run cost report contains usage from all three.
- [ ] Revisit the local-only registry fallback (`_get_registry_strict` at `reporting_manager.py:115`, `_try_add_to_registry` at `:137`) once the distributed read-back lands. (The old `_get_registry` TODO that previously sat here is already gone — the accessor was renamed to `_get_registry_strict` — but the local-only behaviour it flagged remains until the cross-worker path is wired.)

---

## P2 — Phase 6a: Local cross-package dependencies in crate

Detailed plan: [phase6a-local-cross-package-deps.md](phase6a-local-cross-package-deps.md).

In one line: ship dependency blueprints inside the `LibraryCrate` so workers don't need the dependency packages on PIPELEXPATH. Prerequisite for P3.

---

## P3 — Phase 6b: Remote dependencies from GitHub

Detailed plan: [phase6b-remote-deps-from-github.md](phase6b-remote-deps-from-github.md).

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

P2 (Phase 6a — local cross-package deps)
   │
   ▼
P3 (Phase 6b — remote deps from GitHub)
```

P0/P0.1/P0.2/P1 and P2/P3 are independent tracks; P0 unlocks P0.1, P0.2, and P1; P2 blocks P3. P0.1 is a parallel testing affordance that improves P0 / P1 / future cross-process work confidence. P0.2 items are independent of each other — pick them up individually as needs and signals dictate.
