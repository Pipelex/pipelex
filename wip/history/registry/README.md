# `UsageRegistry` leak fix + distributed cost reporting

Cost reporting was reworked from a leaky per-run, in-process `UsageRegistry` buffer into an **event-sourced artifact that rides back on `PipeOutput`**. The success-path registry leak is gone by removal; a multi-worker (Temporal) run now aggregates usage from every worker into a single end-of-run cost report. A default-on `--costs` switch decouples cost collection from `--graph` over a shared event-log transport, and a cheap deterministic mock validates the distributed path (originally `--mock-inference`; since the unified dry run it is the internal `--dry-run --mock-usage` trigger — see `../../dry-run-refactor/plan-unified-dry-run.md`).

Shipped in **PR #967** on `fix/For-API-update`, with the companion rename **#968** (`GraphContext → TraceContext`, `is_generate_costs → is_generate_usage`).

> **Scope — NDJSON only.** The cost-reporting event log is implemented and validated through **NDJSON**. The end-of-run read-back is backend-agnostic, so the code path covers DynamoDB for free — but making distributed cost reporting actually work on DynamoDB is **deferred** and is not a validation target of this work.

## What we built

- [`cost-reporting-overview.html`](cost-reporting-overview.html) — **the illustrated overview. Start here.** TL;DR, the two-bugs-one-lifecycle framing, before/after architecture, the shared-transport `--costs` switch, the cross-worker flow, the critical diffs, and the deferred items.

## Shipped follow-ups

- [`cost-report-submitter-helper-handoff.md`](cost-report-submitter-helper-handoff.md) — ✅ the one-arg `render_cost_report_for_output(pipe_output)` submitter helper (the embedder-ergonomics facet): submitters render the standard cost report from a finished output in one call, with the `--costs` gate read off the output (`tokens_usages is None`) instead of re-read from config. Landed on `feature/Cost-report-helper`; the downstream cocode delegate collapse is still pending. Composes with — does not resolve — decisions #3/#6 below.

## Open follow-ups

- [`deferred-followups.md`](deferred-followups.md) — the deliberate non-goals: the costs-only in-memory tracer skip (E1 deep half), cost-per-node correlation, the A1 `TraceContext.from_execution_config` factory, T5, T3 request-scoped tracing state, the costs-only event-log explicit-close cleanup (PR #977 re-review), `--mock-inference` coverage, and the leftover `graph_id → run_id` rename + shelved `TraceContext` split.
- [`cost-report-deferred-decisions.md`](cost-report-deferred-decisions.md) — two deferred **design decisions**: (#3) cost reporting is coupled to `tracing_config.is_enabled` (costs-on + tracing-off ⇒ no report); (#6) the agent CLI gates costs on the raw `costs` param while the main CLI gates on the resolved `is_generate_usage`. Both want a deliberate call.
- [`usage-reporting-without-cost.md`](usage-reporting-without-cost.md) — capability idea (low priority): make usage (token counts) a separately-requestable output, with cost as one view layered on top.

## Companion track

The cost-reporting half mirrors graph-spec assembly, documented in the distributed-execution feature:

- [`../../distributed-execution/tracing-cost-reporting.md`](../../distributed-execution/tracing-cost-reporting.md) — as-built tracing & cost reporting (T2 cross-worker cost-report assembly = **FIXED** by this work).
- [`../../distributed-execution/README.md`](../../distributed-execution/README.md) — the priority plan (P0.1 `--mock-inference` and P1 cost-report assembly both **shipped** here).
