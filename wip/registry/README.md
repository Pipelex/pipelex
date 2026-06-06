# `UsageRegistry` lifecycle — leak + distributed cost aggregation

This folder tracks one topic that grew as we worked it: the lifecycle of the per-run `UsageRegistry` held in the process-global `ReportingManager`. It started as a narrow "success-path leak" bug and, on investigation, turned out to be the same lifecycle as the deferred **distributed cost-report aggregation** (the distributed-execution track's T2 / P1). The leak is the missing *close*; cost aggregation is the missing *replay-populate*. Same buffer, same lifecycle, one piece of work.

**Status: analysis complete, all design decisions locked. Next is the implementation plan** — start a fresh planning session from the synthesis doc's "For the planning phase" section.

## Start here

- [`registry-lifecycle-synthesis.md`](registry-lifecycle-synthesis.md) — **the canonical doc.** The unified model, the locked decisions (Option B; a default-on `--costs` switch that folds in `--cost-report`; events as the single source; usage carried on `PipeOutput`), the readiness checklist, and the planning-phase scope + test surface.

## The trail (how we got here — findings still valid, recommendations superseded by the synthesis)

- [`registry-success-path-leak-brief.md`](registry-success-path-leak-brief.md) — the original brief that opened the investigation: the success-path leak, evidence, and why it is not a one-line fix.
- [`registry-success-path-leak-assessment.md`](registry-success-path-leak-assessment.md) — verification of the brief + extended blast radius (both API endpoints leak; `/pipeline/start` is dead weight; the dead `inject_tokens_usages`; the caller-id collision; `cocode` double-counting).
- [`registry-success-path-leak-execution-contexts.md`](registry-success-path-leak-execution-contexts.md) — the revisit through DIRECT vs Temporal: the registry is a DIRECT-mode in-process buffer, and the leak is one of two facets later unified in the synthesis.

## Companion track

The cost-reporting half lives in the distributed-execution plan, and the architecture to mirror (graph-spec assembly) is documented there:

- [`../distributed-execution/tracing-cost-reporting.md`](../distributed-execution/tracing-cost-reporting.md) — as-built tracing & cost reporting, including **T2** (cross-worker cost report assembly not wired). Line references in that doc are somewhat stale, but the architecture description holds.
- [`../distributed-execution/README.md`](../distributed-execution/README.md) — the priority plan; **P1** is the cost-report assembly wiring this synthesis designs.
