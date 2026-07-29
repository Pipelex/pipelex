# Complete the layer boundary — placement, so the predicate can say what it means

**Status:** plan, drafted 2026-07-29 against `dev` at `8c0b99b3a` (the base of `fix/Codegen-lint-clean`). Nothing implemented. Every number below was measured on that tree, and the recipe to reproduce each one is inline — no external tooling required.

**Where to work:** the `pipelex/` worktree, on a branch off `dev` (e.g. `refactor/Layer-placement`), normal PR back to `dev`. **Do not start before PR [#1070](https://github.com/Pipelex/pipelex/pull/1070) merges** — it touches `codegen/emitters/` and `core/concepts/structure_generation/`, and this track touches `core/concepts/concept_structure_blueprint.py`; the overlap is small but the branch bases should be linear.

**What this finishes.** The hub split drew the boundary and made it enforceable. It left one thing undone, and the track recorded it honestly rather than fixing it: three top-level packages could not be named in the closure test's `INTERPRETER_PACKAGES`, so the property the whole track exists to state — *importing the runtime loads zero interpreter modules* — still ships with a caveat. The caveat is not repeated in four places, as [`../refactoring/deferred-placement-follow-ups.md`](../refactoring/deferred-placement-follow-ups.md) §3 estimated; it is repeated in **six**, and a caveat repeated six times is a caveat that will go stale in at least one. This plan removes it.

The measurement also turned up something the deferral did not know: one of those three packages is not an interpreter package at all, and it is hiding a module that loads the entire interpreter.

## Related documents

- [`pr-1062-review-notes.md`](../pr-1062-review-notes.md) §1 — where the leak was first recorded, from the Codex thread on the closure test. **Partly stale**: it names `core.bundles.exceptions` as the awkward case, and that module no longer exists — the modularity refactors moved it to `core.exceptions`, and it is no longer part of the problem.
- [`../refactoring/deferred-placement-follow-ups.md`](../refactoring/deferred-placement-follow-ups.md) §3 — the same leak, restated after M1, with the remedy named ("move the leaf models to a runtime-layer home, *then* widen the predicate"). This plan is that remedy, measured.
- [`hub-split-tracker.md`](hub-split-tracker.md) → [Cross-repo sweep](hub-split-tracker.md#cross-repo-sweep) — **still open and release-gated.** This track's cross-repo work is the same shape and must merge into that sweep rather than open a second one. See [Cross-repo](#cross-repo--fold-into-the-pending-hub-sweep).
- [`docs/contribute/hub-layering.md`](../../docs/contribute/hub-layering.md) — the shipped specification. It is the thing this plan edits at the end, not the thing it works around.

## The measurement — reproduce it in two minutes

Everything below rests on three commands run from the `pipelex/` worktree.

**1. What leaks into a runtime closure.** For any entry point, which modules of the three suspect packages get loaded:

```bash
.venv/bin/python -c "
import sys, importlib
importlib.import_module('pipelex.core.stuffs.stuff_factory')
print(sorted(m for m in sys.modules if m.startswith(('pipelex.pipeline','pipelex.pipe_run','pipelex.graph'))))
"
```

**2. Every module-level edge from the declared runtime layer into them** — the authoritative work list, because the closure is just this list plus transitive fallout:

```bash
grep -rn --include='*.py' -E '^from pipelex\.(pipeline|pipe_run|graph)[.a-z_]* import|^import pipelex\.(pipeline|pipe_run|graph)' \
  pipelex/cogt pipelex/core pipelex/plugins pipelex/providers pipelex/reporting \
  pipelex/system pipelex/tools pipelex/tracing pipelex/runtime_hub.py pipelex/config.py
```

**3. Whether an undeclared package is secretly clean (or secretly dirty)** — import each of its modules in a fresh subprocess and count interpreter modules loaded:

```bash
.venv/bin/python - <<'EOF'
import subprocess, sys, pathlib
INTERP = ('pipelex.libraries','pipelex.pipe_operators','pipelex.pipe_controllers','pipelex.codegen',
          'pipelex.builder','pipelex.interpreter_plugins','pipelex.pipe_machinery','pipelex.pipe_signature',
          'pipelex.mthds_parsing','pipelex.interpreter_hub')
script = f"import sys, importlib; importlib.import_module(sys.argv[1]); print(len([m for m in sys.modules if m.startswith({INTERP!r})]))"
for pkg in ("graph", "tracing", "observer", "errors"):
    for f in sorted(pathlib.Path("pipelex", pkg).rglob("*.py")):
        if f.name == "__init__.py":
            continue
        mod = str(f.with_suffix("")).replace("/", ".")
        n = subprocess.run([sys.executable, "-c", script, mod], capture_output=True, text=True).stdout.strip()
        if n not in ("0", ""):
            print(f"{n:>6}  {mod}")
EOF
```

Command 3 is the one that changed this plan's shape. Run it before trusting anything below.

## What actually leaks

Command 2 returns exactly nine edges, from eight files. This is the complete surface — there is no long tail:

| # | Importer (declared runtime layer) | Imports | Resolution |
| --- | --- | --- | --- |
| 1 | `cogt/content_generation/cogt_run_params.py` | `pipe_run.pipe_run_mode.PipeRunMode` | **move the leaf** |
| 2 | `core/pipes/inputs/exceptions.py` | `pipe_run.pipe_run_mode.PipeRunMode` | **move the leaf** |
| 3 | `core/pipes/inputs/exceptions.py` | `pipe_run.exceptions.PipeRunError` | **move the leaf** |
| 4 | `core/concepts/concept_structure_blueprint.py` | `pipe_run.pipe_run_params.PipeRunParamKey` | **move the leaf** |
| 5 | `core/pipes/pipe_output.py` | `pipeline.pipeline_models.SpecialPipelineId` | **move the leaf** |
| 6 | `core/pipes/pipe_output.py` | `graph.graphspec.GraphSpec` | **declare `graph`** |
| 7 | `system/configuration/configs.py` | `graph.graph_config.GraphConfig` | **declare `graph`** |
| 8 | `tracing/trace_events.py` | `graph.graphspec.{EdgeKind, ErrorSpec, IOSpec, NodeKind}` | **declare `graph`** |
| 9 | `tracing/graphspec_assembler.py` | `graph.graphspec.*` | **declare `graph`** |

Two different problems wearing one label. Four of the nine are not a placement wart at all — they are a **missing declaration**, and the fix costs nothing. The other five are the real leaves.

Everything else in the closures is transitive fallout from these nine. In particular the longest chain — `pipeline.exceptions` → `pipeline.validation_errors` → `pipeline.fixes.planner` — is reached *only* through edge 4, via `pipe_run_params.py`'s import of `PipeStackOverflowError`. Cut edge 4 and the whole chain leaves every runtime closure without being touched.

## Part 1 — `graph` and `tracing` are runtime-layer, and one module is lying about it

**The finding.** Command 3, run over every module in `graph/`, `tracing/`, `observer/` and `errors/`, returns exactly one offender:

```
    77  pipelex.graph.graph_rendering
```

Every other module in all four packages loads **zero** interpreter modules. `graph/` imports no interpreter package anywhere except that one file; `tracing/`, `observer/` and `errors/` import none at all.

So `graph` was never an interpreter package. It is the run-graph data model (`graphspec.py`), the tracer, the renderers and their config — all of it machinery present at execution time whatever is loaded, which is the runtime layer's own definition. It sat outside both declarations because nobody measured it, and the closure test could not name it because `graphspec` is in every runtime closure — which reads as a leak only if you have already assumed the package is interpreter-layer. It isn't. Edges 6–9 are correct imports that needed a declaration, not a refactor.

**The hidden breach.** `graph/graph_rendering.py` imports `pipeline.dry_run_pipeline`, and importing it pulls in `interpreter_hub` and 76 more interpreter modules. It has passed every gate to date for a reason worth stating: the layer rule and the transitive rule both filter their candidates through `is_runtime_layer`, and `pipelex.graph` is not declared — so *omitting a package makes the guard quieter, not louder*. The guard's own note says exactly this. `graph_rendering` has been outside the rule's domain the whole time.

This is the same shape as the `pipelex.plugins` breach the transitive rule was built to catch, and it is the argument for declaring these packages rather than leaving them undeclared: an undeclared package is not neutral, it is unpoliced.

**The module splits cleanly.** Its two importers are both CLI (`cli/commands/graph_cmd.py`, `cli/agent_cli/commands/validate/bundle_cmd.py`), and its contents fall on either side of the line by themselves:

- Runtime-layer, imports nothing but `graph/` + `config` + `tools`: `GraphFormat`, `_sanitize_graph_name`, `render_graph_from_spec` (takes a `GraphSpec`, renders it).
- Interpreter-layer, needs `dry_run_pipeline`: `_dry_run_bundle`, `generate_graph_for_bundle`, `generate_view_for_bundle` (take a *bundle*, dry-run it, then render).

The split is along "do I need a loaded method?", which is the layer boundary's own question.

## Part 2 — the four leaves in `pipeline` and `pipe_run`

Unlike `graph`, these two are genuinely interpreter-layer. Measured by counting module-level imports of interpreter packages:

| package | modules importing the interpreter | verdict |
| --- | --- | --- |
| `pipeline` | 14 of 32 (`validate_bundle`, `resolve_bundle`, `controller_taint`, `fixes/fix_loop`, `execution_seams`, `bundle_validator`, `runner`, …) | solidly interpreter |
| `pipe_run` | 3 of 15 (`pipe_job`, `pipe_job_factory`, `dry_run_in_process`) | straddles |
| `graph` | 1 of 27 (`graph_rendering`) | runtime, with one tenant in the wrong house |

The symbols the runtime layer actually needs out of the two interpreter packages:

| symbol | today | size | who needs it from the runtime layer |
| --- | --- | --- | --- |
| `SpecialPipelineId` | `pipeline/pipeline_models.py` — the whole module | 6 lines, one `StrEnum` | `core/pipes/pipe_output.py` |
| `PipeRunMode` | `pipe_run/pipe_run_mode.py` — the whole module | 34 lines, one `StrEnum` + three properties | `cogt/content_generation/cogt_run_params.py`, `core/pipes/inputs/exceptions.py` |
| `PipeRunParamKey` | inside `pipe_run/pipe_run_params.py` (255 lines) | 2-member `StrEnum` + `value_list()` | `core/concepts/concept_structure_blueprint.py`, for its reserved-names list |
| `PipeRunError` | inside `pipe_run/exceptions.py` (106 lines, 11 classes) | one `PipelexError` subclass | `core/pipes/inputs/exceptions.py`, as a base class |

Two are whole tiny modules that move as-is. Two are single symbols inside larger modules and need extracting.

**A note on `pipe_run/exceptions.py`.** `AsyncExecutionNotEnabledError`'s docstring, in that same file, says *"it lives in core precisely because it is the shared contract between the runner API … and any async-execution backend plugin"*. It does not live in core. That docstring is evidence the module's placement was already thought to be wrong once, and it is a free doc fix whichever way D-2 goes.

## Decisions to settle before coding

- **D-1 — destination for the relocated leaves.** Recommended: **`pipelex/system/`**. This is not a new judgment call, it is the precedent the hub track already set — `JobMetadata` moved to `system/job_metadata.py`, `TraceContext` to `system/trace_context.py`, `DataInclusionConfig` to `system/data_inclusion_config.py`, all for exactly this reason. The alternative, `pipelex/core/`, reads worse: `core/` is documented as describing *what a method's values are*, and a run mode is not a value.
- **D-2 — `pipe_run`: move the leaves, or split the package the way `core/` was split?** Recommended: **move the leaves.** The split is superficially attractive (only 3 of 15 modules touch the interpreter, and `core/` → `pipe_machinery` is the precedent), but the measurement kills it: declaring `pipe_run` runtime-layer would put `pipe_run_params.py` inside the declaration, and it imports `PipeStackOverflowError` from `pipeline.exceptions` — so the split *also* requires relocating the `pipeline.exceptions` → `validation_errors` → `fixes.planner` chain, which the leaf-move approach removes from the closure for free. The split is strictly more work and strictly more cross-repo churn (`pipe_job` is on the `pipelex-transport` `ALLOWED_SURFACE` and is imported by four sibling repos). Take the leaves.
- **D-3 — where `graph_rendering.py`'s two halves go.** Recommended: **split it.** The pure half (`GraphFormat`, `render_graph_from_spec`, `_sanitize_graph_name`) stays in `graph/`; the bundle-driven half (`_dry_run_bundle`, `generate_graph_for_bundle`, `generate_view_for_bundle`) moves to `pipelex/pipeline/`, next to the `dry_run_pipeline` it exists to wrap. The alternative — move the whole file to `cli/` because both importers are CLI — is worse: it would strand `render_graph_from_spec`, which is a genuine runtime-layer renderer, behind a CLI import path.
- **D-4 — how far to extend the declaration.** `graph` and `tracing` are required by this plan. `observer` and `errors` are measured equally clean and are cheap to add in the same commit; `kit` is data files and `language` has interpreter edges, so both stay out. Recommended: declare `graph`, `tracing`, `observer`, `errors` — a partial declaration is what let `graph_rendering` hide, and the fix is to stop leaving measured-clean packages unpoliced.
- **D-5 — does the closure test name `graph` in `INTERPRETER_PACKAGES`?** No — that is the point of Part 1. `graph` moves into `RUNTIME_LAYER_PACKAGES`; only `pipeline` and `pipe_run` get added to `INTERPRETER_PACKAGES`. Recorded as a decision because [`pr-1062-review-notes.md`](../pr-1062-review-notes.md) and the deferred-placement note both list `graph` alongside the other two, and a reader coming from those docs will expect it on the wrong side.

## Phases

### Phase 1 — declare the clean packages, and evict the one tenant that isn't

- [x] 1.1 Split `graph/graph_rendering.py` per D-3: bundle-driven helpers to `pipelex/pipeline/bundle_graph_rendering.py`, pure renderer stays. Updated the one affected CLI import site (`bundle_cmd.py`; `graph_cmd.py` only wanted `render_graph_from_spec`, which stayed) and moved the four bundle-half test modules from `tests/unit/pipelex/graph/` to `tests/unit/pipelex/pipeline/`.
- [x] 1.2 Add `pipelex.graph`, `pipelex.tracing`, `pipelex.observer`, `pipelex.errors` to `RUNTIME_LAYER_PACKAGES` in `pipelex/cli/dev_cli/commands/hub_layering_guard.py`, and extend the tuple's note to say why each is there.
- [x] 1.3 `make check-hub-layering` passes. **Negative control run and recorded**: re-adding the `pipeline.dry_run_pipeline` import to `graph/graph_rendering.py` makes the guard fail with `interpreter-hub-transitive` at `pipelex/graph/graph_rendering.py:14`, chain `pipelex.pipeline.dry_run_pipeline → pipelex.pipeline.runner → pipelex.interpreter_hub`. Before 1.2 that same file produced no finding at all.
- [x] 1.4 Re-ran measurement command 3 over the four newly-declared packages: no output.

**Deviation from D-3, recorded.** `_sanitize_graph_name` moved with the bundle half rather than staying in `graph/`. It is a private helper whose only caller is `generate_graph_for_bundle`; leaving it behind would have meant either dead code in `graph/` or promoting it to a public cross-module symbol to buy nothing. The layer argument for keeping it is untouched — it needs no loaded method — it just has no reason to live apart from its caller.

**Added at review, beyond the plan.** Two findings from the checkpoint review, both accepted:

- **The four new declarations are now pinned by a test.** `test_the_measured_clean_packages_stay_declared` asserts their membership in `RUNTIME_LAYER_PACKAGES`. Without it, deleting an entry left the whole suite green — which is precisely the failure this track exists to close, and the guard's own note already claimed the declaration "is asserted by a test". Mirrors the existing `test_the_plugin_split_left_both_halves_declared`; negative control run (dropping `pipelex.tracing` fails it).
- **Test placement follow-through.** `tests/CLAUDE.md`'s `pipelex/pipeline/` row listed no unit path, so the four relocated modules landed outside the documented targeted-test route; the row now names `tests/unit/pipelex/pipeline/`. And `test_graph_rendering.py` — which tests `pipelex.graph.graph_rendering` — moved from `tests/unit/pipelex/cli/` to `tests/unit/pipelex/graph/`, where the mapping says it belongs and where the name is now free. It became load-bearing in this change: the bundle-side test stopped asserting the inclusion-flag mapping (that is the renderer's business, not the dispatcher's), so it is the only place that covers it.

**🛑 CHECKPOINT 1** — the four packages are declared, policed, and clean; nothing in `pipeline`/`pipe_run` has moved yet. Gates: `make agent-check`, `make check-hub-layering`, full `make agent-test`. This is a coherent unit and a natural handoff: it is defensible on its own (it closes a live unpoliced breach), and it is the half with no cross-repo consequences at all — `graph_rendering`'s only importers are in this repo. Land it before opening Part 2.

### Phase 2 — relocate the four leaves

- [ ] 2.1 Move `pipeline/pipeline_models.py` → `pipelex/system/` (D-1). Whole module, one enum. Update `core/pipes/pipe_output.py`.
- [ ] 2.2 Move `pipe_run/pipe_run_mode.py` → `pipelex/system/`. Whole module. Its `GraphSpecMode` import is fine post-Phase-1 (runtime → runtime). Update `cogt/content_generation/cogt_run_params.py` and `core/pipes/inputs/exceptions.py`, plus every in-repo import site — this is the widest one.
- [ ] 2.3 Extract `PipeRunParamKey` out of `pipe_run/pipe_run_params.py` into its own module under `pipelex/system/`. Update `concept_structure_blueprint.py`, `pipe_run_params.py` itself, and `pipe_operators/llm/pipe_llm.py`.
- [ ] 2.4 Move `PipeRunError` out of `pipe_run/exceptions.py` (D-2 says the leaf, not the module). Decide whether its siblings that subclass it travel with it or import back up — check `PipeJobError`, `DeliveryError` and the rest before splitting. Update `core/pipes/inputs/exceptions.py`. Fix `AsyncExecutionNotEnabledError`'s stale "it lives in core" docstring while you are in the file.
- [ ] 2.5 Re-run measurement command 1 for every entry point in `RUNTIME_LAYER_ENTRY_POINTS`. Expected: the empty list, for all of them.

### Phase 3 — widen the predicate and delete the caveat

- [ ] 3.1 Add `pipeline` and `pipe_run` to `INTERPRETER_PACKAGES` in `tests/unit/pipelex/test_runtime_layer_import_closure.py`. Do this **after** 2.5 measures clean, not before — a red test here is the confirmation, not the goal.
- [ ] 3.2 Update the module docstring on that test: the "two documented interpreter homes are absent, and their absence is a known wart" note goes away entirely.
- [ ] 3.3 Delete the caveat at all **six** sites. The deferred-placement note said four; it is six, and missing one leaves a doc claiming a wart that no longer exists:
    - `pipelex/runtime_hub.py` — module docstring ("Two interpreter-named packages are deliberately absent…").
    - `pipelex/cli/dev_cli/commands/hub_layering_guard.py` — the `RUNTIME_LAYER_PACKAGES` note ("`core.pipes.pipe_output` does still pull in `pipeline.pipeline_models`…").
    - `tests/unit/pipelex/test_runtime_layer_import_closure.py` — the `INTERPRETER_PACKAGES` note (3.2 above).
    - `docs/contribute/hub-layering.md` — "Two interpreter-named packages are deliberately **not** on the list".
    - `docs/contribute/hub-layering.md` — "Where core splits", the parenthetical on `core.pipes.pipe_output`.
    - `docs/contribute/hub-layering.md` — "The property — the import-closure test", "What the predicate still cannot name is `pipeline` and `pipe_run`".
- [ ] 3.4 `docs/contribute/hub-layering.md` gains the positive statements this track earned: `graph`/`tracing`/`observer`/`errors` are runtime-layer and why; the `graph_rendering` eviction goes in "Known inversions" as a *fixed* one, next to the `pipelex.plugins` worked example it rhymes with — including the lesson, which is the sharpest one this track produced: **an undeclared package is not neutral, it is unpoliced.**
- [ ] 3.5 CHANGELOG: breaking. Public import paths move for `SpecialPipelineId`, `PipeRunMode`, `PipeRunParamKey`, `PipeRunError`, and for `graph_rendering`'s bundle helpers. Give the old → new table.

**🛑 CHECKPOINT 2** — the property is unqualified: every runtime entry point loads zero modules from any interpreter package, stated by a predicate that names them all. Gates: `make agent-check`, `make check-hub-layering`, full `make agent-test`, `make drift-check`.

### Phase 4 — cross-repo, release-gated

- [ ] 4.1 Fold this track's moves into the pending hub cross-repo sweep rather than opening a second one. See below.

**🛑 CHECKPOINT 3 = done** — no consumer is on a stale import path, and the sweep table in `hub-split-tracker.md` is closed.

## Cross-repo — fold into the pending hub sweep

The hub track's own [cross-repo sweep](hub-split-tracker.md#cross-repo-sweep) is **still open and release-gated**, and the evidence is easy to see: `conformance/tests/pipelex_transport/test_data.py`'s `ALLOWED_SURFACE` still pins `pipelex.pipeline.job_metadata` and `pipelex.graph.trace_context` — both of which moved to `pipelex/system/` when the hub split landed. Several sibling repos are on the same stale paths.

So this track must not open a second sweep. Its moves get added to the existing one, and both go out on the same release.

Consumers found by grepping the workspace (`grep -rn --include='*.py' -E 'from pipelex\.(pipeline|pipe_run|graph)' <repo>`) — re-run at sweep time, this is a 2026-07-29 snapshot:

| repo | what it imports | affected by this track |
| --- | --- | --- |
| `cocode/` | `pipe_run.pipe_run_mode.PipeRunMode` in five CLI modules | **yes — the widest consumer of a moved symbol** |
| `pipelex-cookbook/` | `pipe_run.pipe_run_mode.PipeRunMode` (two files), `pipe_run.pipe_run_params.FORCE_DRY_RUN_MODE_ENV_KEY` | **yes** |
| `conformance/` | `ALLOWED_SURFACE` pins `pipe_run.*`, `pipeline.job_metadata`, `graph.trace_context` | **yes — plus the stale hub-track entries** |
| `pipelex-api/` | `graph.graphspec.GraphSpec`, `pipe_run.exceptions.DryRunError`, `pipe_run.pipe_job`, `pipeline.runner` | check `DryRunError` under D-2's split |
| `pipelex-transport/` | `pipe_run.pipe_job`, `pipe_run.pipe_run_params_factory`, `pipeline.job_metadata` | only if D-2 goes the other way |
| `pipelex-daytona-sandbox/` | `pipe_run.pipe_run_params`, `pipeline.job_metadata` | only via the stale hub-track paths |
| `pipelex-mistralai-workflows/` | `graph.trace_context`, `graph.graph_config`, `graph.graph_tracer_manager`, `pipe_run.*` | `graph.*` paths are **unchanged** by this track (Part 1 declares, it does not move) |

Worth stating plainly, because it is the main reason D-2 recommends the leaf move: **Part 1 changes no public import path at all** apart from `graph_rendering`'s bundle helpers, whose only importers are in this repo. All the cross-repo cost lives in Part 2, and the leaf move is the variant that minimizes it.

## Exit criteria — measured, not asserted

1. Measurement command 1 returns `[]` for every entry point in `RUNTIME_LAYER_ENTRY_POINTS`.
2. Measurement command 2 returns only edges into `graph` (which is by then runtime-layer), or nothing.
3. Measurement command 3 returns no output over `graph/`, `tracing/`, `observer/`, `errors/`.
4. `INTERPRETER_PACKAGES` names `pipeline` and `pipe_run`; the closure test is green; its negative control (`pipelex.interpreter_hub` as an entry point) still fails with an offender list.
5. `make check-hub-layering` passes with the four new packages in `RUNTIME_LAYER_PACKAGES`.
6. `grep -rn 'wart' pipelex/runtime_hub.py pipelex/cli/dev_cli/commands/hub_layering_guard.py tests/unit/pipelex/test_runtime_layer_import_closure.py docs/contribute/hub-layering.md` returns nothing about placement.

## Cold-start brief

Read this file top to bottom, then:

1. `cd` to the `pipelex/` worktree, `git pull`, confirm #1070 is merged, `make install` if the venv is stale.
2. Run all three [measurement commands](#the-measurement--reproduce-it-in-two-minutes) and check the numbers still match. If command 3 returns something other than `pipelex.graph.graph_rendering`, a new breach landed and Part 1 needs re-scoping before anything else.
3. Settle D-1 … D-5 with Louis if they are not already recorded here, then branch off `dev` and start at Phase 1.
4. Read `docs/contribute/hub-layering.md` before editing any of it — particularly "Where core splits" and "Known inversions", which are where this track's outcome gets written down.

The two files that carry the boundary's machinery are `pipelex/cli/dev_cli/commands/hub_layering_guard.py` (the guard, and the `RUNTIME_LAYER_PACKAGES` declaration) and `tests/unit/pipelex/test_runtime_layer_import_closure.py` (the closure test, and the `INTERPRETER_PACKAGES` declaration). They state the two halves of one boundary and they are edited together; read both before touching either.
