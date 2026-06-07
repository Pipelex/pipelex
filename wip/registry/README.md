# `UsageRegistry` lifecycle — leak + distributed cost aggregation

This folder tracks one topic that grew as we worked it: the lifecycle of the per-run `UsageRegistry` held in the process-global `ReportingManager`. It started as a narrow "success-path leak" bug and, on investigation, turned out to be the same lifecycle as the deferred **distributed cost-report aggregation** (the distributed-execution track's T2 / P1). The leak is the missing *close*; cost aggregation is the missing *replay-populate*. Same buffer, same lifecycle, one piece of work.

**Status: IMPLEMENTED.** All design decisions were locked, then built out across the phased plan in [`../../TODOS.md`](../../TODOS.md). Phases 1–5 (emit decoupling → usage on `PipeOutput` → renderer cutover → registry removal → `--mock-inference`) are committed on `fix/For-API-update`; Phase 6 (the `temporal-e2e-validate` skill's Tier 8b) and Phase 7 (changelog + these as-built docs) landed on top. The leak is fixed by removal and cross-worker cost reporting works end to end.

## Start here

- [`../../TODOS.md`](../../TODOS.md) — **the canonical as-built record.** The sequenced phases, every checkpoint's cold-start notes (deleted symbols, new anchors, deviations), and §7's deferred-items list. Read this first when reviewing the branch.
- [`registry-lifecycle-synthesis.md`](registry-lifecycle-synthesis.md) — the locked design the plan implemented: the unified model, Option B (usage on `PipeOutput`), the default-on `--costs` switch folding in `--cost-report`, events as the single source.
- [`deferred-followups.md`](deferred-followups.md) — **the deferred non-goals** of this feature (D5 costs-only tracer skip, cost-per-node correlation, A1 factory, T5, T3, `--mock-inference` coverage). The two deferred *design decisions* are in [`cost-report-deferred-decisions.md`](cost-report-deferred-decisions.md).
- [`graphcontext-rename-to-tracecontext.md`](graphcontext-rename-to-tracecontext.md) — **deferred naming cleanup** surfaced by the #967 fast-path emit fix: usage/cost events now ride on `GraphContext`, which was born graph-only. Decided (Option 1): rename `GraphContext` → `TraceContext` as its own change. Now also bundles a **companion flag rename** (`is_generate_costs` → `is_generate_usage`, aligning the internal gate to the `emit_usage_events` it feeds; public `--costs` flag and cost-computation cluster left alone). The diagnosis, field taxonomy, and the "graph substrate is always present" constraint that bounds a deeper split are recorded there.
- [`usage-reporting-without-cost.md`](usage-reporting-without-cost.md) — **capability idea, low priority.** The deeper question behind the naming cleanup: should usage (token counts) be a separately-requestable output with cost as one view on top, rather than usage-emission and cost-render being bundled under one switch? Decide the capability before touching the public `--costs` flag.

## Review records (all resolved — kept for the audit trail)

- [`phase1-emit-decoupling-review.md`](phase1-emit-decoupling-review.md) — multi-angle review of the Phase 1 implementation. Its correctness/efficiency/altitude cluster (F1/F2/E1/A2 etc.) was folded into Phase 2 — see TODOS Phase 2's review-driven additions and CHECKPOINT 2's "review cluster confirmed landed".
- [`cost-report-deferred-decisions.md`](cost-report-deferred-decisions.md) — the two **still-deferred** design decisions from the Phase 3 review (the correctness/cleanup findings #1/#2/#4/#7 were fixed in Phase 3). #3: cost reporting is coupled to `tracing_config.is_enabled` (costs-on + tracing-off ⇒ no report). #6: the agent CLI gates on the raw `costs` param while the main CLI gates on the resolved config. Both still want a deliberate call — the only open design items from this track.
- [`phase5-mock-inference-review.md`](phase5-mock-inference-review.md) — review of the Phase 5 `--mock-inference` change. The whole punch-list (F1 hard guard for img-gen/extract/search, F2 typed object-fidelity error, F3 shared flag validator, F4/F5) **landed** — see TODOS §7 "Post-CP5 review punch-list landed (2026-06-07)". The full per-operator mock coverage and the `is_mock_inference → run_mode=DRY` re-keying remain tracked in [`../dry-run-refactor/followup-leaf-run-mode-mock.md`](../dry-run-refactor/followup-leaf-run-mode-mock.md).

## The trail (how we got here — findings still valid, recommendations superseded by the synthesis)

- [`registry-success-path-leak-brief.md`](registry-success-path-leak-brief.md) — the original brief that opened the investigation: the success-path leak, evidence, and why it is not a one-line fix.
- [`registry-success-path-leak-assessment.md`](registry-success-path-leak-assessment.md) — verification of the brief + extended blast radius (both API endpoints leak; `/pipeline/start` is dead weight; the dead `inject_tokens_usages`; the caller-id collision; `cocode` double-counting).
- [`registry-success-path-leak-execution-contexts.md`](registry-success-path-leak-execution-contexts.md) — the revisit through DIRECT vs Temporal: the registry is a DIRECT-mode in-process buffer, and the leak is one of two facets later unified in the synthesis.

## Companion track

The cost-reporting half lives in the distributed-execution plan, where the mirrored architecture (graph-spec assembly) is documented:

- [`../distributed-execution/tracing-cost-reporting.md`](../distributed-execution/tracing-cost-reporting.md) — as-built tracing & cost reporting; **T2** (cross-worker cost report assembly) is now **FIXED** via this track's Option B.
- [`../distributed-execution/README.md`](../distributed-execution/README.md) — the priority plan; **P0.1** (`--mock-inference`) and **P1** (cost-report assembly) are both **shipped** by this work.
