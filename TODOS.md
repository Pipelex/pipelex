# Implementation plan — `UsageRegistry` leak fix + distributed cost-report aggregation (Option B)

**Branch:** `fix/For-API-update` · **Status:** PLAN (not started — no code yet)

**Design source (locked):** [`wip/registry/registry-lifecycle-synthesis.md`](wip/registry/registry-lifecycle-synthesis.md) → "For the planning phase". Companion: [`wip/distributed-execution/tracing-cost-reporting.md`](wip/distributed-execution/tracing-cost-reporting.md) (T2/P1), [`wip/distributed-execution/README.md`](wip/distributed-execution/README.md) (P0.1/P1).

This doc turns the locked decisions into a sequenced, checkpointed implementation. **Line numbers below are indicative (branch at time of writing); the symbol names are the durable anchors.**

---

## 0. What we are building, in one screen

The `UsageRegistry` is a per-run, in-process cost buffer with lifecycle **open → populate → report → close**. Two problems are one lifecycle:

- **The leak** = the *close* never happens on the success path (registry opened in `pipeline_run_setup`, closed only on failure).
- **Distributed cost reporting (T2/P1)** = the cross-worker *replay-populate* is never wired (events land in the backend, never become a report).

**Option B (locked) resolves both by removal:** usage rides on `PipeOutput` like `graph_spec` does — assembled from the trace-event stream at the end of the run, in both DIRECT and TEMPORAL modes — and the **submitter** renders the cost report from that field. With nothing populating a submitter-side registry, the registry is removed entirely; the leak becomes structurally impossible and `inject_tokens_usages` + the live-add trio retire.

**The load-bearing decoupling:** today usage events are only emitted when `--graph` + tracing are on (the event log is created inside `if is_generate_graph`). Once the live registry is gone, `--no-graph` would lose cost. So we add a dedicated, default-on **`--costs` / `is_generate_costs`** switch (mirrors `--graph` / `is_generate_graph`) over the **shared event-log transport**: `--graph` gates graph (node/edge) events + `GraphSpecAssembler`; `--costs` gates `UsageReportEvent`s + `UsageAggregator`. Each rides its artifact back on `PipeOutput`. `--cost-report` is folded into `--costs` (removed; no back-compat).

---

## 1. Decisions this plan makes (forks the synthesis left to planning)

These are decided here so implementation is unambiguous. Each is open to veto at plan review.

