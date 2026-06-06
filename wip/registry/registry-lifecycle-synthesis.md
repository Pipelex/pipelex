# Synthesis: the `UsageRegistry` lifecycle — leak fix and distributed cost aggregation are one piece of work

**Status:** **Analysis complete — all design decisions are locked (see Decided, below). This doc is the input to the implementation-planning phase; start a fresh planning session from [For the planning phase](#for-the-planning-phase).** Supersedes the *recommendation* sections of [`registry-success-path-leak-assessment.md`](registry-success-path-leak-assessment.md) and [`registry-success-path-leak-execution-contexts.md`](registry-success-path-leak-execution-contexts.md) (their *findings* still stand). Pairs with the distributed-execution track's **T2 / P1** — see [`../distributed-execution/tracing-cost-reporting.md`](../distributed-execution/tracing-cost-reporting.md) and [`../distributed-execution/README.md`](../distributed-execution/README.md).

## Answers to the two questions

- **Are we ready to take this on now?** The foundation is ready: P0 shipped (usage events from every worker land in one backend partition with `writer_id` disambiguation), the cross-worker read-back is proven by graph assembly, and the cost pieces (`UsageAggregator.aggregate`, `inject_tokens_usages`, `generate_report`) all exist. The design decisions are now locked (below); the one remaining prep item is a cheap way to validate the cross-worker path (the P0.1 testing affordance). So: ready to plan and build.
- **Fix the leak first, or complete cost reporting first?** Neither in isolation — **do the leak fix as the closing step of the cost-reporting lifecycle work, in the same change.** The leak is the missing *close* of the same registry lifecycle that distributed cost reporting completes the *populate* of. Fixing the leak standalone first would bake in lifecycle decisions (where the registry is opened, whether the Temporal submitter opens one at all) that the cost-reporting design then has to unwind. The only reason to ship a standalone leak stopgap first is acute production memory pressure — and the leaked objects are tiny empty registries, so that is unlikely to be urgent.

## The unifying insight

The `UsageRegistry` is a **per-run, in-process cost-aggregation buffer**. Its full lifecycle is: **open → populate → report → close.** It has two possible population sources:

- **Live** — `_try_add_to_registry` during in-process inference. Only fires where inference runs in the same process that opened the registry (DIRECT mode, or a same-process worker).
- **Replay** — `inject_tokens_usages` from event-log read-back. The path for distributed runs, at end-of-run assembly.

Seen this way, the two problems we have been circling are the **same lifecycle, missing two different steps**:

- **The leak** = the **close** step never happens on the success path. (The brief's bug.)
- **Distributed cost reporting** = the **replay-populate** step is not wired. (T2 / P1.)

That is why they must be designed together: the close we need for the leak is the last step of the assembly hook that the cost report needs, and the source-of-truth decision (live vs replay) determines where and whether a registry is even opened.

## The template to mirror: graph-spec assembly

Graph assembly already solved the cross-worker "analyze the event stream at the end" problem the user pointed at. It is backend-agnostic (`make_event_log(tracing_config)` picks NDJSON or DynamoDB) and it assembles at the **end of the run**, then rides the artifact back to the caller **on `PipeOutput`**, in both modes:

- **DIRECT:** `PipeRun.run()` `finally` → `assemble_graph_on_output(pipe_output, ...)` (`pipe_run/graph_assembly.py`) reads events for the `pipeline_run_id`, builds the `GraphSpec`, sets `pipe_output.graph_spec`. Runs in the submitter process.
- **TEMPORAL:** `WfPipeRun.run()` Step 2 → `act_assemble_graph` activity reads events, returns the `GraphSpec`, the workflow sets `pipe_output.graph_spec`. The `pipe_output` (graph included) is returned from the workflow and flows back to the submitter via `TemporalPipeRun.run()` → rehydrate.

The usage pieces are the direct analogues, already present:

- `UsageAggregator.aggregate(events) → list[AnyTokensUsage]` (`tracing/usage_aggregator.py`) — the `GraphSpecAssembler.assemble` analogue (trivial: keep the `UsageReportEvent` payloads).
- `CostRegistry.generate_report(tokens_usages=...)` already renders from a plain usage list — no registry needed to render.

## The design fork (decision needed)

Both options "analyze events at the end like graph does." They differ in **where the assembled usage lands** and therefore **whether the leaky submitter registry survives at all.**

### Option B — mirror graph exactly: ride usage on `PipeOutput` (recommended)

Assemble usage at the same hook as the graph (worker-side in Temporal, submitter-side in direct), attach the aggregated `tokens_usages` (or a small cost summary) to `PipeOutput` alongside `graph_spec`, and have the **submitter** render the cost report from `pipe_output` via `CostRegistry.generate_report(tokens_usages=...)`.

- **The leak vanishes by removal.** Nothing needs the submitter-side registry that `pipeline_run_setup` opens — so stop opening it. No registry on the submitter means nothing to leak, on every entry point and both backends. The live `_try_add_to_registry` path and dead `inject_tokens_usages` both retire.
- **Exact symmetry with graph** — same hook, same flow, same landing on `PipeOutput`, one mental model for "post-run analysis of the event stream."
- **The decoupling it requires — a dedicated `--costs` switch (agreed direction).** Cost then comes from the event stream in all modes, so usage events must be emittable independently of `--graph`. Today they are accidentally coupled: `set_event_log` is only wired when `is_generate_graph` + tracing, so once the live registry is removed, `--no-graph` would lose cost entirely. The fix is a dedicated `--costs` / `is_generate_costs` switch that mirrors `--graph` / `is_generate_graph`: the event log is the **shared transport**, `--graph` gates graph (node/edge) event emission + `GraphSpecAssembler`, `--costs` gates `UsageReportEvent` emission + `UsageAggregator`, and each rides its artifact back on `PipeOutput`. This is a more literal mirror of graph than "usage events always on", and it is **load-bearing, not cosmetic** — it is what keeps cost reporting working when graph is off. (In Temporal, the `--costs` flag must thread to the worker so its emission respects it — same plumbing as `--graph`.)

### Option A — manager-centric: replay into the submitter registry (the plan's stated path)

Keep the submitter registry. DIRECT stays live-populated; for TEMPORAL the **submitter** (after `TemporalPipeRun.run()` returns) reads events back → `UsageAggregator.aggregate` → `inject_tokens_usages(pipeline_run_id)` → `generate_report(pipeline_run_id)`. Fix the leak by **closing** the registry after the report, unconditionally, in every mode.

- **Pros:** preserves cost reporting without tracing in DIRECT mode (the live registry needs no events); uses the `inject_tokens_usages` plumbing the plan already intends; smaller blast radius on the response model.
- **Cons:** keeps the process-global singleton on the hot path (the T3 design smell persists); does not mirror graph (cost goes through the singleton, graph rides on output — two patterns); the TEMPORAL read-back must run submitter-side (not in the worker `act_assemble_graph`) so the report reaches the caller; and the leak fix is now an easy-to-miss "remember to close" rather than a structural guarantee.

**Recommendation: Option B (chosen), with a dedicated `--costs` switch.** It mirrors the graph-spec approach literally — `--graph` and `--costs` become two symmetric "post-run analyses of the event stream", each gating its own event type + assembler and riding its artifact on `PipeOutput`. It makes the leak structurally impossible (no submitter registry) instead of relying on a close, and removes (rather than revives) dead code. The `--costs` switch is not cosmetic: once the live registry is gone, it is what keeps cost working when `--graph` is off. Option A is the fallback only if we decide cost reporting must keep working with the event log fully off in DIRECT mode (which the `--costs` switch otherwise handles).

## Double-counting caution (either option)

In DIRECT mode with usage events on, inference both adds to the live registry (`_try_add_to_registry`) **and** emits a `UsageReportEvent`. Aggregating the events into the same run's registry on top of the live adds would **double-count**. Whatever we pick must choose a single source of truth per run: Option B removes the live registry so there is one source (events); Option A must gate replay to the modes where the registry is empty (TEMPORAL only), never re-injecting in DIRECT.

## Scope for now (per the build guidance)

- **NDJSON only.** The read-back is backend-agnostic, so the code path covers both — but we validate and care about the local NDJSON backend now and defer DynamoDB-specific concerns (the `BatchWriteItem` batching and shared-filesystem invariant checks already sit under P0.2).
- Reuse the existing assembly hook points rather than inventing new ones: extend the graph-assembly step (`act_assemble_graph` / `assemble_graph_on_output`) or add a sibling at the same site.

## Readiness checklist

Green (exists, verified in code):

- Events from every worker land in one partition with `writer_id` disambiguation (P0 / T1, shipped).
- Cross-worker read-back proven end-to-end for graph (`read_events` → assembler → on `PipeOutput`, both modes).
- `UsageAggregator.aggregate`, `inject_tokens_usages`, `generate_report`, and `CostRegistry.generate_report(tokens_usages=...)` all present.
- Assembly hook points exist in both modes (`PipeRun.run` `finally`; `WfPipeRun.run` Step 2).

Decided (locked):

- **Mechanism: Option B** — ride usage on `PipeOutput`, remove the submitter registry.
- **Dedicated `--costs` / `is_generate_costs` switch** mirroring `--graph` / `is_generate_graph`, gating `UsageReportEvent` emission + `UsageAggregator` over the shared event-log transport.
- **`--costs` defaults ON.** Parity with `--graph` (default on); usage events are tiny and cost is money, so collect by default and accept the small always-on emission. `--no-costs` opts out.
- **`--cost-report` is folded into `--costs`.** `--costs` becomes the single master switch (collect + render); the existing `is_log_costs_to_console` / `is_generate_cost_report_file_enabled` config keys become the "which channel" (console / CSV) sub-controls applied when `--costs` is on. The old `--cost-report` / `--no-cost-report` flag is removed — no back-compat (per the development principles).
- **Single source of truth: events.** The live `_try_add_to_registry` accumulation and the submitter registry are removed; cost always comes from the aggregated event stream, so there is no double-counting to guard.
- **`PipeOutput` carries the assembled usage** (a `tokens_usages` list or typed cost summary) alongside `graph_spec`; the submitter renders from it (console / CSV per config) so the report reaches the caller in every mode — never generated on the worker's console.

Left to the implementation plan (mechanics, not direction):

- Exact field name/type for the usage artifact on `PipeOutput`; the config key (`is_generate_costs`) placement in `configs.py` + `pipelex.toml`; the `--costs` CLI flag wiring across the `run` subcommands and the agent CLI.
- Whether to extend `act_assemble_graph` / `assemble_graph_on_output` to also aggregate usage, or add a sibling at the same hook.
- The shared-transport split: emit `UsageReportEvent`s under `--costs` independently of `--graph`, and thread `--costs` to the Temporal worker (same plumbing `--graph` has).
- Removal cleanup: `inject_tokens_usages`, the `_get_or_create_registry` / `_get_registry_strict` / `_try_add_to_registry` trio, the `open_registry` call in `pipeline_run_setup`, and `start_pipeline`'s orphaned open in `pipelex-api`.

Dependency for cheap validation:

- **P0.1 (dry-run through activity dispatch)** — today `--dry-run` mocks inference *inside the workflow* and never dispatches the activity, so the cross-worker usage path can't be exercised without real LLM spend in a real multi-worker topology. A `--mock-inference` mode that dispatches the activity but mocks inside it is effectively a prerequisite for validating cross-worker cost reporting cheaply. Worth pulling in alongside this work.

## For the planning phase

The plan should turn the locked decisions above into a concrete, sequenced implementation. Scope to cover:

- **Config + flags:** add `is_generate_costs` (default `true`) to `pipeline_execution_config` in `configs.py` and `pipelex.toml`; add `--costs` / `--no-costs` to the `run` subcommands (main CLI + agent CLI); remove `--cost-report` / `--no-cost-report` and re-home `is_log_costs_to_console` / `is_generate_cost_report_file_enabled` as render-channel sub-controls.
- **Shared-transport split:** make `UsageReportEvent` emission fire under `--costs` independently of `--graph` (event log exists if either is on; each event type gated by its own flag); thread `--costs` to the Temporal worker.
- **Assembly + carry:** aggregate usage at the existing graph-assembly hook in both modes; add the usage field to `PipeOutput`; render the cost report on the submitter from that field.
- **Removals:** the live registry trio, `inject_tokens_usages`, the `open_registry` in `pipeline_run_setup`, and `start_pipeline`'s orphaned open — verifying nothing else reads the live registry (`cocode`'s no-id `generate_report` included).
- **Scope guard:** NDJSON-first; DynamoDB rides along for free via the backend-agnostic read-back but is not a validation target now.

Test surface to design:

- Success-path no-leak characterization (mirror the existing failure-path test in `test_pipeline_run_setup_characterization.py`): `_usage_registries` stays at baseline after a successful run.
- DIRECT `--costs` renders correct non-zero cost; DIRECT `--no-graph --costs` still renders (proves the decoupling); `--no-costs` emits no usage events and renders nothing.
- Cross-worker (parent on worker A, child on B, activity on C) → one aggregated end-of-run cost report (needs P0.1 or real spend).
- `pipelex-api` `/pipeline/execute` and `/pipeline/start` leave no registry behind across requests.

Constraints: no back-compat (just change it, note in changelog); run `make agent-check` + `make agent-test` before wrapping; consider whether to pull P0.1 in first so the cross-worker case is testable without LLM spend.

## What does NOT change from the earlier docs

The findings in the assessment and execution-contexts docs all still hold: the leak is real and unbounded on long-lived servers; `/pipeline/start` opens a registry that is pure dead weight; the worker never opens a registry; the caller-supplied-`pipeline_run_id` collision is a latent 500; `cocode`'s `generate_report()`-with-no-id re-reports leaked registries. Option B resolves all of these as a side effect of removing the submitter registry; Option A resolves them via the unconditional close plus the collision going away once ids are closed.
