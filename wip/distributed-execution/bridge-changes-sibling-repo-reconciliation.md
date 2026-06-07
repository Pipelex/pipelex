# Runtime-bridge changes → sibling-repo reconciliation

**Status: DIAGNOSED — 2026-06-07.** Research + diagnosis are done (this session grepped both sibling repos, checked the dependency pins, and read the reference implementations). No sibling code has been changed yet — the reconciliation is sequenced behind #966 landing (see "Sequenced reconciliation plan"). This doc is now the authoritative breakage inventory; act on it, don't re-investigate.

## TL;DR

`_bridge` (this worktree, branch `feature/Runtime-bridge-extraction`, PR **#966**) is the clean extraction of the framework-agnostic runtime bridge, now reconciled against dev's distributed cost-reporting work (#967 + #968). That reconciliation renamed/removed parts of the bridge's public surface. Two downstream consumers depend on that surface:

- **`pipelex-mistralai-workflows`** (`/Users/lchoquel/repos/Pipelex/pipelex-mistralai-workflows`) — the published package (PyPI `pipelex-mistralai-workflows`, import root `pipelex_mistralai_workflows`). The Mistral Workflows plugin that invokes Pipelex pipes from inside Mistral Workflows activities.
- **`_workflows`** (`/Users/lchoquel/repos/Pipelex/_workflows`) — a pipelex worktree on branch `feature/Mistral-workflows-merge-4` (the bigger Mistral-Workflows-integration line, PR #954 family).

**The break is deferred, not live.** Both consumers are pinned to / based on a *pre-rename* pipelex, so nothing is broken at this instant. The break materializes the moment either consumer is moved onto post-#966 pipelex. The fix is mechanical: the Mistral-native graph/usage path is a mirror of the Temporal path, and it needs the **exact same** `act_assemble_graph → act_assemble_tracing` rewiring the Temporal path already received in #967 — plus it gains cost reporting it never had.

## Dependency reality (why it's deferred)

- **`pipelex-mistralai-workflows/pyproject.toml`** pins `pipelex` via `[tool.uv.sources]` to a **git rev**: `pipelex = { git = "...pipelex.git", rev = "8f52d40130e3bf6043569b303b7984844272dd4d" }`. The editable `pipelex = { path = "../_workflows", editable = true }` override sits right above it, **commented out**. `[project].dependencies` separately declares `pipelex>=0.27.0`, but the `[tool.uv.sources]` git rev wins for resolution.
  - Rev `8f52d40` = tip of `feature/Mistral-workflows-merge-3` (`backup/pre-dev-merge`), dated 2026-06-01. It is **pre-rename** (has `pipelex/graph/graph_context.py`, not `trace_context.py`) and is **not an ancestor of `origin/dev` nor of this `_bridge` branch**. So the package currently builds against old pipelex and is internally consistent — it does **not** break until that rev is bumped (or the editable override is uncommented against a reconciled `_workflows`).
- **`_workflows` (merge-4)** is its own pipelex copy and is also **pre-rename / pre-#967**: it still has `pipelex/graph/graph_context.py` (no `trace_context.py`), has **no** `pipelex/pipe_run/tracing_assembly.py`, and still ships the old `pipelex/runtime_bridge/primitives/graph_assembly.py`. `origin/dev` is **not** an ancestor of merge-4; merge-4 carries ~100+ commits not in `_bridge`. It has the bridge extraction (`runtime_bridge/` with bootstrap/bridge/execution_mode/primitives) but built on a base that predates dev's #967/#968.

Net: the editable override couples the two — when uncommented, the package's `pipelex` comes from `../_workflows`. So the package can only be **correctly fixed and validated** once `_workflows` itself carries the reconciled (post-#966/#967/#968) pipelex. Fixing the package in isolation against an un-merged `_workflows` would be wrong. This dictates the ordering below.

## Breakage inventory — `pipelex-mistralai-workflows` package

All paths under `pipelex_mistralai_workflows/`. Split into hard breaks (won't import/run against post-#966 pipelex) and a parity gap (compiles, but silently drops cost).

### Hard breaks (renamed/removed pipelex surface)

1. **`primitives/act_pipelex_assemble_graph.py`** — imports `from pipelex.runtime_bridge.primitives.graph_assembly import assemble_graph_for_pipeline_run`. **That module + function are deleted** (replaced by `pipelex/pipe_run/tracing_assembly.py::assemble_tracing`). This whole file must be rewritten as `act_pipelex_assemble_tracing.py` (see fix pattern). It defines `AssembleGraphArg` + `act_pipelex_assemble_graph`.
2. **`primitives/wf_pipe_run.py`** (lines ~32-35, 112-123) — imports `AssembleGraphArg` / `act_pipelex_assemble_graph`, constructs `AssembleGraphArg(...)`, calls the activity, and copies **only** `graph_spec` + `graph_assembly_error` onto `pipe_output`. Must call the new tracing activity, gate on the run's emit flags, and copy all four fields.
3. **`primitives/wf_pipe_router.py`** (lines ~134, 156-173) — reads `pipe_job.job_metadata.graph_context` and `model_copy(update={"graph_context": ...})`. **`JobMetadata.graph_context` → `trace_context`** (confirmed: `pipelex/pipeline/job_metadata.py:74 trace_context: TraceContext | None`). The per-step tracer-open attributes it reads (`graph_id`, `data_inclusion`, `parent_node_id`) **survive** on `TraceContext` unchanged, so only the container attribute/var name changes here.
4. **`streaming.py`** (lines ~144, 167) — calls `run_pipe_via_bridge(input_payload, graph_context=graph_context)`. **The kwarg is renamed `graph_context` → `trace_context`** (confirmed: `bridge.py:88 run_pipe_via_bridge(input_payload, trace_context: TraceContext | None = None)`). The local var fed from `tracer_manager.open_tracer(...)` can be renamed for clarity but only the kwarg is load-bearing.
5. **`primitives/__init__.py`** + **`primitives/registration.py`** — both re-export `act_pipelex_assemble_graph` (and `__init__` the `AssembleGraphArg` symbol via the module). Update to the new activity name when (1) is rewritten.

### Parity gap (no compile break, but wrong post-#967)

6. The Mistral-native path **never assembled usage/cost** — `wf_pipe_run.py` only ever set `graph_spec`. Post-#967 cost rides on `PipeOutput.tokens_usages` (+ `usage_assembly_error`). When you rewrite (1)+(2) to use `assemble_tracing`, you get usage assembly **for free** from the same single event read; copy `tokens_usages` + `usage_assembly_error` onto `pipe_output` too. This is the "Mistral-native gains cost reporting" win, not just a break-fix.

### Confirmed NOT broken (don't touch — already verified to resolve against post-#966 pipelex)

- `streaming_event_forwarder.py`, `streaming.py`, `wf_pipe_router.py`, `pipe_run.py`, `pipe_router.py`, `act_pipelex_leaf.py`, `act_pipelex_deliver.py`, `act_pipelex_flush_trace_events.py`, `scoped_library.py`, `_kajson_codec.py`, `dependency.py`, `activities.py` import these, all of which **survive**: `pipelex.graph.graph_config.DataInclusionConfig`, `pipelex.tracing.event_log_protocol.EventLogProtocol`, `pipelex.graph.graph_tracer_manager.GraphTracerManager`, `pipelex.runtime_bridge.bootstrap.ensure_pipelex_booted`, and the bridge primitives `trace_flush.flush_trace_events_to_backend` / `hydration.hydrate_working_memory` / `pipe_classification.is_controller_pipe` / `submitter_hydration.rehydrate_pipe_output_with_crate` / `delivery.execute_delivery`.
- **`tests/integration/test_bridge_temporal_*.py`** import `from pipelex.temporal.tprl_pipe.temporal_pipe_router import make_temporal_pipe_router` — that path **still exists** in `_bridge` (only `pipe_run_arg` moved out of `temporal.tprl_pipe` into `runtime_bridge.primitives`). Not a break.
- The package uses **none** of `is_generate_costs`, `UsageRegistry`, `open_registry`, `close_registry`, `generate_report`, `inject_tokens_usages`, `--cost-report` — so #968's cost-API removals don't hit it directly. Its cost story is purely the additive parity gain in (6).

## The canonical fix pattern (mirror the Temporal path)

The Temporal path already did this exact migration in #967. Use these `_bridge` files as the reference implementation:

- **`pipelex/pipe_run/tracing_assembly.py`** — `assemble_tracing(pipeline_run_id, *, assemble_graph: bool, assemble_usage: bool, domain_code=None, main_pipe_code=None) -> TracingAssembly`. One event read → both artifacts. `TracingAssembly(extra="forbid")` carries `graph_spec` / `graph_assembly_error` / `tokens_usages` / `usage_assembly_error`. Best-effort read failures (incl. `EventLogReadError`) are caught inside and returned on the `*_error` fields; only programming bugs propagate.
- **`pipelex/temporal/tprl_pipe/act_assemble_tracing.py`** — the activity wrapper. `AssembleTracingArg` adds `assemble_graph: bool` / `assemble_usage: bool` (mirror of the run's emit flags) on top of `pipeline_run_id` / `domain_code` / `main_pipe_code`, and returns `TracingAssembly`. Deliberately **not** wrapped in error-classification — observability, not a pipe step.
- **`pipelex/temporal/tprl_pipe/wf_pipe_run.py`** (the dispatch, ~lines 87-122) — gates on `trace_context is not None and (trace_context.emit_graph_events or trace_context.emit_usage_events)`, passes `assemble_graph=trace_context.emit_graph_events` / `assemble_usage=trace_context.emit_usage_events`, then copies **all four** populated fields onto `pipe_output`. This is the precise shape `wf_pipe_run.py` in the Mistral package should take.

Mistral-package edits, concretely:

- Rename `act_pipelex_assemble_graph.py` → `act_pipelex_assemble_tracing.py`: `AssembleTracingArg(pipeline_run_id, domain_code, main_pipe_code, assemble_graph, assemble_usage)`; body `return assemble_tracing(...)` returning `TracingAssembly`; keep the Mistral `@activity(...)` decorator.
- In `wf_pipe_run.py`: gate on the run's emit flags (the Mistral parent has the `PipeJob`, hence `job_metadata.trace_context`; if `trace_context` is None, default both to True to preserve today's always-assemble-graph behavior — or read the config gate the way DIRECT does, decide during impl), call the new activity, copy `graph_spec` / `graph_assembly_error` / `tokens_usages` / `usage_assembly_error`.
- In `wf_pipe_router.py` + `streaming.py`: the `graph_context` → `trace_context` renames in the breakage inventory above.
- Update `primitives/__init__.py` + `registration.py` exports.

## `_workflows` (merge-4) reconciliation

merge-4 is a divergent pipelex worktree that has the bridge extraction but predates dev's #967/#968. To carry the reconciled bridge it must absorb dev — the **same** reconciliation `_bridge` just performed, but it also has its own in-tree copies to migrate:

- its `pipelex/runtime_bridge/primitives/graph_assembly.py` must be deleted in favor of `pipe_run/tracing_assembly.py` (the merge with dev surfaces this);
- `pipelex/graph/graph_context.py` → `trace_context.py` + the `graph_context` → `trace_context` rename across `JobMetadata` and all callers;
- `is_generate_costs` → `is_generate_usage`; `UsageRegistry` removal; `--cost-report` → `--costs` — all per #967/#968.

Two viable paths; recommend (b):

- **(a)** Merge `origin/dev` into `_workflows` directly and reconcile by hand (re-doing the tracing reconciliation a second time, in a much bigger tree).
- **(b) Preferred:** land #966 onto dev first, *then* merge the post-#966 dev into `_workflows`. #966 is the already-reconciled bridge extraction, so this folds the bridge reconciliation in once and leaves only the Mistral-Workflows-specific integration code to fix up in merge-4. Confirmed prerequisite: merge-4 is downstream of the bridge work conceptually but **not** an ancestor/descendant of either dev or this branch today — it genuinely needs a merge, not a fast-forward.

## Sequenced reconciliation plan (ordering matters)

1. **Land #966** (this `_bridge` branch) onto `dev`. It carries the reconciled bridge surface (`trace_context`, unified `assemble_tracing`, `EventLogReadError` layering, deleted `graph_assembly` primitive).
2. **Merge post-#966 `dev` into `_workflows` (merge-4)**, reconciling merge-4's in-tree pipelex copies (graph_assembly deletion, `graph_context→trace_context`, `is_generate_costs→is_generate_usage`, UsageRegistry removal, CLI flag). Path (b) above.
3. **Fix the `pipelex-mistralai-workflows` package** against the reconciled API — the breakage inventory + canonical fix pattern above. Validate by **uncommenting** the editable `pipelex = { path = "../_workflows", editable = true }` override (now that `_workflows` carries the reconciled pipelex) and running the package's own pyright/mypy/tests + its `tests/integration/test_bridge_temporal_*` and Mistral-native suites.
4. **Re-pin** the package: replace the editable override with a git rev (or a released `pipelex` version) that includes #966+#967+#968, then re-comment the editable override per the file's own instructions ("Strip this override before publishing... Add it back on the next dev cycle when the next breaking change to `pipelex.runtime_bridge` lands").

Until step 1 happens, steps 2-4 are blocked and **no sibling code should change** — editing either consumer now would only desync it from its current (pre-rename) pipelex.

**Ready-to-run per-repo handoffs** (self-contained, keyed to "#966 has hit dev"; this doc is the index, those are the executables):

- `_workflows` → `/Users/lchoquel/repos/Pipelex/_workflows/wip/post-966-dev-reconciliation-handoff.md`. Key insight there: #966 *is* merge-4's bridge extraction, so once it's on dev merge-4's bridge work is redundant and its only remaining unique value is the mistralai-2.x HOLD group (blocked on `instructor` PR #2298). Recommends retiring merge-4 in favor of a minimal HOLD-group branch off the new dev, rather than a conflict-heavy merge.
- `pipelex-mistralai-workflows` → `/Users/lchoquel/repos/Pipelex/pipelex-mistralai-workflows/wip/post-966-bridge-reconciliation-handoff.md`. The breakage inventory + canonical fix pattern below, written as concrete edits with code, plus the repin/validate/settle steps. Can pin straight to a post-#966 dev rev — does not require the `_workflows` consolidation.

## The MISTRAL_NATIVE question — ANSWERED

Original open question: did `_run_mistral_native` or the sibling package consume the now-deleted `assemble_graph_for_pipeline_run`?

- **`_run_mistral_native`** (in `_bridge` `pipelex/runtime_bridge/bridge.py:394`) is **thin** — it imports `make_mistral_workflows_pipe_run`, calls `pipe_run.run(...)`, and serializes via `_serialize_completed_output`. It does **not** touch graph/usage assembly. No change needed there.
- **The sibling package DOES** consume it — `primitives/act_pipelex_assemble_graph.py` imports `assemble_graph_for_pipeline_run` directly and `primitives/wf_pipe_run.py` orchestrates it. So the Mistral-native graph/usage handling needs the identical `act_assemble_graph → act_assemble_tracing` / unified-`assemble_tracing` rewiring the Temporal path got, and additionally **gains** usage/cost assembly it never performed (parity gap (6)).

## Current state of `_bridge` (this worktree)

- Branch `feature/Runtime-bridge-extraction`, worktree `/Users/lchoquel/repos/Pipelex/_bridge`, PR **#966** (#959 is closed).
- 0 behind `dev`; unpushed commits ahead carry dev's #967 + the merge (tracing reconciliation: `EventLogReadError` layering, `graph_assembly` primitive deletion, `graph_context → trace_context`) + the TODOS retarget.
- All green at last check: `make agent-check` (pyright clean, mypy clean), unit suite, DIRECT-tracing + `runtime_bridge` integration tests; temporal tracing tests collect clean.

## Pointers / prior art

- `TODOS.md` (this worktree) — PR #966 reviewer's guide, incl. the "Tracing reconciliation (post-`dev` merge)" section with the exact decisions.
- `wip/runtime-bridge/` — review-triage of #959/#966. README is the cold-start entry.
- `wip/distributed-execution/tracing-cost-reporting.md` — #967's as-built tracing/cost-reporting design.
- Memory (auto-loaded): `project_runtime_bridge_pr959_review` (this PR's state), `project_registry_leak_fix` (#967), `project_temporal_not_shipped` (Temporal not in prod).
- Reference impls in `_bridge` for the Mistral-package fix: `pipelex/pipe_run/tracing_assembly.py`, `pipelex/temporal/tprl_pipe/act_assemble_tracing.py`, `pipelex/temporal/tprl_pipe/wf_pipe_run.py`.