- **D1 — P0.1 sequencing: core cost work FIRST (pytest-validated, no spend), then P0.1, then skill upgrade.** The leak fix + cross-worker cost aggregation is the primary deliverable and is fully validatable deterministically without `--mock-inference`: the existing `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` already substitutes the inference activity with a server-side wrapper that synthesizes a real `LLMJob` cross-process — we extend that exact pattern to assert assembled cost. P0.1 (`--mock-inference`) is only needed for **CLI-level** (3-process `pipelex run bundle`) cheap cross-worker validation, which is exactly what the **skill upgrade** consumes — so P0.1 is sequenced as the bridge into the skill upgrade (Phase 5), not the critical path's start. *If you prefer the cheap CLI harness available from day one, P0.1 reorders cleanly to Phase 1 — it has no dependency on the cost work.*
- **D2 — Usage artifact on `PipeOutput`: `tokens_usages: list[AnyTokensUsage] | None = None` + `usage_assembly_error: str | None = None`.** Literal mirror of `graph_spec` / `graph_assembly_error`. `AnyTokensUsage` is already a discriminated union of pydantic `BaseModel`s, already serialized in `UsageReportEvent` through the event-log backend → safe across the Temporal boundary and through the `StoragePayloadCodec`. The submitter renders with the existing `CostRegistry.generate_report(tokens_usages=...)` which already takes a usage list. (Rejected: a pre-computed cost summary — less flexible, duplicates the renderer.)
- **D3 — One generalized assembly hook, single event read → both artifacts.** Generalize the existing graph hook to read the event stream once and feed it into **both** `GraphSpecAssembler` (if `--graph`) and `UsageAggregator` (if `--costs`). DIRECT: `assemble_graph_on_output` → `assemble_tracing_on_output` (or keep name, add usage). TEMPORAL: `act_assemble_graph` → returns a small `TracingAssemblyResult{graph_spec, tokens_usages}`; `WfPipeRun.run` Step 2 sets both on `pipe_output`. Rationale: the events are read once and aggregating usage is trivial (`[e.tokens_usage for e in events if isinstance(e, UsageReportEvent)]`); a second activity dispatch / event read is wasted latency + history. *Lower-risk fallback if the proven graph path must stay byte-for-byte untouched: an additive sibling `act_assemble_usage` / `assemble_usage_on_output` that does its own read. Documented; not chosen.*
- **D4 — Thread the two gates to the worker on the tracing context (`GraphContext`).** Add `emit_graph_events: bool` and `emit_usage_events: bool` to `GraphContext` (already serialized through `JobMetadata`, already the per-run tracing context). The worker (`WfPipeRouter.run`) reads them to decide whether to wire the tracer's event log (graph) and whether to `set_event_log` on the report delegate (usage); the assembly step reads them to decide what to assemble. Today the *presence* of `graph_context` threads the single graph bit — now the context is present whenever **graph OR costs** is on, and the two booleans say which. (Rejected: new `JobMetadata` fields — the context is the natural home.)
- **D5 — In costs-only mode (`--no-graph --costs`), still open the tracing context but pass `event_log=None` to the graph tracer.** The tracer accumulates the in-memory graph (cheap, never assembled/output when graph off) and keeps minting node ids; graph **events** are suppressed (emission is guarded by `self._event_log is not None` in `graph_tracer.py`); the usage event-log context is registered via `set_event_log` so usage events emit. This keeps `GraphContext` as the single keying mechanism for both event types (the report delegate's `_event_log_contexts` is keyed by `graph_context.lookup_key`) and avoids a deep refactor of the delegate's keying. *Deferred optimization: skip the in-memory tracer entirely in costs-only mode.*
- **D6 — Channel model (DECIDED).** `--costs` (default ON) = collect + assemble + render-eligibility. `is_generate_cost_report_file_enabled` gates the CSV channel; `is_log_costs_to_console` gates the console channel — applied **only when `--costs` is on** (synthesis's "which channel" framing). Remove the per-inference-job live console logging in `_report_*_job` (worker-side noise; the synthesis says the report is rendered submitter-side, never on the worker's console) and let `is_log_costs_to_console` mean the **end-of-run** console channel. **Decided (user-confirmed): flip `is_log_costs_to_console` default `false → true`** in `pipelex/pipelex.toml` **and** `.pipelex/pipelex.toml`, so the CLI shows the cost table by default when `--costs` is on — parity with `--graph` producing visible output by default. Library embedders who don't want console spam set it false. (Applied in Phase 3.)
- **D7 — P0.1 `--mock-inference` is an orthogonal signal, not a new `PipeRunMode` enum value.** Adding a `PipeRunMode` member forces an exhaustive-`match`/`case` burn-down across the codebase (python standards forbid `case _`). Instead carry a boolean (e.g. `is_mock_inference` on the run params that already thread to the worker alongside `run_mode`): the operator treats it as LIVE for **dispatch** (the activity IS scheduled), and the **activity body** swaps in `ContentGeneratorDry` when the flag is set. Lower blast radius, no enum-exhaustiveness churn.

---

## 2. Current architecture — anchors to edit (compact reference)

**Registry + reporting (`pipelex/reporting/`):**

- `reporting_manager.py` — `ReportingManager` (process singleton via `hub.get_report_delegate()`):
  - `_usage_registries: dict[str, UsageRegistry]` (`~:61`), `_event_log_contexts: dict[str,_EventLogContext]` (`~:64`) — keyed by `graph_context.lookup_key`.
  - `setup` (`~:102`, seeds `UNTITLED`), `open_registry` (`~:216`, raises on dup), `close_registry` (`~:393`, idempotent `pop`).
  - Live trio: `_get_registry_strict` (`~:115`), `_get_or_create_registry` (`~:126`), `_try_add_to_registry` (`~:137`).
  - `inject_tokens_usages` (`~:223`) — **zero production callers**.
  - `_report_llm_job`/`_report_img_gen_job`/`_report_extract_job`/`_report_search_job` (`~:152-210`) — each: `_try_add_to_registry` + `_emit_usage_event` + per-job console log gated by `is_log_costs_to_console`.
  - `_emit_usage_event` (`~:237`): `graph_context is None → return`; fast path `_emit_via_registered_context` (`~:264`) when `_event_log_contexts[lookup_key]` exists; else `_emit_usage_event_runner_fallback` (`~:285`, gated only by `tracing_config.is_enabled`).
  - `set_event_log` (`~:71`) / `clear_event_log` (`~:92`) — **keep** (the usage transport).
  - `generate_report` (`~:365`) — iterates registries; renders via `CostRegistry.generate_report(...)`.
- `reporting_protocol.py` — `ReportingProtocol` + `ReportingNoOp` (update in lockstep with any surface change).
- `reporting_types.py` — `AnyTokensUsage = Annotated[LLMTokensUsage|ImgGenTokensUsage|ExtractTokensUsage|SearchTokensUsage, Field(discriminator="model_type")]` (all pydantic `BaseModel`).
- `pipelex/cogt/usage/cost_registry.py` — `CostRegistry.generate_report(pipeline_run_id, tokens_usages, unit_scale, cost_report_file_path=None, print_to_console=True)` (`~:38`) renders Rich table + optional CSV directly from a usage list. `complete_cost_report` (`~:257`).
- `pipelex/tracing/usage_aggregator.py` — `UsageAggregator.aggregate(events) -> list[AnyTokensUsage]` (the `GraphSpecAssembler.assemble` analogue).
- `pipelex/tracing/trace_events.py` — `UsageReportEvent(TraceEvent){ node_id, tokens_usage }` (`~:162`).

**Lifecycle / gating:**

- `pipelex/pipeline/pipeline_run_setup.py` — event-log + tracer created inside `if execution_config.is_generate_graph:` (`~:184-200`); `make_event_log` (`~:189`); `open_registry` + `registry_opened=True` (`~:209-210`); `set_event_log` if `event_log is not None` (`~:213-219`); `finally` gates all cleanup behind `if not success:` incl. `close_registry` (`~:264-281`) — **this asymmetry is the leak.**
- `pipelex/pipeline/runner.py` — `PipelexRunner.execute_pipeline` (`~:77`); finally closes tracer `if is_generate_graph` (`~:205`), `clear_event_log` (`~:212`), library teardown — **never closes the registry** (the forgotten resource). Returns `PipelexPipelineExecuteResponse.from_pipe_output(pipe_output, ...)` (`~:237`). `start_pipeline` raises `NotImplementedError` here (`~:255`) — the API has its own.
- `pipelex/pipe_run/pipe_run.py` — DIRECT `PipeRun.run` finally → `assemble_graph_on_output(pipe_output, pipeline_run_id, domain_code, main_pipe_code)` (`~:70-76`). Runs in the submitter process.
- `pipelex/pipe_run/graph_assembly.py` — `assemble_graph_on_output` (`~:22`): gate `if not tracing_config.is_enabled: return`; `make_event_log` → `read_events` → `GraphSpecAssembler.assemble` → sets `pipe_output.graph_spec`.
- `pipelex/temporal/tprl_pipe/act_assemble_graph.py` — `act_assemble_graph(AssembleGraphArg{pipeline_run_id,domain_code,main_pipe_code}) -> GraphSpec|None` (`~:29`).
- `pipelex/temporal/tprl_pipe/wf_pipe_run.py` — Step 2 dispatches `act_assemble_graph`, sets `pipe_output.graph_spec` / `pipe_output.graph_assembly_error` (`~:76-94`).
- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py` — `TemporalPipeRun.run` (`~:47-88`) returns `rehydrate_pipe_output_with_crate(pipe_output, crate)`.
- `pipelex/temporal/tprl_pipe/wf_pipe_router.py` — per-workflow tracing gated `if tracing_config.is_enabled and graph_context is not None:` (`~:75-127`): `BufferingEventLog` → `open_tracer(event_log=...)` + `set_event_log(...)`; finally drains via `act_flush_trace_events` + `clear_event_log` (`~:151-171`).
- `pipelex/graph/graph_context.py` — `GraphContext` (`~:12`); `lookup_key = tracer_key or graph_id` (`~:34`). **D4 adds the two flags here.**
- `pipelex/graph/graph_tracer.py` — every graph event emit guarded by `if self._event_log is not None:` (`~:620,671,731,774,815,857,469`). (D5 relies on this.)
- `pipelex/system/configuration/configs.py` — `PipelineExecutionConfig` (`~:153`, holds `is_generate_graph`, `with_graph_config_overrides` `~:163`); `ReportingConfig` (`~:94`, holds `is_log_costs_to_console`, `is_generate_cost_report_file_enabled`); `TracingConfig` (`~:123`, `is_enabled` master flag).

**CLI surfaces:**

- Main CLI `run`: `pipelex/cli/commands/run/{pipe_cmd,method_cmd,bundle_cmd}.py` declare `--graph/--no-graph` and `--cost-report/--no-cost-report`; `_run_core.py` `with_graph_config_overrides(generate_graph=graph,...)` (`~:145`) and the post-run `generate_report(pipeline_run_id=..., print_to_console=...)` (`~:289-301`, gated by `cost_report`/`is_log_costs_to_console`/`is_generate_cost_report_file_enabled`).
- Agent CLI `run`: `pipelex/cli/agent_cli/commands/run/...` — has `--graph/--no-graph` only; **no `--cost-report`, never calls `generate_report`** (`with_graph_config_overrides` `~:51`, graph output `~:103-146`).

**Cross-repo consumers:**

- `cocode/cocode/swe/swe_cmd.py` — `get_report_delegate().generate_report()` with **no** `pipeline_run_id` (multiple sites). Re-reports all (leaked) registries → must migrate to render from its returned `pipe_output.tokens_usages`.
- `pipelex-api` — `/pipeline/execute` → `ApiRunner.execute_pipeline`; `/pipeline/start` → `ApiRunner.start_pipeline` calls `pipeline_run_setup` **directly** (the "orphaned open"). No registry calls of its own; `PipelexPipelineExecuteResponse` wraps `pipe_output` (so D2's field is auto-exposed). Leak vanishes once `pipeline_run_setup` stops opening.

---

## 3. Phased plan (keep the tree green at every checkpoint)

Build the new event-driven path alongside the old live registry, cut the renderers over, then delete the old. At no point are both summed (no double-count): the old path renders from the registry, the new from `PipeOutput`; only one renderer is active at a time.

### Phase 1 — Decouple emission: shared transport, two independent gates

- [ ] Add `is_generate_costs: bool` to `PipelineExecutionConfig` (`configs.py`), default in `pipelex/pipelex.toml` `[pipelex.pipeline_execution_config]` = `true`; mirror in `.pipelex/pipelex.toml` (real value, never commented).
- [ ] Generalize `with_graph_config_overrides` → `with_execution_overrides(generate_graph=None, generate_costs=None, force_include_full_data=None, mock_inputs=None)` (update its callers: main `_run_core.py`, agent `_run_core.py`, `ApiRunner`, characterization-test helpers).
- [ ] Add `--costs/--no-costs` typer option to all three main `run` subcommands + agent CLI subcommands; thread `costs` into `with_execution_overrides(generate_costs=costs)`. (Leave `--cost-report` in place for now — removed in Phase 3.)
- [ ] Add `emit_graph_events: bool` + `emit_usage_events: bool` to `GraphContext` (D4).
- [ ] `pipeline_run_setup.py`: broaden the gate `if is_generate_graph:` → `if is_generate_graph or is_generate_costs:`; create `event_log` when `tracing_config.is_enabled`; `open_tracer(event_log=event_log if is_generate_graph else None, ...)` (D5); set `emit_graph_events`/`emit_usage_events` on the context; call `set_event_log(...)` only when `is_generate_costs` (not merely "event_log is not None").
- [ ] `runner.py` finally: broaden tracer-close gate to `is_generate_graph or is_generate_costs`.
- [ ] `reporting_manager.py` `_emit_usage_event_runner_fallback`: add early-return `if not graph_context.emit_usage_events: return` (so graph-only mode does **not** emit usage via the runner fallback). Confirm the fast path is only reachable when costs on (it is — `set_event_log` only called when costs on).
- [ ] `wf_pipe_router.py`: keep the `graph_context is not None` gate (context now present when graph OR costs); inside, wire the tracer event log only when `emit_graph_events`, and `set_event_log` only when `emit_usage_events`.
- [ ] **Tests:** unit/integration that with `--no-graph --costs` (DIRECT) `UsageReportEvent`s ARE emitted and no graph events are; with `--graph --no-costs` graph events emitted and NO usage events (incl. runner fallback path); default (`--costs` on) unchanged. The live registry still accumulates — no renderer change yet.
- [ ] `make agent-check` + targeted tests (`tests/integration/pipelex/pipeline/`, `tests/unit/pipelex/reporting/`, `tests/integration/pipelex/temporal/tracing/`, `make tb` for the config/TOML touch).

> **🔶 CHECKPOINT 1 — transport decoupled.** Update §6 cold-start notes: confirm event emission now keys off `is_generate_costs` independent of `--graph`, in both modes; list any match/case or gate sites discovered beyond the inventory above. The registry is still live and still the only thing rendered.

### Phase 2 — Assemble usage onto `PipeOutput` (additive; nothing removed)

- [ ] `pipe_output.py`: add `tokens_usages: list[AnyTokensUsage] | None = None` + `usage_assembly_error: str | None = None` (D2). Verify `prepare_for_temporal` / `rehydrate_pipe_output_with_crate` carry them (they're plain serializable fields, but confirm the dehydrate path doesn't drop them).
- [ ] DIRECT: generalize `graph_assembly.py` so the single `read_events` feeds both `GraphSpecAssembler` (if context `emit_graph_events`) and `UsageAggregator.aggregate` → `pipe_output.tokens_usages` (if `emit_usage_events`); top gate becomes `is_enabled and (graph or costs)` (D3, D5). Best-effort try/except mirrors the graph path; failures set `usage_assembly_error`.
- [ ] TEMPORAL: `act_assemble_graph` → returns `TracingAssemblyResult{graph_spec, tokens_usages}` (read once); `WfPipeRun.run` Step 2 sets both on `pipe_output` (+ `usage_assembly_error` on `ActivityError`). Update `AssembleGraphArg`/activity name + worker activity registration (note rename blast radius: skill refs, tests).
- [ ] **Tests (no spend):** extend `test_split_worker_usage.py` pattern → assert `pipe_output.tokens_usages` is populated and non-empty after a cross-worker (router+runner) run, and that the aggregated total matches the emitted events. DIRECT integration: `pipe_output.tokens_usages` populated and equals the live registry's contents (fidelity cross-check).
- [ ] `make agent-check` + targeted temporal + pipeline tests.

> **🔶 CHECKPOINT 2 — usage rides on `PipeOutput` in both modes.** Cold-start notes: record the assembly hook's final shape (generalized vs sibling), the activity rename, and the cross-worker pytest that proves aggregation without spend. Old registry path still renders; PipeOutput field populated in parallel.

### Phase 3 — Cut renderers over to `PipeOutput`; re-home channel configs; remove `--cost-report`

- [ ] Main `_run_core.py`: replace the post-run `get_report_delegate().generate_report(pipeline_run_id=...)` with rendering from `response.pipe_output.tokens_usages` via `CostRegistry.generate_report(tokens_usages=..., unit_scale=reporting_config.cost_report_unit_scale, cost_report_file_path=<if csv enabled>, print_to_console=<console channel>)`, gated by the resolved `is_generate_costs`. Channels per D6.
- [ ] Remove `--cost-report/--no-cost-report` from the three main subcommands (no back-compat; changelog).
- [ ] Agent CLI: add equivalent cost rendering from `pipe_output.tokens_usages` (gated by `is_generate_costs`).
- [ ] **D6 (decided):** flip `is_log_costs_to_console` default `false → true` in `pipelex/pipelex.toml` **and** `.pipelex/pipelex.toml` (run `make tb` after). Remove the per-job live console logging in `_report_*_job` (the `is_log_costs_to_console` checks there) and re-point that key to the end-of-run console channel.
- [ ] **cocode (cross-repo):** migrate every `swe_cmd.py` `generate_report()` to `CostRegistry.generate_report(tokens_usages=<pipe_output.tokens_usages>, ...)`; bump the `pipelex` pin. (Will break at call time otherwise — expected, per no-back-compat.)
- [ ] **Tests:** CLI cost table still prints correct non-zero totals (DIRECT); `--no-costs` prints nothing and emits no usage events; numbers from PipeOutput match the (still-present) registry for the same run.
- [ ] `make agent-check` + CLI tests (`tests/...cli/`) + pipeline tests; in cocode, its own suite against the new pin.

> **🔶 CHECKPOINT 3 — rendering is event-sourced; `--cost-report` gone; D6 applied (`is_log_costs_to_console` now defaults `true`).** Cold-start notes: confirm the only cost renderer is `CostRegistry.generate_report(tokens_usages=...)` fed from `PipeOutput`, the live registry is now unused by any renderer, both TOMLs flipped + `make tb` green, and cocode's migration + pin bump status. This is a natural handoff boundary (a coherent unit landed; the next phase opens a new area — deletion).

### Phase 4 — Remove the live registry + dead code (the leak vanishes structurally)

- [ ] `reporting_manager.py`: delete `_usage_registries`, `open_registry`, `close_registry`, `_get_registry_strict`, `_get_or_create_registry`, `_try_add_to_registry`, `inject_tokens_usages`, and `generate_report` (or reduce to a thin `tokens_usages`-list passthrough if any caller still needs the delegate — prefer full removal). Strip `_try_add_to_registry` from `_report_*_job` (keep `_emit_usage_event`). Update `setup` (no `UNTITLED` seed needed).
- [ ] `reporting_protocol.py`: drop the removed methods from `ReportingProtocol` and `ReportingNoOp`; keep `set_event_log`/`clear_event_log`/`report_inference_job`/`setup`/`teardown`. Update every `@override`.
- [ ] `pipeline_run_setup.py`: remove `open_registry` + `registry_opened` + the `close_registry` in `finally` (**the leak fix**). Keep the event-log `set_event_log`/`clear_event_log` and tracer cleanup.
- [ ] `pipelex/pipeline/bundle_validator.py` (`~:241,248`): remove the per-sweep `open_registry`/`close_registry` (verify the dry-run sweep reads nothing from a registry — it shouldn't once `_try_add_to_registry` is gone).
- [ ] `tests/conftest.py` (`~:182,189`): remove the `open_registry`/`close_registry` fixture wiring.
- [ ] Characterization test `tests/integration/pipelex/pipeline/test_pipeline_run_setup_characterization.py`: delete `test_failure_after_open_registry_closes_registry` + `test_failure_before_open_registry_does_not_close_registry`; **add** the success-path no-leak case — a successful run through `execute_pipeline` leaves the `ReportingManager` with no accumulated per-run state (`_event_log_contexts` empty; assert `_usage_registries` attribute no longer exists).
- [ ] **Tests:** `pipelex-api` `/pipeline/execute` + `/pipeline/start` leave no per-run state across successive requests on a persistent app; reusing a `pipeline_run_id` on `/pipeline/start` no longer 500s (the `open_registry`-on-dup path is gone). cocode multi-run process no longer re-reports prior runs.
- [ ] **Full `make agent-test`** (this touches shared run/teardown + `hub`/reporting surface — full suite, not targeted) + `make agent-check`.

> **🔶 CHECKPOINT 4 — leak fixed by removal; cost reporting event-sourced end to end (DIRECT + cross-worker via pytest).** This is the primary deliverable landed. Cold-start notes: list every deleted symbol + every updated implementer of `ReportingProtocol`, the new characterization assertion, and confirm full suite green. Commit boundary.

### Phase 5 — P0.1: `--mock-inference` (cheap cross-worker validation affordance)

- [ ] Add `is_mock_inference` signal on the run params that already thread to the worker alongside `run_mode` (D7); add `--mock-inference` to the `run` subcommands (distinct from `--dry-run`).
- [ ] At the dry-mock sites (`pipe_llm.py ~:515`, and the equivalents in `pipe_extract.py`, `pipe_compose.py`, `pipe_img_gen.py`): when `is_mock_inference`, **dispatch the activity** (don't instantiate `ContentGeneratorDry` pre-dispatch); inside the activity body (`act_llm_gen_text` / `act_extract_*` / `act_img_gen_images` / compose) use `ContentGeneratorDry` when the flag is set.
- [ ] **Tests:** a router+runner run with `--temporal --mock-inference` produces `wf_*__w_act_{pid}_{uuid}.ndjson` (runner-side `writer_id=act_*`) deterministically and a non-empty assembled `tokens_usages` — no LLM spend.
- [ ] `make agent-check` + temporal tests.

> **🔶 CHECKPOINT 5 — cheap cross-process inference mocking works.** Cold-start notes: the flag's name + threading path, the four mock sites touched, and the deterministic NDJSON evidence command. Independent of Phases 1–4's correctness; gates the skill's cheap arm.

### Phase 6 — Upgrade the `temporal-e2e-validate` skill to validate distributed cost reporting

- [ ] `references/mode-2-tiers.md`: add **Tier 8b — Cross-worker cost report assembly**. Using the split router+runner workers + `--mock-inference` (Phase 5) so it's free and deterministic: run a multi-worker bundle with `--temporal --mock-inference --no-logo --costs`, then assert the submitter renders a **single** end-of-run cost report whose usage came from all workers (router + runner; for parent/child, A+B+C). Capture the NDJSON (`writer_id` set incl. `act_*`) and the rendered total. Add a **live arm** (real spend, opt-in) mirroring Tier 8's live block for the real-payload case.
- [ ] Add a `--no-costs` negative check: emits no `usage_report` events and renders no table.
- [ ] `SKILL.md` + `references/mode-2-tiers.md` Step 7 master table: add the Tier 8b row(s); update the description/trigger text to mention cost-report validation. Fix any `act_assemble_graph` references touched by the Phase-2 rename.
- [ ] Reconcile the existing Tier 8 note ("dry-run does NOT exercise this path") to point at `--mock-inference` as the cheap deterministic way (it previously said integration-test or live only).

> **🔶 CHECKPOINT 6 — skill validates distributed cost reporting cheaply + live.** Cold-start notes: the new tier's exact commands, the assertion of a single aggregated report, and which references changed.

### Phase 7 — Docs, changelog, wrap

- [ ] CHANGELOG `[Unreleased]`: `--costs`/`--no-costs` (default on), removal of `--cost-report`, distributed cost reporting now produces a report, registry leak fixed. (Use `[Unreleased]` on this branch.)
- [ ] Update the wip docs to "as-built": flip `wip/distributed-execution/tracing-cost-reporting.md` T2 to FIXED + `README.md` P1 to DONE; mark `wip/registry/` synthesis status as implemented; record any deferred follow-ups (e.g. D5's costs-only tracer skip, cost-per-node correlation) in `wip/registry/` per the deferred-items convention.
- [ ] Final `make agent-check` + `make agent-test`.

---

## 4. Test surface (synthesis §"Test surface to design" → where it lands)

- Success-path no-leak characterization → **Phase 4** (mirrors the deleted failure-path test).
- DIRECT `--costs` renders correct non-zero cost → **Phase 3**.
- DIRECT `--no-graph --costs` still renders (proves decoupling) → **Phase 1** (emission) + **Phase 3** (render).
- `--no-costs` emits nothing, renders nothing → **Phase 1** + **Phase 3**.
- Cross-worker (A/B/C → one report) → **Phase 2** (pytest, wrapper, no spend) + **Phase 6** (CLI, `--mock-inference` + live).
- `pipelex-api` `/execute` + `/start` leave no registry across requests → **Phase 4**.

---

## 5. Risks / watch-items

- **Double-count window:** none by construction — old renders from registry, new from `PipeOutput`; cutover (Phase 3) flips the single active renderer; deletion (Phase 4) removes the registry. The DIRECT fidelity cross-check (Phase 2/3) guards numeric drift between the two sources.
- **The `_emit_usage_event` early-returns** are the subtle correctness core: `graph_context is None` (neither concern) stays; the **runner fallback must additionally gate on `emit_usage_events`** (Phase 1) or graph-only mode wrongly emits usage.
- **`act_assemble_graph` rename** ripples into the skill + temporal tests + worker activity registration — grep before renaming.
- **cocode + pipelex-api are separate repos:** cocode breaks at call time until migrated (Phase 3); pipelex-api needs only verification (leak gone, usage auto-exposed via `pipe_output`). Coordinate the `pipelex` pin bump.
- **Payload size:** `tokens_usages` rides on every Temporal `PipeOutput` when `--costs` on (default). Records are small and the `StoragePayloadCodec` offloads >1MB — fine, but note it.
- **Config↔model↔TOML drift:** `make tb` after every `configs.py` / `*.toml` touch (Phases 1, 3).

---

## 6. Cold-start notes (fill in at each checkpoint)

> Keep this section current so a fresh session can resume without re-reading the whole tree. After each checkpoint, append: what landed, decisions taken/changed, new file:line anchors discovered, and the exact next unchecked box.

- **CP1:** _pending_
- **CP2:** _pending_
- **CP3:** _pending — D6 decided: flip `is_log_costs_to_console` → `true` in both TOMLs (apply here)_
- **CP4:** _pending (deleted-symbol inventory + full-suite status)_
- **CP5:** _pending_
- **CP6:** _pending_

---

## 7. Out of scope / explicitly deferred

- DynamoDB as a validation target (NDJSON-first; the read-back is backend-agnostic so DDB rides along for free).
- P0.2 follow-ons (`strict_mode`, `BatchWriteItem`, NDJSON shared-FS check, per-thread writer_id, tz-aware `JobMetadata.started_at`).
- D5's costs-only in-memory-tracer skip; cost-per-node correlation via `UsageReportEvent.node_id`.
- The deeper T3 "request-scoped tracing state instead of process-singleton" refactor.
