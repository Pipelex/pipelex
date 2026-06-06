# Cost reporting — deferred design decisions (Phase 3 review)

Two findings from the Phase 3 code review (event-sourced cost-report rendering) are **design decisions, not bugs to reflexively patch**. They are deferred here so they are not lost. The review's correctness/cleanup findings (#1 free-model suppression, #2 try-scope, #4/#7 aggregation consolidation) were fixed in the Phase 3 change itself; these two need a deliberate call.

Both touch the same question the registry track is converging on: *what is the single, intentional trigger for "collect and report costs"?* Right now that intent is spread across three switches — `--costs` / `is_generate_costs`, `tracing_config.is_enabled`, and the agent CLI's own `costs` param default — and they don't fully agree.

---

## #3 — Cost reporting is coupled to `tracing_config.is_enabled`

**What.** After the Phase 3 cutover, the *only* cost renderer reads `pipe_output.tokens_usages`, which is assembled from the trace-event stream. That stream only exists when tracing is enabled. So with `[pipelex.tracing_config] is_enabled = false` but `--costs` on (the default), **no cost report is produced at all** — silently.

**Evidence.**

- `pipelex/pipeline/pipeline_run_setup.py:193` — the event log is created only `if tracing_config.is_enabled:`; otherwise `event_log` stays `None`.
- `pipelex/pipeline/pipeline_run_setup.py:228` — usage events are emitted only `if is_generate_costs and event_log is not None:` → no event log ⇒ no usage events.
- `pipelex/pipe_run/tracing_assembly.py:80` — `assemble_tracing` early-returns `if not tracing_config.is_enabled:`, leaving `tokens_usages = None`.
- `pipelex/reporting/cost_report_renderer.py` — `render_run_cost_report` no-ops on `not tokens_usages`.

**Why it's a regression.** Before Phase 3, the cost report was rendered from the live `UsageRegistry`, which `_report_*_job` populated directly — independent of tracing. So `pipelex run --costs` printed a table even with tracing disabled. Now it doesn't. Default config has `is_enabled = true`, so the default experience is fine; the gap is for embedders who turn tracing off (e.g. to avoid NDJSON files) and reasonably expect `--costs` to keep working.

**The design question.** Is `--costs` *meant* to require the event-log transport?

- **Option A — accept the coupling, make it honest.** Treat tracing as the cost transport (which is the Phase 3/4 architecture). Then: when `is_generate_costs` is on but `tracing_config.is_enabled` is off, emit a one-time `log.warning` ("costs requested but tracing is disabled; no cost report will be produced — enable tracing or disable --costs"), and document the dependency in `reporting-config.md` / the `--costs` help text. Cheapest, keeps one transport.
- **Option B — decouple at setup.** When `is_generate_costs` is on, force the event log into existence even if `tracing_config.is_enabled` is off (a costs-only, in-memory event log that never writes NDJSON), and let `assemble_tracing` run for the usage concern regardless of `is_enabled`. Restores the pre-Phase-3 "costs work without tracing" guarantee at the cost of a second reason the event log can exist.
- **Option C — separate enable flags.** Split "emit trace events to a backend (NDJSON/DDB)" from "assemble in-memory usage for reporting." `is_enabled` governs the former; `is_generate_costs` governs the latter. Cleanest conceptually, most config surface.

**Lean:** A for now (it matches the locked Option-B-events-as-single-source direction and is a few lines), with C as the principled end state if embedders hit it. Decide before Phase 4 removes the registry — after that there is no fallback renderer, so the coupling becomes the only behavior.

---

## #6 — Agent CLI gates costs on the raw `costs` param; main CLI gates on the resolved config

**What.** The two CLIs resolve "should we collect/report costs" differently:

- **Main CLI** (`pipelex run`): the renderer is gated on `execution_config.is_generate_costs` — the value *resolved* from the `--costs/--no-costs` tri-state over the config default. A user who sets `is_generate_costs = false` in config and passes no flag gets no costs.
- **Agent CLI** (`pipelex-agent run`): `costs` is a hard-coded `bool = True` parameter (see `run_pipeline_core` / the `pipe_cmd`/`bundle_cmd`/`method_cmd` defaults). It is forced into the config via `with_execution_overrides(generate_costs=costs)` and also gates `build_cost_summary` directly (`pipelex/cli/agent_cli/commands/run/_run_core.py:111`). It **never consults the config default** `is_generate_costs`.

**Consequence.** An embedder who disables cost collection globally (`[pipeline_execution_config] is_generate_costs = false`, e.g. to cut event-log overhead) gets it honored by `pipelex run` but **not** by `pipelex-agent run` — the agent keeps emitting usage events and attaching a `cost_report` to every `--with-memory` envelope / on-disk JSON unless `--no-costs` is passed explicitly.

**History.** This predates Phase 3 (the agent `--costs` default-True override landed in Phase 1). Phase 3 only made it *observable*, because it surfaces a `cost_report` object in the agent output where before nothing was shown.

**The design question.** Should the agent CLI honor the config `is_generate_costs` default like the main CLI, or is "agent always collects unless told not to" intentional?

- **Option A — make the agent tri-state like the main CLI.** Change the agent `costs` param to `bool | None = None` and resolve it through `with_execution_overrides` (None ⇒ use config default). One-line-ish per command + the `_run_core` gate reads the resolved `execution_config.is_generate_costs`. Makes the two surfaces consistent.
- **Option B — keep agent default-on by design, document it.** If the agent is meant to be maximally informative for machine consumers regardless of an embedder's human-CLI preference, leave it but document the divergence in `agent_cli/CLAUDE.md` so it's a choice, not an accident.

**Lean:** A — consistency across the two surfaces is worth more than the agent being unconditionally chatty, and `--no-costs` still lets a caller force it off. But it's a behavior change for agent consumers, so it needs a deliberate sign-off rather than being folded silently into the Phase 3 fix.

---

## Cross-cutting note

Both findings are facets of the same gap: there is no *single owner* of "is cost collection/reporting on for this run?" The value is currently derived in three places (config default, the two CLIs' flag resolution, and the tracing toggle) and they disagree at the edges. Whoever takes the Phase 4 registry removal should consider collapsing this into one resolved predicate on `PipelineExecutionConfig` that both CLIs and the assembly path read — at which point #3 and #6 both fall out as consequences of one decision.
