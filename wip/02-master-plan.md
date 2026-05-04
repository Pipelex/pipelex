# Master Plan v3 — Distributed Workers

> **Status**: Live plan — drives the next round of distributed-execution work.
> **Date**: 2026-05-04
> **Predecessors**: [archive/00-master-plan.md](archive/00-master-plan.md) (Phases 0–5, shipped) · [archive/01-master-plan.md](archive/01-master-plan.md) (interim plan, now split into per-topic files).

The big direction now is to actually run **activities on standalone Worker pools** — separate processes from the workflow Worker pool — so we can scale workflow orchestration and inference activity execution independently. Today's tracing / cost-reporting design was built for the single-bundle-per-Worker case and breaks the moment activities move off-process. That has to be fixed before anything else.

---

## Priority order

| # | Item | Status | Owner file |
|---|---|---|---|
| **P0** | **Tracing & cost reporting across separate-process workers** | Done — shipped on `fix/Tracing-across-workers`; see [TODOS.md](../TODOS.md) and [tracing-cost-reporting-as-built.md](tracing-cost-reporting-as-built.md) (T1 marked fixed) | this file (problem statement) |
| **P0.1** | **Dry-run through activity dispatch (testing affordance)** | Not started — surfaced during P0 Phase 6 validation | this file (problem statement) |
| **P1** | **Cross-worker cost report assembly wiring** | Not started — depends on P0 design | this file (problem statement) |
| **P2** | Phase 6a — Local cross-package dependencies in crate | Not started | [phase6a-local-cross-package-deps.md](phase6a-local-cross-package-deps.md) |
| **P3** | Phase 6b — Remote dependencies from GitHub | Not started — needs P2 | [phase6b-remote-deps-from-github.md](phase6b-remote-deps-from-github.md) |

What's already shipped on this front: see [tracing-cost-reporting-as-built.md](tracing-cost-reporting-as-built.md). It also enumerates the open issues (T1, T2, T3) that motivate P0 and P1.

Sibling tracks (separate branches, not in this plan): worker error-handling Phases 4–7 (`error-handling-phase-{4,5,6,7}-*.md`), instructor-unwrap port (`instructor-unwrap-other-workers.md`).

---

## P0 — Tracing & cost reporting across separate-process workers — DONE

Shipped on `fix/Tracing-across-workers`. The full plan (six phases, eng-review notes, decisions) lives in [TODOS.md](../TODOS.md); the architectural notes below are kept for context.

### Why this is top priority

The whole point of the distributed-execution work is to allow **activities on standalone Worker pools** (separate processes from the workflow Worker pool). The current tracing implementation cannot serve that topology — it relies on the activity sharing the workflow's process so the singleton `ReportingManager` already has `set_event_log` configured. Until P0 is solved, splitting activities off is a regression on observability and cost reporting, not a feature.

### Problems with the current implementation

(All concretely enumerated in [tracing-cost-reporting-as-built.md](tracing-cost-reporting-as-built.md). Summarized here so the priority is legible.)

1. **Standalone activity workers lose usage events.** When an activity runs on a process that never executed `WfPipeRouter.run()`, that process's `ReportingManager._event_log_contexts` is empty for the workflow's `lookup_key`. `_emit_usage_event` returns silently; usage data is dropped. The `_get_registry` TODO at `reporting_manager.py:111-117` ("Auto-create registry for unknown pipeline IDs ... TODO: replace with proper distributed reporting system") confirms this is a known gap.
2. **`BufferingEventLog` + `act_flush_trace_events` is workflow-scoped.** Both pieces are tied to the workflow lifecycle (buffer in workflow context, flush after pipe execution). They cannot serve a standalone activity Worker that has no enclosing workflow process.
3. **`set_event_log` lives on a process-singleton `ReportingManager`.** The per-context `_event_log_contexts` dict pattern relies on the activity emitting from the same process that configured the event log. The moment activity execution moves off-process, the activity has no way to discover its event log without something flowing in via request data (`JobMetadata` / a new `TracingContext`) instead of via a process-local dict.

### Design discussion (deferred)

We're not designing the fix yet — that comes when we pick up P0. The two natural starting points are (a) the original Phase 4.5 Step 6 `TracingActivityInboundInterceptor` design (now in `archive/00-master-plan.md` and `archive/01-master-plan.md`), and (b) plumbing tracing config + workflow id through `JobMetadata` so each activity can construct its own event log directly. Either way the activity needs request-scoped tracing data, not process-scoped state.

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

## P1 — Cross-worker cost report assembly wiring

### Why this is second, not first

Even if P0 ships, the events still need to be turned into a cost report. Today the read-back path exists for the **graph** (`assemble_graph_on_output` / `act_assemble_graph` → `GraphSpecAssembler`) but not for **usage**. The pieces all exist on the manager side:

- `UsageAggregator.aggregate(events) → list[AnyTokensUsage]` (`pipelex/tracing/usage_aggregator.py`).
- `ReportingManager.inject_tokens_usages(pipeline_run_id, tokens_usages)` (`reporting_manager.py:191`) — docstring: *"Used after assembling usage data from distributed trace events, so that generate_report() can produce a complete cost report across all workers."*
- `ReportingManager.generate_report(pipeline_run_id)` (`reporting_manager.py:247`).

Nothing in the runtime calls these. `generate_report()` has zero runtime callers; only integration tests invoke it. Captured events sit in the backend and never become a cost report.

This is a small piece of plumbing once P0's design is settled — the same place that calls the graph assembler can call the usage aggregator and inject the result into the report delegate before `generate_report` runs.

### Acceptance criteria (sketch)

- [ ] Runtime path: read events for `pipeline_run_id` → `UsageAggregator.aggregate()` → `ReportingManager.inject_tokens_usages()` → `generate_report()`.
- [ ] Wired in both direct mode (in `pipelex/pipeline/runner.py`) and Temporal mode (alongside or inside the existing graph-assembly hook).
- [ ] Cross-worker case verified: parent workflow on Worker A, child workflow on Worker B, activity on Worker C — single end-of-run cost report contains usage from all three.
- [ ] Replace / remove the `_get_registry` TODO at `reporting_manager.py:111-117` since the proper distributed path now exists.

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
   │
   ▼
P1 (Cross-worker cost report assembly)

P2 (Phase 6a — local cross-package deps)
   │
   ▼
P3 (Phase 6b — remote deps from GitHub)
```

P0/P0.1/P1 and P2/P3 are independent tracks; P0 blocks both P0.1 and P1, P2 blocks P3. P0.1 is a parallel testing affordance that improves P0 / P1 / future cross-process work confidence.
