# Phase 1 (emit decoupling) — review findings & altitude items

**Date:** 2026-06-06 · **Branch:** `fix/For-API-update` · **Reviewing:** the uncommitted Phase 1 implementation (CHECKPOINT 1 in [`../../TODOS.md`](../../TODOS.md)).

This captures a multi-angle code review of the Phase 1 changes so the discussion can resume cold. Phase 1 itself is green (`make agent-check` clean, targeted suites pass); the items below are correctness gaps, an efficiency regression, and altitude/design concerns the phased plan either deferred or didn't anticipate.

**Triage status (updated 2026-06-06):**

- **Applied now** (do-now bucket): **F2** — usage gate hoisted into the dispatcher `_emit_usage_event` so it guards both the fast path and the runner fallback (new tests `test_registered_context_{suppresses_usage_when_costs_off,emits_when_costs_on}`); the CP1 note in `TODOS.md` that assumed the fast path was safe is corrected. **F3** — docs method rename applied.
- **Folded into Phase 2** (checklist amended in `TODOS.md`, named so they can't slip): **A2** (thread emit flags into `open_tracer`, kill both `model_copy` footguns — do FIRST), **F1** (gate BOTH Temporal `graph_spec` sites on `emit_graph_events`), **E1-cheap** (gate `pipe_abstract` serialization on `emit_graph_events`).
- **Deferred** (recorded in `TODOS.md` §7): **A1** full factory, **E1-deep** costs-only tracer skip, **T5** pre-existing latent. **T1–T4** resolved by Phases 3–4; **T6** folds into Phase 2 test work.

---

## Context — what Phase 1 shipped, and where the gates live

Phase 1 decouples **cost-report emission** from **graph generation**. Before, usage (cost) trace events were only emitted as a side effect of `--graph` + tracing being on. Now there is a dedicated `is_generate_costs` config (default `true`) and a `--costs/--no-costs` CLI flag, independent of `is_generate_graph`/`--graph`, over the **shared event-log transport**.

The mechanism is a pair of booleans on `GraphContext` — `emit_graph_events` (driven by `is_generate_graph`) and `emit_usage_events` (driven by `is_generate_costs`) — that gate which event stream actually emits. The gating decisions are spread across **four files**:

- `pipeline_run_setup.py` (DIRECT) — opens the tracer when graph **or** costs is on; feeds the `event_log` to the tracer only when graph on (costs-only → `event_log=None`, tracer still mints node ids); registers the usage event-log (`set_event_log`) only when costs on; stamps the two flags onto the run's `GraphContext` via a post-hoc `model_copy`.
- `wf_pipe_router.py` (TEMPORAL) — re-derives the same decision for the per-workflow context.
- `reporting_manager.py` — the runner-side usage fallback early-returns on `not emit_usage_events`.
- `pipe_run.py` (DIRECT) — gates `assemble_graph_on_output` on `emit_graph_events` so `--no-graph` doesn't produce a node-less `GraphSpec` from usage-only events.

**The transitional state (by plan):** the live `UsageRegistry` still accumulates and is still the only thing rendered; `--cost-report`/`is_log_costs_to_console` still drive the console/CSV report from the registry. Phase 3 folds `--cost-report` into `--costs` and cuts the renderer to `PipeOutput`; Phase 4 removes the registry. Several findings below are artifacts of that transition — flagged so they're not forgotten, not necessarily fixed now.

---

## The structural theme (read this first)

**The gating got spread across four files, and the TEMPORAL arm was not held to the same `--no-graph` contract as the DIRECT arm.** I added the `--no-graph` gate to DIRECT (`pipe_run.py:75`) during Phase 1 to stop a costs-only run from emitting a graph; the TEMPORAL path has no equivalent. The same `(graph, costs) → (event_log routing, set_event_log, emit-flags)` decision is computed twice (DIRECT in `pipeline_run_setup`, TEMPORAL in `wf_pipe_router`) with near-identical logic — and it has **already drifted**. Findings F1, A1, A2 are all facets of this one root cause. The cleanest resolution is to give the decision a single owner (a `GraphContext` factory both modes call, and/or thread the flags into `open_tracer`) rather than keep patching each arm.

---

## Correctness findings (resolve with / before Phase 2)

### F1 — TEMPORAL `--no-graph --costs` still produces a non-None `graph_spec`
- **Where:** `wf_pipe_router.py:155-157` (`close_tracer` → `pipe_output.graph_spec = graph_spec`, no `emit_graph_events` gate) **and** `wf_pipe_run.py:90-91` (`act_assemble_graph` overwrites `graph_spec` from trace events).
- **Why it's real:** `GraphTracer.on_pipe_start` accumulates nodes in-memory regardless of `event_log` (the `if self._event_log is not None` guard only gates *emission*). So in costs-only mode `close_tracer` returns a fully-populated `GraphSpec` and line 157 assigns it unconditionally. Even with that gated, `wf_pipe_run` Step 2 reads the run's usage-only events and `GraphSpecAssembler.assemble` builds a **node-less but non-None** `GraphSpec` that overwrites it. Either way `pipe_output.graph_spec` is non-None under `--no-graph`, whereas DIRECT correctly yields `None`.
- **Severity:** real Phase-1-introduced asymmetry; **Temporal is not shipped to prod**, so no live impact today — but it's the exact bug I gated in DIRECT, left ungated in TEMPORAL.
- **Direction:** gate the router's `graph_spec` assignment on `emit_graph_events`, AND gate the `act_assemble_graph` dispatch in `wf_pipe_run` on `emit_graph_events`. The latter overlaps Phase 2's D3 ("`act_assemble_graph` → `TracingAssemblyResult`, gate on `emit_graph_events`"), so this naturally folds into Phase 2 — just make sure Phase 2 closes it, or gate it now for symmetry.

### F2 — Usage fast-path lacks the `emit_usage_events` gate
- **Where:** `reporting_manager.py` — gate is only in `_emit_usage_event_runner_fallback` (`:316`), not in the fast path `_emit_via_registered_context` (`:265`). Dispatch is `_emit_usage_event` (`:237`, branches at `:255`).
- **Why it's real:** correctness relies on the cross-file invariant "a context is registered (`set_event_log`) only when costs on", which nothing tests. `_event_log_contexts` is a process-wide singleton and `clear_event_log` is best-effort in `finally` blocks. If a prior costs-enabled run's `clear_event_log` was skipped (teardown raised) and a later graph-only run reuses/collides on the same `lookup_key` — possible via the API's explicit `pipeline_run_id` param, or Temporal `workflow_id` reuse — the fast path emits `UsageReportEvent`s despite `emit_usage_events=False`.
- **Severity:** affects the shipped DIRECT/API path; trigger is narrow (requires a leaked context + id reuse). Plausible, not yet observed.
- **Direction:** hoist `if not graph_context.emit_usage_events: return` into `_emit_usage_event` (before the context lookup, ~`:251`), so both paths are guarded and the "unreachable fast path" reasoning stops being load-bearing. ~2 lines.

### F3 — Stale docs reference the renamed method
- **Where:** `docs/under-the-hood/execution-graph-tracing.md:69` and `:79` still call `config.with_graph_config_overrides(...)`.
- **Why it's real:** the method was renamed to `with_execution_overrides`; these are the only non-test, non-planning references to the old name left in the tree. A reader copy-pasting the example hits `AttributeError`. Kwargs (`generate_graph`, `mock_inputs`) are unchanged — name-only fix.
- **Severity:** trivial; public docs are the API contract.

---

## Efficiency

### E1 — Costs-only mode pays full per-pipe graph serialization, then discards it
- **Where:** `pipe_abstract.py:471-498` — the IOSpec/registry capture block runs whenever `graph_context is not None`, with per-field serialization gated on `data_inclusion.*` (default all-true), **not** on `emit_graph_events`.
- **Why it's real:** in costs-only mode the in-memory tracer is opened (D5), so this block runs `smart_dump()` + `rendered_pretty_text()` + `rendered_pretty_html()` per input stuff and `model_dump(mode="json")` per pipe — building a `GraphSpec` that `pipe_run.py:75` then discards (DIRECT) or that `act_assemble_graph` replaces with a node-less one (TEMPORAL). On large stuffs (documents, image data-URLs) this is the dominant per-pipe cost, paid for zero output.
- **vs the old world:** old `--no-graph` opened **no tracer at all** → zero cost. So costs-default-on makes every `--no-graph` run more expensive than before.
- **Severity:** real regression for the common "cost tracking without graphs" case. The plan named this a deferred optimization ("skip the in-memory tracer in costs-only mode") but framed it as cheap node-id minting; the true cost is full serialization.
- **Direction:** either skip the in-memory tracer in costs-only mode (the deferred D5 optimization), or gate the data-inclusion serialization on `emit_graph_events`. Worth doing once `tokens_usages` rides on `PipeOutput` (Phase 2) and the graph path is the only consumer of the in-memory tracer.

---

## Altitude / design (fold into Phase 2 thinking)

### A1 — The DIRECT/TEMPORAL gating decision has no single owner and has already drifted
- The `(graph, costs) → (event_log, set_event_log, flags)` policy lives in both `pipeline_run_setup` and `wf_pipe_router` with subtly different control flow; F1 is the proof it drifted. Phase 2 ("assemble usage onto `PipeOutput`") will have to touch both arms again.
- **Direction:** give the decision one home — e.g. a `GraphContext.from_execution_config(...)` factory both modes call, so "what does this run emit" is computed once. This is the deepest fix and would subsume F1 and A2.

### A2 — Emit flags are stamped via post-hoc `model_copy`, not set at construction
- **Where:** `pipeline_run_setup.py:210` and `wf_pipe_router.py:101` both `model_copy(update={...})` the flags **after** `open_tracer` returns a `GraphContext` with both flags defaulting to `True` (field defaults in `graph_context.py`; built in `graph_tracer.setup`).
- **Why it matters:** every caller must remember the second copy or silently re-enable both streams. `wf_pipe_router`'s own comment documents the footgun. Default-`True` makes the safe behavior opt-in rather than derived.
- **Direction:** thread `emit_graph_events`/`emit_usage_events` as params into `open_tracer`/`tracer.setup` so the context is correct at birth — eliminates two redundant `model_copy`s and the footgun. (Couples naturally with A1.)

---

## Lower-priority / transitional (don't lose, don't rush)

- **T1 — `--no-costs` doesn't suppress the registry-based report.** `_run_core.py:294`: the console/CSV report is fed by the always-on registry and gated only on the old `cost_report` flag, independent of `is_generate_costs`. `--no-costs --cost-report` (or `--no-costs` with `is_log_costs_to_console=true`) still prints costs. Transitional — Phase 3 folds `--cost-report` into `--costs` and resolves it. No test pins the combination today.
- **T2 — Agent CLI `--costs` is currently inert + help overpromises.** `agent_cli/.../_run_core.py`: the agent CLI never renders a cost report in Phase 1, so `--costs` only toggles emission/assembly. Help text says "Enable cost reporting (usage collection + end-of-run cost report)". Phase 2/3 make it meaningful; soften the help text until then.
- **T3 — Agent CLI `costs: bool = True` always overrides config.** `agent_cli/.../pipe_cmd.py:49` (and bundle/method): non-Optional, so a project's `is_generate_costs=false` can't take effect for agent runs. Mirrors the agent CLI's existing `--graph=bool=True` behavior, so it's consistent with that surface — but the same flag name has different config-override semantics across the two CLIs.
- **T4 — `is_generate_costs=true` + `tracing_config.is_enabled=false` silently drops usage events.** `pipeline_run_setup.py:228`: `event_log` is only created when tracing is enabled, so the event-sourced cost path yields nothing with no warning. Low impact in Phase 1 (the registry/console path doesn't need tracing); becomes a real silent dependency once cost reporting is sourced from `PipeOutput` events.
- **T5 — `wf_pipe_router` setup-failure `except` doesn't restore `job_metadata.graph_context`.** `wf_pipe_router.py:122`: on a tracing-setup failure after `job_metadata` was replaced (`:101`), the pipe runs with a `graph_context` whose `tracer_key` points at a closed tracer. Pre-existing latent issue (not introduced here, Temporal not shipped); flag-and-fix candidate.
- **T6 — Test helper duplication.** `tests/unit/pipelex/reporting/test_emit_usage_event_gating.py` re-defines `_make_llm_job` / `_make_graph_context` / `_enable_ndjson_tracing` / `DATA_INCLUSION_OFF` already present in sibling `test_emit_runner_fallback.py`; no `conftest.py` in that dir. The graph conftest factory (`tests/unit/pipelex/graph/conftest.py`) also wasn't updated for the two new `GraphContext` fields. Hoist shared helpers; extend the conftest factory with the emit flags.

---

## Refuted / verified-clean (so the cold-start session doesn't re-litigate)

- **Not a bug:** `graph_rendering.py` / `dry_run_pipeline.py` "now silently enable costs" — these are `generate_graph=True` paths; the *old* `pipeline_run_setup` already created the event_log and called `set_event_log` when graph was on, so usage emission was already happening (and they're DRY runs anyway). No behavior change.
- **Verified clean:** `is_generate_costs` is required-no-default, but no code constructs `PipelineExecutionConfig(...)` directly (all via config-load / `model_copy`); all three TOMLs carry the key; `make tb` + targeted suites pass. The `is not None` override logic correctly distinguishes `--no-costs` (force off) from omitted (defer to config). The DIRECT `--no-graph` gate is correct and `graph_context` is never `None` when graph is on.

---

## Suggested sequencing for the discussion

1. **Quick, contained, do-now:** F2 (hoist the usage gate to the dispatcher) and F3 (docs rename). Both are small and unambiguous.
2. **Decide deliberately:** F1 + E1 + A1 + A2 are one cluster — they argue for consolidating the emit decision into a `GraphContext` factory / `open_tracer` params, and for gating the TEMPORAL graph path. Phase 2 already reopens both the assembly hook (DIRECT + TEMPORAL) and the `PipeOutput` shape, so this is the natural place to land the consolidation rather than patch each arm again. Open question to settle: do A1/A2 happen *as part of* Phase 2, or as a small pre-Phase-2 refactor so Phase 2 builds on the single-owner shape?
3. **Park as transitional:** T1–T4 are resolved or made moot by Phases 3–4; T5 is pre-existing; T6 is cleanup. Track them, don't gate Phase 2 on them.
