# TODOS — split `pipelex.hub` into `runtime_hub` + `interpreter_hub`

**Worktree:** `_hub/` · **Branch:** `refactor/Hub` (off `origin/dev`, base `f23fda7a0` = v0.40.0) · **PR:** [#1062 → `dev`](https://github.com/Pipelex/pipelex/pull/1062), open.

**Status:** **ALL PHASES DONE + THE RENAME LANDED — all gates green.** Branch `refactor/Hub` is pushed and PR #1062 is open. **Jump to [▶ Resume here](#-resume-here-the-rename-is-landed) first.**

The split is landed, the boundary is mechanically enforced (`make check-hub-layering` + a subprocess import-closure test over eight entry points), the misplaced types are moved, and core's data model has joined the runtime layer behind injected providers. Every runtime-layer entry point measures **0 interpreter modules**. Docs and the CHANGELOG breaking-change note are written, and the [runtime/interpreter rename](wip/hub/layer-and-hub-renaming.md) is applied throughout.

**What is left is not a phase** — it is the release-gated [cross-repo sweep](#cross-repo-sweep) (three waves). Nothing else is open.

### Cold start — read in this order

1. [The one rule](#the-one-rule) and [Symbol partition](#symbol-partition) — the settled boundary.
2. [Checkpoint H-4 record](#checkpoint-h-4-record) — **start here**: why the plan's "all of `core/` goes low" premise was wrong, the `if it names a Pipe, it is high` rule that replaced it, and the injected-provider pattern.
3. [Checkpoint H-3 record](#checkpoint-h-3-record) — the two type moves, why `TraceContext` had to travel with `JobMetadata`, and why the templating primitives split across two packages.
4. [Checkpoint H-2 record](#checkpoint-h-2-record) — what the guard actually enforces (two rules, not one), its two carve-outs, and two CI wiring traps.
5. [Checkpoint H-1 record](#checkpoint-h-1-record) — the split itself, including the two places reality forced a change to the plan (the D5 slot could not live on `RuntimeHub`; boot was deliberately not reordered).
6. [`docs/contribute/hub-layering.md`](docs/contribute/hub-layering.md) — the shipped specification: the two halves, "Where core splits", enforcement, and "Placement, not coupling".

Three notes for whoever picks this up:

- **The cross-repo sweep is the only substantial work remaining, and it is release-gated.** Three waves now: the `pipelex.hub` split ([table](#cross-repo-sweep)), the Phase 3 type moves ([table](#cross-repo-impact-added-by-phase-3)), and the Phase 4 moves + signature changes ([table](#cross-repo-impact-added-by-phase-4)). Do all three in one pass per repo.
- **The `hub-layering-convention` drift contract is now in the manifest.** Louis gave explicit say-so; it was added, reviewed, and acked — see [Proposed, reverted, then landed](#proposed-reverted-then-landed).
- **`core.pipes.pipe_output → pipeline.pipeline_models` was NOT removed.** H-3 predicted Phase 4 would take it out; it did not. It remains one of the two edges pulling non-inference modules into the inference closure, which is why the module/SLOC rows are flat at H-4. The reason recorded at H-4 — "`pipe_output` is on the Pipe-touching (high) side of the core split" — was **wrong**, and the PR #1062 review corrected it: `pipe_output` names no `Pipe`, imports zero interpreter modules, and sits inside `runtime_hub`'s own closure. It is runtime-layer. What survives is the edge itself: `SpecialPipelineId` is a leaf constant filed in an interpreter-named package. See [`wip/pr-1062-review-notes.md`](wip/pr-1062-review-notes.md).
- **The PR #1062 agent-review pass is recorded in [`wip/pr-1062-review-notes.md`](wip/pr-1062-review-notes.md).** It fixed the `pipe_output` misclassification above, widened the import-closure predicate to name core's Pipe machinery (closing a real `core.pipes.pipe_blueprint` blind spot), and deferred one item: `pipeline` / `pipe_run` / `graph` leak leaf models into every runtime closure, so the predicate cannot name them yet.

Design rationale, alternatives considered, and the full measured argument live in [`wip/hub/hub-split-refactor.md`](wip/hub/hub-split-refactor.md). This file is the executable tracker: what to do, in what order, with the concrete tables the work needs. Where the two disagree, this file wins — it carries the settled decisions and the re-measured numbers.

ℹ **The names in this document are the final ones.** Louis challenged the Phase 0–4 naming at the close of H-4 and settled on a rename, which has since **landed as its own commit**: the layers are **runtime** / **interpreter**, and the hubs are `runtime_hub` (`RuntimeHub`) / `interpreter_hub` (`InterpreterHub`). This tracker has been swept to those names — including the cross-repo tables, so the sweep rewrites external repos exactly once, straight to the final names. The intermediate `service_hub` / `method_hub` names never shipped. The decision, the rejected alternatives, and the mechanical plan are in [`wip/hub/layer-and-hub-renaming.md`](wip/hub/layer-and-hub-renaming.md); [D1](#decisions) keeps the original naming decision's reasoning verbatim.

Note that the prose below still uses "low layer" / "high layer" in the historical checkpoint records (H-1 through H-4), because that was the vocabulary at the time. Read *low* as **runtime** and *high* as **interpreter**; the shipped code, tests, guard and docs use only the new terms.

## The one rule

`interpreter_hub` may import `runtime_hub`. **`runtime_hub` must never import `interpreter_hub`.** That single arrow is the whole architecture, and it is what the Phase 2 guard checks.

> At H-1 only the forbidden direction is load-bearing; the permitted one turned out to be unused, because the one low-layer thing `interpreter_hub` needs (the class-registry scoping slot) lives below *both* hubs. Importing either hub loads the other in neither direction — stronger than the rule requires. Phase 2's guard should still check the forbidden direction, not assert the permitted one exists.

`pipelex/hub.py` is deleted outright — not kept as an alias for either half. A stale import must fail loudly at import time rather than silently resolve to the wrong layer.

## Baseline — measured on the base commit

Reproduce with the snippet in [Exit criteria](#exit-criteria--measured-not-asserted). Re-taken at CHECKPOINT H-1 — the after is in [Measured after](#measured-after).

| | baseline | target after Phase 1 |
| --- | --- | --- |
| interpreter modules loaded by `cogt.content_generation.content_generator` | 50 | **0** |
| pipelex modules loaded | 357 | ≤ 260 |
| SLOC loaded | 29,193 | ≤ 19,000 |

Call-site inventory (`ast`-parsed over `pipelex/` + `tests/`, zero symbols left unclassified by the partition below):

| | count |
| --- | --- |
| files importing `pipelex.hub` | 309 |
| — low-only | 134 |
| — high-only | 139 |
| — straddling (gain a second import line) | 36 |
| parenthesized multi-line import blocks | 29 |
| `PipelexHub()` construction sites | 5 (2 production, 3 test) |
| `importlib.import_module("pipelex.hub")` hacks | 3 |

## Decisions

**D1 — module names. SUPERSEDED by the [runtime/interpreter rename](wip/hub/layer-and-hub-renaming.md); the modules are now `pipelex/runtime_hub.py` + `pipelex/interpreter_hub.py`.** The original decision, kept because its rejected alternatives are still live reasoning: *SETTLED: `pipelex/service_hub.py` + `pipelex/method_hub.py`, both flat at the package root, `pipelex/hub.py` deleted. Rejected: keeping `hub.py` for one half (a stale import would silently succeed); `library_hub` (the high half also holds the router, the runner, and the pipeline manager); a `pipelex/hubs/` package (`pipelex.hubs.services` reads worse than `pipelex.service_hub` at 300+ call sites). Noted for review: `method_hub` borrows the MTHDS noun for a runtime container — acceptable because the object genuinely holds the loaded method's libraries, but it is a conscious call against the brand-boundary rule.* That last note is exactly what Louis acted on at the close of H-4: the flat-at-the-root shape and the no-alias deletion survive unchanged, only the two names moved. `library_hub` was re-proposed and re-rejected during the rename, on the same grounds plus one more — a library is inert, while the container is active machinery.

**D2 — one container or two. SETTLED: two** — `RuntimeHub` and `InterpreterHub`, each its own singleton, each with its own module-level accessors. One container would have to live in the low module, forcing every high-level slot to a quoted `TYPE_CHECKING` annotation — that keeps the god-object and adds a fig leaf. Two is affordable: the construction surface is five sites total.

**D3 — where `get_pipe_func_executor_registry` lands. SETTLED: high (`interpreter_hub`).** It is a plugin registry by kind but its protocol lives in `pipe_operators/func/`. The underlying inversion — `pipelex/plugins/pipe_func_executor_registry.py` importing from `pipe_operators/` — is recorded as a follow-up (see [Known inversions](#known-inversions-not-fixed-here)), not fixed here.

**D4 — does `core/` join the low layer now? SETTLED: no, not in Phase 1.** Five `core/` modules use high-hub symbols; converting them means passing resolved concepts in rather than looking them up, which is design work, not mechanical. Phase 4 does it, and the guard's low-layer set widens only when that lands.

**D5 — `get_class_registry` is low but reads the library manager. SETTLED: callable resolver slot, defaulting to "no scoping", installed downward at boot.** Not in the design doc; surfaced while building the partition table. It is the decision that makes Phase 1.6 possible at all, so it is recorded here in full.

> **Amended at implementation (H-1): the slot does not live on `RuntimeHub`.** It lives in a new leaf module, `pipelex/system/registries/class_registry_access.py`, reached through the `class_registry_scoping` module singleton. The mechanism, the default, and the downward-at-boot crossing are all exactly as designed below — only the physical home moved, and it was forced by a measured cycle rather than chosen. See [Checkpoint H-1 record → D5 amendment](#d5-amendment-the-resolver-slot-could-not-live-on-servicehub).

Today's body reaches straight into the high layer:

```python
def get_class_registry() -> ClassRegistryAbstract:
    library_id = _library_id.get()
    if library_id is not None:
        registry = get_library_manager().get_library_class_registry(library_id)   # ← HIGH
        if registry is not None:
            return registry
    return KajsonManager.get_class_registry()
```

`get_class_registry` is the single symbol all three `importlib` hacks want, and it has 29 importers spread across both layers — so it must be low, and it must keep its library scoping (Phase 1 is zero-behavior-change).

Resolution: `RuntimeHub` grows a `Callable[[], ClassRegistryAbstract | None]` slot — default returns `None`, and boot installs the library-scoped resolver once `InterpreterHub` is populated. `get_class_registry` calls the slot and falls back to `KajsonManager.get_class_registry()`. The `_library_id` ContextVar stays in `interpreter_hub` with the rest of its family; the resolver closure is what crosses, and it crosses downward at boot, not as an import.

This is not a new pattern — it is exactly how `_isolated_execution_probe` already works (`HubSlot.ISOLATED_EXECUTION_PROBE`, defaulting to `_never_in_isolated_execution`), so the precedent, the naming, and the plugin-claim machinery are all in place.

Alternative considered and rejected: move the whole `_library_id` contextvar family down into `runtime_hub`. Simpler (no indirection) but it splits the "current library" concept across both modules and makes `pipelex.runtime_hub` export `set_current_library`, which reads wrong. Also rejected: drop the scoping from `get_class_registry` and expose a separate high `get_scoped_class_registry` — that is a behavior change, and `tests/unit/pipelex/test_class_registry_scoping.py` pins the current semantics.

`tests/unit/pipelex/test_class_registry_scoping.py` is the regression guard for D5 — it must keep passing unmodified except for its import lines.

## Symbol partition

Complete and verified: an `ast` sweep of every `from pipelex.hub import …` across `pipelex/` and `tests/` classified every imported name against these two sets with nothing left over.

### → `pipelex/runtime_hub.py` (runtime layer)

| group | symbols |
| --- | --- |
| container | `RuntimeHub`, `get_runtime_hub`, `set_runtime_hub` |
| config | `get_required_config`, `get_optional_config` |
| console | `get_console` |
| secrets | `get_secrets_provider`, `get_secret` |
| system registries | `get_class_registry` (see D5), `get_func_registry` |
| storage | `get_storage_provider` |
| telemetry | `get_telemetry_manager`, `get_otel_tracer` |
| models | `get_models_manager`, `get_model_deck`, `get_sdk_client_manager` |
| inference | `get_inference_manager`, `get_llm_worker`, `get_img_gen_worker`, `get_extract_worker` |
| content generation | `get_content_generator`, `scoped_content_generator` |
| reporting | `get_report_delegate`, `is_in_isolated_execution` |
| run mode | `is_dry_run_forced` |
| tracing | `scoped_event_log`, `get_event_log_override` |
| plugin registries | `get_inference_backend_registry`, `get_model_lister_registry`, `get_orchestrator_registry`, `get_bundle_validator_registry`, `get_storage_provider_registry`, `get_secrets_provider_registry` |

### → `pipelex/interpreter_hub.py` (interpreter layer)

| group | symbols |
| --- | --- |
| container | `InterpreterHub`, `get_interpreter_hub`, `set_interpreter_hub` |
| library manager | `get_library_manager`, `get_library` |
| library lookups | `get_concept_library`, `get_required_concept`, `get_native_concept`, `get_required_domain`, `get_optional_domain`, `get_pipe_library`, `get_pipes`, `get_required_pipe`, `get_optional_pipe`, `get_pipe_source` |
| current-library contextvar | `set_current_library`, `get_current_library`, `get_current_library_id_or_none`, `clear_current_library`, `scoped_current_library` |
| library dirs | `resolve_library_dirs`, `get_default_library_dirs` |
| pipe router | `get_pipe_router`, `set_pipe_router`, `teardown_current_pipe_router`, `scoped_pipe_router` |
| run | `get_pipe_run`, `get_pipeline_manager`, `get_pipeline` |
| pipe func (D3) | `get_pipe_func_executor`, `scoped_pipe_func_executor`, `get_pipe_func_executor_registry` |

Setter methods follow their getters onto the matching container. Do **not** delete the accessors with no in-tree importers (`get_bundle_validator_registry`, `get_orchestrator_registry`, `get_pipe_func_executor_registry`, `get_default_library_dirs`, `get_func_registry`, `scoped_pipe_func_executor`) — they are reached internally via the container and several are live external plugin contract (see [Cross-repo sweep](#cross-repo-sweep)). Placement is decided by kind, not by in-tree usage.

### Straddling files — hand-review list for step 1.4

These are the only files that gain a second import line. Everything else is a one-line module swap.

| file | low symbols | high symbols |
| --- | --- | --- |
| `pipelex/cli/commands/build/inputs/_inputs_core.py` | `get_telemetry_manager` | `get_library_manager`, `get_required_pipe`, `resolve_library_dirs`, `set_current_library` |
| `pipelex/cli/commands/build/output/_output_core.py` | `get_telemetry_manager` | `get_library_manager`, `get_required_pipe`, `resolve_library_dirs`, `set_current_library` |
| `pipelex/cli/commands/build/runner/_runner_core.py` | `get_telemetry_manager` | `get_current_library_id_or_none`, `get_library_manager`, `get_required_pipe` |
| `pipelex/cli/commands/codegen/inputs_cmd.py` | `get_telemetry_manager` | `get_required_pipe` |
| `pipelex/cli/commands/show_cmd.py` | `get_console`, `get_models_manager`, `get_secrets_provider`, `get_telemetry_manager` | `get_library_manager`, `get_pipe_library`, `get_required_pipe`, `resolve_library_dirs`, `set_current_library` |
| `pipelex/cli/commands/validate/_validate_core.py` | `get_console`, `get_telemetry_manager` | `get_library_manager`, `get_pipe_library`, `get_pipes`, `get_required_pipe`, `resolve_library_dirs`, `set_current_library` |
| `pipelex/cli/commands/which_cmd.py` | `get_console`, `get_telemetry_manager` | `get_library_manager`, `get_optional_pipe`, `get_pipe_source`, `resolve_library_dirs`, `set_current_library` |
| `pipelex/core/stuffs/stuff_factory.py` | `get_class_registry` | `get_concept_library`, `get_native_concept`, `get_required_concept` |
| `pipelex/libraries/library_manager.py` | `get_class_registry` | `get_current_library`, `get_current_library_id_or_none`, `scoped_current_library` |
| `pipelex/pipe_operators/compose/pipe_compose.py` | `get_class_registry` | `get_concept_library`, `get_native_concept` |
| `pipelex/pipe_operators/extract/pipe_extract.py` | `get_content_generator`, `get_model_deck` | `get_concept_library`, `get_native_concept` |
| `pipelex/pipe_operators/func/pipe_func.py` | `get_class_registry` | `get_pipe_func_executor` |
| `pipelex/pipe_operators/img_gen/pipe_img_gen.py` | `get_class_registry`, `get_content_generator`, `get_model_deck` | `get_concept_library`, `get_native_concept` |
| `pipelex/pipe_operators/llm/helpers.py` | `get_class_registry` | `get_required_concept` |
| `pipelex/pipe_operators/llm/pipe_llm.py` | `get_class_registry`, `get_content_generator`, `get_model_deck` | `get_concept_library`, `get_native_concept`, `get_required_concept` |
| `pipelex/pipe_operators/structure/pipe_structure.py` | `get_class_registry`, `get_content_generator`, `get_model_deck` | `get_concept_library`, `get_native_concept` |
| `pipelex/pipe_run/dry_run_in_process.py` | `scoped_content_generator`, `scoped_event_log` | `get_library_manager`, `scoped_pipe_router` |
| `pipelex/pipeline/bundle_validator.py` | `get_telemetry_manager`, `scoped_content_generator` | `clear_current_library`, `get_current_library`, `get_current_library_id_or_none`, `get_library_manager`, `get_pipe_library`, `scoped_pipe_router`, `set_current_library` |
| `pipelex/pipeline/pipeline_run_setup.py` | `get_event_log_override`, `get_otel_tracer`, `get_report_delegate`, `get_telemetry_manager` | `clear_current_library`, `get_current_library_id_or_none`, `get_library_manager`, `get_pipeline_manager`, `get_required_pipe`, `set_current_library` |
| `pipelex/pipeline/runner.py` | `get_report_delegate`, `get_telemetry_manager` | `clear_current_library`, `get_current_library_id_or_none`, `get_library_manager`, `get_pipe_run`, `get_pipeline_manager`, `set_current_library` |
| `tests/integration/pipelex/pipeline/test_bundle_validator.py` | `get_telemetry_manager` | `clear_current_library`, `get_library_manager`, `get_required_pipe` |
| `tests/integration/pipelex/pipeline/test_pipeline_run_setup_characterization.py` | `get_report_delegate`, `get_telemetry_manager` | `clear_current_library`, `get_current_library_id_or_none`, `get_library_manager`, `get_pipeline_manager`, `set_current_library` |
| `tests/integration/pipelex/pipeline/test_pipeline_run_setup_emit_gates.py` | `get_report_delegate` | `clear_current_library`, `get_library_manager` |
| `tests/integration/pipelex/pipes/controller/pipe_parallel/test_pipe_parallel_absence.py` | `get_class_registry` | `get_concept_library`, `get_pipe_library` |
| `tests/integration/pipelex/pipes/controller/pipe_parallel/test_pipe_parallel_branch_type_validation.py` | `get_class_registry` | `get_concept_library`, `get_pipe_library` |
| `tests/integration/pipelex/pipes/controller/pipe_parallel/test_pipe_parallel_unresolvable_structure_class.py` | `get_class_registry` | `get_concept_library`, `get_pipe_library` |
| `tests/integration/pipelex/pipes/operator/pipe_llm/test_pipe_llm.py` | `get_class_registry` | `get_native_concept`, `get_pipe_library`, `get_pipe_router` |
| `tests/integration/pipelex/pipes/operator/pipe_llm/test_pipe_llm_date_output_path.py` | `get_content_generator` | `get_pipe_library`, `get_pipe_router` |
| `tests/integration/pipelex/pipes/operator/pipe_llm/test_pipe_llm_yes_no_output_path.py` | `get_content_generator` | `get_pipe_library`, `get_pipe_router` |
| `tests/integration/pipelex/pipes/operator/pipe_structure/test_preliminary_text_e2e.py` | `get_report_delegate` | `get_native_concept`, `get_pipe_router`, `get_required_pipe` |
| `tests/integration/pipelex/pipes/operator/pipe_structure/test_preliminary_text_inline_e2e.py` | `get_report_delegate` | `get_native_concept`, `get_pipe_router`, `get_required_pipe` |
| `tests/integration/pipelex/pipes/optionals/test_parallel_optional_combine_validation.py` | `get_class_registry` | `get_concept_library`, `get_pipe_library` |
| `tests/integration/pipelex/system/test_hub_slot_injection_precedence.py` | `get_content_generator` | `get_pipe_router` |
| `tests/unit/pipelex/core/memory/input_shaper/conftest.py` | `get_class_registry` | `get_concept_library` |
| `tests/unit/pipelex/core/stuffs/test_stuff_factory_implicit_memory.py` | `get_class_registry` | `get_concept_library` |
| `tests/unit/pipelex/test_class_registry_scoping.py` | `get_class_registry` | `clear_current_library`, `get_library_manager`, `set_current_library` |

Note the shape of the `pipe_operators/` rows: every one of them straddles for the same reason — `get_class_registry` / `get_content_generator` / `get_model_deck` (low) next to `get_concept_library` / `get_native_concept` (high). That is the D4 boundary showing through, and it is what Phase 4 dissolves.

## Phases

### Phase 0 — declare the boundary ✅

- [x] 0.1 Confirm **D5**. Settled as recorded above, and amended at implementation (the slot's home moved; the mechanism did not).
- [x] 0.2 Baseline re-taken on the branch tip and confirmed identical to the table above (357 / 29,193 / 50).
- [x] 0.3 Wrote [`docs/contribute/hub-layering.md`](docs/contribute/hub-layering.md) — the two hubs, the partition, how to place a new symbol, the class-registry exception, the measurement, enforcement, and the known inversions. Modelled on `keyword-only-arguments.md`. Its "Enforcement" section describes what is true at H-1 and is rewritten by Phase 2 when the guard lands.
- [x] 0.4 Updated `docs/under-the-hood/architecture-overview.md` with a "What Keeps The Layers Apart: The Two Hubs" section naming the boundary and the one-arrow rule, linking to the contributor doc. Added both pages to the `mkdocs.yml` nav.

### Phase 1 — the split ✅

- [x] 1.1 Created `pipelex/runtime_hub.py`. Module-level imports verified to name nothing from `libraries`, `pipe_operators`, `pipe_controllers`, `codegen`, `builder`, `core.bundles`, `core.concepts`, or `core.pipes`.
- [x] 1.2 Created `pipelex/interpreter_hub.py`, importing `runtime_hub`'s layer for the D5 install. `set_interpreter_hub` installs the resolver, so scoping is live exactly when a InterpreterHub exists and a caller cannot forget to wire it.
- [x] 1.3 Deleted `pipelex/hub.py`.
- [x] 1.4 Rewrote all 309 call sites via an `ast` pass over the whole import statement (the 29 parenthesized blocks came through intact). The 36 straddlers each gained a second import line, as predicted. **Two string-literal references the AST pass could not see broke the suite and had to be found by running it** — see the record below.
- [x] 1.5 Re-wired boot. Both hubs are constructed and installed at the top of `Pipelex.__init__`; every setter was retargeted to its own container. **The setter sequence was deliberately NOT reordered** — see the record below.
- [x] 1.6 Replaced all three `importlib.import_module("pipelex.hub")` hacks with plain top-level imports and deleted the `_get_class_registry` shims. The import target is the new leaf module, not `runtime_hub` — that is the D5 amendment.
- [x] 1.7 `Pipelex.teardown` and the `make()` failure path now release both hubs' process-global state. Pinned by `tests/unit/pipelex/test_hub_lifecycle.py`, which asserts a boot installs both singletons and that the reset really drops the scoping a InterpreterHub installed.

**CHECKPOINT H-1** — zero behavior change.

Gates: `make agent-check` + **full** `make agent-test` (no test edits beyond import lines) + `make drift-check`. Expect the **`cli-docs` drift contract to fire** — `pipelex/cli/**/*.py` is a trigger and the rewrite touches many CLI files. Review `docs/tools/cli/` and `pipelex/cli/agent_cli/CLAUDE.md`, then `make drift-ack` with an honest rationale ("import-path-only change, CLI surface unaffected" is legitimate if that is what the review found). Re-take the measurement and record the after against the target table.

### Checkpoint H-1 record

Written at the checkpoint so Phase 2 can start cold. Everything below is what actually happened, including where the plan was wrong.

#### Measured after

| | baseline | target | **after H-1** |
| --- | --- | --- | --- |
| interpreter modules loaded by `cogt.content_generation.content_generator` | 50 | **0** | **0** ✅ |
| pipelex modules loaded | 357 | ≤ 260 | 275 |
| SLOC loaded | 29,193 | ≤ 19,000 | 21,186 |

The headline property is met exactly: the inference layer now loads **zero** `libraries` / `pipe_operators` / `pipe_controllers` / `codegen` / `builder` modules. The module and SLOC targets were missed, and the reason is that the estimate was wrong rather than the change: those targets were derived from "236 modules / 17,683 SLOC *plus headroom for cogt's own modules*", and the real headroom is ~40 modules / ~3,500 SLOC, not the ~24 / ~1,300 assumed. A low-only hub's own closure measures 235 modules / 17,675 SLOC on this branch — within 1 of the estimate — so the partition is exactly as tight as designed; only the headroom guess was low. **Do not treat the module/SLOC rows as open work.** Squeezing them further means attacking `cogt`'s own dependency weight (`system.telemetry.otel_factory` → `core.pipes.pipe_output` → `core.stuffs.stuff` is the fattest edge), which is Phase 3/4 territory, not the hub boundary.

#### D5 amendment: the resolver slot could not live on `RuntimeHub`

D5 assumed `core/concepts/` could reach `get_class_registry` from `pipelex.runtime_hub`. It cannot. `core.concepts.concept` is **inside `runtime_hub`'s own import closure**:

```
runtime_hub → cogt.llm.llm_worker_abstract → system.telemetry.otel_factory
            → core.pipes.pipe_output → core.stuffs.stuff → core.concepts.concept
```

so a module-level `from pipelex.runtime_hub import get_class_registry` in `concept.py` is a hard cycle — and it fails in *both* import orders, which is why it could not simply be ordered around. The design doc's claim that "a hub that does not import `Concept` has no cycle with `concept.py`" was half right: the cycle is not via `Concept`, it is via `cogt → system → core`.

Resolution, which preserves every property D5 was chosen for:

- `pipelex/system/registries/class_registry_access.py` — a new leaf module importing nothing from `pipelex`. Holds the real `get_class_registry` plus the `class_registry_scoping` slot (a module singleton in the `config_manager` style; the resolver default returns `None`, so a RuntimeHub-only process degrades to the global registry rather than raising, exactly as [Risks](#risks-and-containment) requires).
- `pipelex.runtime_hub.get_class_registry` delegates to it and stays the **public** accessor — so the symbol partition table above is unchanged and the cross-repo contract is still "low symbols come from `runtime_hub`".
- The three `core/concepts/` modules import the leaf directly, because they are the one place the public accessor is unreachable.
- `interpreter_hub.set_interpreter_hub` installs the library-scoped resolver; `Pipelex.teardown` calls `class_registry_scoping.reset()`.

`tests/unit/pipelex/test_class_registry_scoping.py` (the D5 regression guard) passes unmodified except for its import lines, as required.

#### Boot was not reordered — deliberately

Step 1.5 predicted the setter sequence would "split cleanly at line 475 with no reordering" once the duplicate pair was deleted. It does not, and cannot: **D3 puts the PipeFunc executor on the high hub**, so `set_pipe_func_executor_registry` and `set_pipe_func_executor` are InterpreterHub calls sitting in the middle of the RuntimeHub run, and `set_isolated_execution_probe` is a RuntimeHub call sitting after the InterpreterHub ones.

Reordering to force a clean split would have moved setters across documented ordering dependencies (the storage-provider block explicitly resolves *after* secrets is on the hub so the GCP factory's secret read works) — a real behavior risk at a checkpoint whose bar is zero behavior change. So: **both hubs are constructed and installed at the top of `__init__`, and the setter sequence is otherwise byte-identical in order.** That delivers what "populate RuntimeHub fully before InterpreterHub" was actually protecting against — no setter can ever run against a missing hub — without touching execution order. Untangling the interleave belongs with D3's inversion, not here.

#### Findings in passing — both resolved, one bigger than recorded

- **Duplicate `set_library_manager` deleted** ✅. Confirmed dead: nothing between the two pairs reads it, and `make tb` plus the full suite pass without it.
- **`_observer` deleted** ✅ — but the tracker's "confirm no external consumer sets it" check turned up something worse than dead code. `docs/advanced/observer-provider-injection.md` **documented `hub.set_observer()` as the public way to register a custom observer**, and that documented API never worked: the value was written and never read, while the live path is `Pipelex.make(observers={...})` → `MultiObserver` → `PipeRouter`. Anyone following that page got a silently ignored observer. Both that page and `docs/advanced/index.md` (which showed a bare `PipelexHub()` being constructed and configured — equally inert) are rewritten to the mechanism that actually works, with a warning against hand-constructing a hub. Verified across the workspace: no repo sets `set_observer`.

#### One fix outside the plan, required by the exit criterion

After the split the measurement still reported 3 interpreter modules, via `content_generator → pipelex.config → plugins.pipe_func_executor_registry → pipe_operators.func.pipe_func_executor_protocol` — D3's underlying inversion, which [Known inversions](#known-inversions-not-fixed-here) had scheduled as "not fixed here". But the exit criterion demands 0 and instructs that the printed offender is what to fix, and Phase 2.5's closure regression test would fail on it regardless. The import is **type-only**, so it was deferred under `TYPE_CHECKING` with a string annotation on the type alias. The placement inversion itself is untouched and stays recorded.

#### Landmines the AST rewrite could not see

`pipelex.hub` ceasing to exist turns a missed *import* into an immediate `ImportError` — but not a missed **string literal**. Two of those existed, and neither is reachable by an import-graph tool:

- `tests/helpers/init_cmd_helpers.py` — `mocker.patch("pipelex.hub.get_console", ...)`. This broke **36 tests** across the init CLI suites, and the failure surfaced as `AttributeError: module 'pipelex' has no attribute 'hub'` from `pkgutil.resolve_name`, nowhere near the hub.
- `tests/unit/pipelex/cli/test_agent_cli_output_discipline.py` — `mocker.patch("...agent_cli_factory.PipelexHub.get_optional_instance")`, caught by grep before the run.

If Phase 2's guard is meant to catch "the string-literal `importlib.import_module` form", it should also be pointed at `mocker.patch` targets — that is where this class of reference actually lives in this repo.

#### Housekeeping done at H-1

- **Subject grants migrated**: 54 `pipelex/hub.py::` entries → 55 under `pipelex/runtime_hub.py::` / `pipelex/interpreter_hub.py::` (`set_instance` and `set_pipelex_hub` each split in two; `set_observer` dropped with the state). `make cko` is green, and staleness is symmetric so a missed entry would have failed.
- **Doc references swept**: `docs/under-the-hood/{pipe-routing-and-execution,runtime-bridge-and-transport,execution-graph-tracing}.md`, `docs/advanced/{index,observer-provider-injection}.md`, `tests/CLAUDE.md`, and in-code docstrings in `signature_walk.py` / the keyword-only guard modules. CHANGELOG history entries were left alone (they are release records). No live `pipelex.hub` reference remains anywhere in `pipelex/`, `tests/`, or `docs/`.

#### Still open at H-1

- **The CHANGELOG breaking-change note is not written yet** — it stays scheduled at H-4 per the plan, but `pipelex.hub` is *already* gone as of this checkpoint. If this branch is ever merged before H-4, write it first.
- The **cross-repo sweep** is untouched and still release-gated.
- One semantic edge worth knowing: `class_registry_scoping` is process-global, so the doctor path (which installs a fresh `RuntimeHub` but leaves any existing `InterpreterHub` in place) now keeps library scoping alive where the single hub would have raised. Strictly more coherent — the InterpreterHub genuinely is still installed — and unreachable in practice, since doctor runs in its own process. Noted rather than fixed.

### Phase 2 — enforce it ✅

- [x] 2.1 Added `pipelex-dev check-hub-layering` — guard in `pipelex/cli/dev_cli/commands/hub_layering_guard.py` (stdlib-only AST core), command in `check_hub_layering_cmd.py` (rich presentation), following the `keyword_only_guard.py` / `check_keyword_only_cmd.py` split exactly. Catches imports **and** string literals, and resolves relative imports against the importing module's own package. **The guard grew a second rule beyond the plan** — see the record below.
- [x] 2.2 Low layer declared as `pipelex.cogt`, `pipelex.plugins`, `pipelex.reporting`, `pipelex.system`, `pipelex.tools`. All five compliant; the guard hard-blocks with an empty exception list (one escape-hatch marker exists, on the guard's own declaration of the forbidden path).
- [x] 2.3 Wired into `make agent-check`, the `make check` aggregate, and both CI lint workflows, with the `chl` alias.
- [x] 2.4 `tests/unit/pipelex/cli/dev/test_hub_layering_guard.py` — layer membership, both directions of the arrow, every import spelling (plain / aliased / `from pipelex import interpreter_hub` / relative), both string forms, the prose-is-not-a-reference and `runtime_hub`-is-not-`hub` boundary cases, the `TYPE_CHECKING` carve-out and its three non-exempt neighbours, the escape hatch, and the dead-module rule across all three layers.
- [x] 2.5 `tests/unit/pipelex/test_runtime_layer_import_closure.py` — imports each low-layer entry point in a subprocess and asserts zero interpreter modules **and** no `pipelex.interpreter_hub` in `sys.modules`. Parametrized over two entry points: the inference layer and `runtime_hub` itself.

**CHECKPOINT H-2** — boundary declared, enforced, and regression-tested.

### Checkpoint H-2 record

Gates: `make agent-check` ✅ (pyright 0 errors, mypy 2,352 files, keyword-only PASSED, hub-layering PASSED) · `make agent-test` ✅ (full suite) · `make drift-check` ✅ (no contract opened — see below).

#### The guard enforces two rules, not one

The plan specified one rule (no `interpreter_hub` in the low layer). The guard ships with a second: **no module anywhere in `pipelex/` or `tests/` may reference `pipelex.hub`.** That is the H-1 note about `mocker.patch` targets, generalized — and generalizing it is what makes it work. The plan framed the string check as an `importlib.import_module` special case; scanning *every* string constant for an exact-or-boundary match on the module path catches `importlib`, `mocker.patch`, `pkgutil.resolve_name`, and any config-driven dotted path in one mechanism, with no call-site special-casing.

Scope follows from the two rules being different: `tests/` is scanned for the dead-module rule **only**. `tests.*` is in no declared layer, so a test may still freely patch `pipelex.interpreter_hub` — while a stale `pipelex.hub` patch target, the thing that actually broke 36 tests, now fails the check.

Matching is exact-or-boundary (`==`, or a `.`/`:` suffix), which is why `pipelex.runtime_hub` does not match `pipelex.hub` and why a docstring that merely *mentions* a module is not a reference. Two in-tree docstrings do exactly that and are correctly ignored. A path assembled at runtime from f-strings is beyond any AST scan; nothing does that today, and it is noted in the module docstring rather than defended against.

#### Two carve-outs, both deliberate

- **`if TYPE_CHECKING:` is exempt from the layer rule, not from the dead-module rule.** The rule is about what *loads*; a type-only import loads nothing, and H-1's own out-of-plan fix used exactly this deferral. Its `else` branch, `if not TYPE_CHECKING:`, and any `pipelex.hub` import inside a `TYPE_CHECKING` block all stay violations — each is pinned by a test.
- **`# hub-layering: ignore`** mirrors `# kw-only: ignore`. There is exactly one in `pipelex/` and one in the test suite, both on lines that *declare* the forbidden path as data. The guard flagged its own configuration on first run, which is a good sign about the matcher and the reason the hatch exists.

#### Verified by breaking it, not only by unit tests

Both forms were injected into a real low-layer module (`cogt/content_generation/content_generator.py`) and the CLI was confirmed to report them at the right lines with the right kinds, then the file was restored byte-identically. Snippet-level unit tests would not have caught a filesystem-walk or layer-membership mistake.

#### Two wiring traps worth knowing

- **The CI aggregator gates on an explicit bash result check, not on `needs`.** Adding `lint-hub-layering` to `lint-all`'s `needs` list is *not* enough — `if: always()` means the aggregator runs regardless, and the `[ "${{ needs.<job>.result }}" != "success" ]` chain is what actually fails the build. Both were updated. A new lint job added without touching that chain would be silently advisory.
- **A new job, not a step on `lint-keyword-only`.** Folding both AST guards into one job would have meant renaming it, and that job name may be a required status check — a rename silently un-requires it. The repo already runs one job per guard; this follows that.

#### Proposed, reverted, then landed

A `hub-layering-convention` drift contract (triggers: the guard + both hub modules; review: `docs/contribute/hub-layering.md`) is the exact analogue of the existing `keyword-only-convention` contract, and it mechanizes the doc obligation Phase 4 and the rename both carried. It was added at H-2, confirmed to open correctly, then **reverted**: `.claude/skills/drift-review` states that during the pilot the manifest must not grow without the user's explicit say-so, because ack friction is the thing being measured. Left as a decision for Louis rather than a silent addition. Note that `cli-docs` legitimately did not fire on this work — it excludes `pipelex/cli/dev_cli/**`.

**Louis approved it after the rename landed, and it is now in `drift.toml`, reviewed and acked.** It carries no verify command, matching `keyword-only-convention`: `check-hub-layering` already gates `make check` and CI, so re-running it before an ack would add the unstaged-file hard error without adding a guarantee. The initial review is mechanical and worth repeating rather than re-reading — extract every public module-level symbol from both hubs and confirm each appears in the doc's partition tables, then import `RUNTIME_LAYER_PACKAGES` from the guard and confirm every declared package is named under Enforcement. The closure test was deliberately left out of the triggers; it is the obvious first addition if the contract ever proves under-triggered.

#### Docs updated

- `docs/contribute/hub-layering.md` — the "Enforcement" section was rewritten from "a guard is the next step" to the shipped two-rule specification: what each rule checks, why the string half is the load-bearing one, both carve-outs, the `tests/` scoping, and the rule-vs-property split.
- `docs/under-the-hood/architecture-overview.md` — one sentence stating the boundary is mechanically enforced rather than held up by review.

### Phase 3 — the placement residue ✅

Neither item was coupling; both were types living in the wrong package, and each was independently correct. Both are **resolved by moving the type**, not by adding indirection — no resolver slot, no protocol, no `TYPE_CHECKING` deferral was needed for either.

- [x] 3.1 **`JobMetadata`** → `pipelex/system/job_metadata.py` (with `JobCategory`, `UnitJobId`); `JobMetadataError` → `pipelex/system/exceptions.py`. `TraceContext` moved with it → `pipelex/system/trace_context.py`, and `DataInclusionConfig` moved down to `pipelex/system/data_inclusion_config.py` so `trace_context` no longer imports `graph_config`. **`cogt → pipeline` is now 0 statements.**
- [x] 3.2 **`cogt.templating.*`** → moved down to `tools`. `TextFormat` / `TemplatingStyle` / `TagStyle` → `pipelex/tools/templating/`; `TemplateCategory` → `pipelex/tools/jinja2/`. **`tools → cogt` drops from 15 statements to 3** (the `tools/pdf` renderer only).

**CHECKPOINT H-3** — placement residue resolved.

### Checkpoint H-3 record

Gates: `make agent-check` ✅ (pyright 0 errors, mypy 2,354 files, keyword-only PASSED, hub-layering PASSED) · `make agent-test` ✅ (full suite) · `make drift-check` ✅ (no contract opened).

#### Measured after

| | baseline | H-1 | **after H-3** |
| --- | --- | --- | --- |
| interpreter modules loaded by `cogt.content_generation.content_generator` | 50 | 0 | **0** ✅ |
| pipelex modules loaded | 357 | 275 | **268** |
| SLOC loaded | 29,193 | 21,186 | **20,304** |

Cross-package import statements, the number Phase 3 was actually aimed at:

| edge | before | after |
| --- | --- | --- |
| `cogt → pipeline` | 18 | **0** |
| `tools → cogt` | 15 | **3** |
| `graph → cogt` | 2 | **0** |
| `reporting → graph` | 1 | **0** |
| `system → graph` | 1 | 1 (by design — see below) |

The module/SLOC rows moved only a little because the fat edge was never `cogt → pipeline` alone. Two edges still pull `graph` and `pipeline` modules into the inference closure, and **both are out of Phase 3's scope by construction**:

- `system.configuration.configs → graph.graph_config` (→ `mermaid_config`, `reactflow_config`): the main config model must name every subconfig, and the repo's convention is that submodels live in their own sub-packages. This is inherent to the one-big-config design, not a layering defect. It is the surviving `system → graph` edge.
- `core.pipes.pipe_output → pipeline.pipeline_models`: a `core → pipeline` edge, which is **Phase 4 territory**.

Together they account for the 7 `graph.*` and 2 `pipeline.*` modules still in the closure. Do not chase them here.

#### 3.1 — where things landed, and why

`JobMetadata` had to go somewhere `cogt` may import, which means a declared low-layer package. `pipelex/system/` is that package and it already houses `telemetry/otel_context.py` — the sibling transport `JobMetadata` carries alongside `TraceContext`.

`TraceContext` moved **with** it rather than staying in `graph/`. Leaving it would only have renamed the inversion: `system/job_metadata.py → pipelex.graph.trace_context` is a `system → graph` edge, exactly the direction being removed. Its one graph dependency was `DataInclusionConfig`, so that class moved down to `pipelex/system/data_inclusion_config.py` and `graph_config.py` now imports it from there. **The TOML shape is unchanged** — the key is still `[pipelex.pipeline_execution_config.graph_config.data_inclusion]`; only the Python class's home moved. `pipelex.system.trace_context` now has a leaf closure: no `graph`, no `pipeline`.

Two homes were considered and rejected for `TraceContext`: `pipelex/tracing/` (would have created a `system ⇄ tracing` package cycle, since `tracing → system` already exists) and `pipelex/system/telemetry/` (that package is OTel + PostHog; `TraceContext` is the pipelex-native node-tree transport, and conflating them would mislead).

#### 3.2 — why the templating primitives split across two packages

None of the three moved modules named anything from `cogt`, so this was pure misfiling. But they could not all land in one new package:

- `TextFormat`, `TemplatingStyle`, `TagStyle` → `pipelex/tools/templating/`. That package imports nothing from `pipelex` beyond its own sibling — a genuine leaf.
- `TemplateCategory` → `pipelex/tools/jinja2/`, because its entire payload is a map of jinja2 filters (`jinja2_filters`, `jinja2_models`, `jinja2_with_images_filter`). Filing it in `tools/templating/` would have made that package import `tools/jinja2` while `tools/jinja2` imports it back — a cycle inside one layer. As placed, the edges run one way: `tools/mermaid → tools/jinja2 → tools/templating`.

What stays in `cogt/templating/` — `TemplateBlueprint`, the sigil preprocessor, `template_rendering` — belongs there: a blueprint is language-layer, and the rest imports `tools/jinja2` downward.

#### Housekeeping done at H-3

- **Subject grant migrated**: `pipelex/graph/trace_context.py::TraceContext.copy_for_child` → `pipelex/system/trace_context.py::…`. Recorded **before** running any check, per the `fko`-silently-rewrites warning in `CLAUDE.md`. No grants existed for the moved templating modules (the two that do, on `template_preprocessor` / `template_rendering`, did not move).
- **Tests**: `tests/unit/pipelex/pipeline/test_job_metadata_request_id.py` → `tests/unit/pipelex/system/` (self-contained, so the move is free). The two `TraceContext` test modules **stayed** in `tests/unit/pipelex/graph/` — they consume `make_trace_context` and the `data_inclusion_config` / `graph_config` fixtures from that directory's `conftest.py`, which the graph tests use heavily. Splitting the fixture module to mirror the source move would cost more than the tidiness is worth.
- **Docs**: `docs/contribute/hub-layering.md` gained a "Placement, not coupling" section recording both moves and the generalizable lesson, and its "Known inversions" bullet was corrected (`tools → cogt` is now the pdf renderer only). `docs/under-the-hood/execution-graph-tracing.md`'s file-reference table was updated for the two moved modules.
- **`make cleanderived` deletes `tests/integration/pipelex/fixtures/_generated_model_sets.py`**, and pyright then fails on 12 unresolved-import errors that have nothing to do with your change. `make regenerate-test-models-quiet` restores it. Worth knowing before debugging a phantom failure.

#### Cross-repo impact added by Phase 3

These are **new** breakages on top of the `pipelex.hub` split, and they land in the same release-gated sweep:

| repo | files touched by the Phase 3 moves |
| --- | --- |
| `pipelex-temporal/` (private) | 22 |
| `pipelex-mistralai-workflows/` | 6 |
| `pipelex-api/` | 1 |

The import lines to rewrite, in full:

| old | new |
| --- | --- |
| `pipelex.pipeline.job_metadata` | `pipelex.system.job_metadata` |
| `pipelex.graph.trace_context` | `pipelex.system.trace_context` |
| `pipelex.graph.graph_config import DataInclusionConfig` | `pipelex.system.data_inclusion_config import DataInclusionConfig` |
| `pipelex.pipeline.exceptions import JobMetadataError` | `pipelex.system.exceptions import JobMetadataError` |
| `pipelex.cogt.templating.text_format` | `pipelex.tools.templating.text_format` |
| `pipelex.cogt.templating.templating_style` | `pipelex.tools.templating.templating_style` |
| `pipelex.cogt.templating.template_category` | `pipelex.tools.jinja2.template_category` |

Clean (no action): `pipelex-cookbook/`, `cocode/`, `pipelex-worker/`, `pipelex-starter-python/`, `pipelex-relay/`, `sandbox/`.

### Phase 4 — core's data model joins the low layer ✅

- [x] 4.1 Converted the `core/` straddlers to injected providers. **The plan's premise was wrong** — `core/` is two layers, not one, and only its *data model* can be low. See the H-4 record.
- [x] 4.2 Widened the guard's low layer with core's six data-model packages, and added six `pipelex.core.*` entry points to `RUNTIME_LAYER_ENTRY_POINTS`.

**CHECKPOINT H-4** — the boundary is complete, enforced, and measured.

### Checkpoint H-4 record

Gates: `make agent-check` ✅ (pyright 0 errors, mypy 2,356 files, keyword-only PASSED, hub-layering PASSED) · `make agent-test` ✅ (full suite, no test edits beyond the mechanical ones recorded below) · `make drift-check` ✅ (both contracts reviewed and acked — see below).

## ▶ Resume here — the rename is landed

All four phases **and** the runtime/interpreter rename are landed, with all three gates green. The rename's own record is [below](#the-runtimeinterpreter-rename-record); the rest of this section is the H-4 close-out it followed.

The two contracts that were left open on purpose at the H-4 pause were reviewed and acked:

- **`config-docs` — clean-pass.** The only trigger change was one import line in `configs.py` (`TemplatingStyle` moving `cogt.templating` → `tools.templating`, the Phase 3 placement fix); every other trigger file was byte-identical. No config field, default, validator, or TOML key moved. `docs/configuration/` documents no import path, and every Python path the docs *do* cite still resolves.
- **`cli-docs` — clean-pass.** All 10 triggers changed by exactly one import line each (the Phase 4 renderer regroup). Verified against the **live CLI** rather than by reading alone — `pipelex build inputs pipe`, `pipelex build output pipe`, `pipelex-agent inputs pipe` — arguments, flags, format values and defaults all match `docs/tools/cli/`. The behavior-adjacent half of Phase 4 was checked too: no CLI doc cites a Python import path or calls a factory that gained a required `concept_provider`, and the runner codegen emits none. `agent_cli/CLAUDE.md`'s layout map lists only `agent_cli`'s own modules, none of which moved.

Also swept `docs/` and `wip/` for stale references to the H-4 moves (`core.pipes.output.*`, `codegen.resolved_fields`, `core.pipes.inputs.input_renderer`): every remaining hit is intentional historical prose in `hub-layering.md` or this tracker.

**One observation is worth carrying forward, because it is now a pattern rather than an anecdote.** This refactor opened **four contracts across three different ids**, and every one of them was import-path churn. The narrowing proposed in the earlier `config-docs` dogfood entry (scope the trigger to files that define settings) would **not** have prevented today's opening — `configs.py` is squarely inside that narrowed set. The mechanism that would prevent all four is a content-aware digest that ignores changes confined to import statements (and, for `keyword-only-convention`, to comments/docstrings): one manifest-wide change instead of three separate glob surgeries. Recorded in `wip/drift-contracts/dogfood-log.md` as the thing to weigh before any per-contract narrowing — it is evidence for the pilot's keep/narrow/mechanize verdict, not a change to make now.

**Next: [PR #1062](https://github.com/Pipelex/pipelex/pull/1062) is open against `dev`** (base was still exactly `f23fda7a0` at open time, so no merge was needed). The only thing outstanding after it lands is the release-gated cross-repo sweep, already retargeted to the final names. Louis' drift-contract decision is resolved — `hub-layering-convention` is in the manifest, reviewed and acked.

The PR body carries a **reviewer map**, which this diff needs: 528 files, of which ~490 are mechanical import churn. It names the dozen files where the judgment actually lives, and pre-empts the two things that look wrong at a glance — `subject_grants.toml`'s 221/221 re-sort (the registry is machine-written sorted, and was not in sort order before; the parsed mapping is identical modulo renames) and the deliberately un-swept old names in D1, the checkpoint records, and `.drift/acks/`.

### The runtime/interpreter rename — record

Landed as its own commit after H-4, per [`wip/hub/layer-and-hub-renaming.md`](wip/hub/layer-and-hub-renaming.md). Gates: `make agent-check` ✅ · full `make agent-test` ✅ · `make drift-check` ✅.

**Pre-flight was clean.** Grepping the whole workspace — including the private `pipelex-temporal`, the heaviest consumer — turned up **zero** collisions on `runtime_hub` / `RuntimeHub` / `interpreter_hub` / `InterpreterHub`. The only hits were the plan documents themselves.

**A token substitution was the right tool here, and the plan's AST warning did not apply.** Phase 1 needed an `ast` rewrite because it was *splitting* one module into two: each import line had to be classified symbol by symbol, and 29 parenthesized multi-line blocks were the hazard. This rename is 1:1 — no import splits, no classification — so the question is only whether the four tokens ever appear where they must not. They do not: enumerating every whole word in `pipelex/` and `tests/` containing any of them returned exactly the identifiers that should change (`get_method_hub`, `set_service_hub`, the hub-named test functions, and the bare class names). Substring replacement across 332 files, then a re-parse of every file in both trees, was safer than a formatting-preserving AST rewrite and left zero residuals.

**The string-literal landmine was real again, and pre-enumerated.** The H-1 lesson (a missed `mocker.patch` target is invisible to every import-graph tool) held: `tests/helpers/init_cmd_helpers.py` carried `mocker.patch("pipelex.service_hub.get_console", ...)` — the same file, the same shape that broke 36 tests at H-1. Because the sweep was token-based over the whole file rather than import-based, it was caught for free. The other string references were the guard's own configuration, the closure test's entry-point list, and the guard test's patch-target fixtures.

**What the plan under-specified: the enum members in the *test* file.** Step 4 lists the guard's `HubLayeringViolationKind` renames but step 5 lists only the test's constants and patch targets, so a first pass renamed the members in the source and left `HubLayeringViolationKind.METHOD_HUB_IMPORT` in the test — 7 failures. Mechanical to fix, but worth recording: when an enum member is renamed, its *references* live wherever the enum is asserted on, and the plan's per-file checklists split that pair across two steps.

**Vocabulary, not just identifiers.** `LOW_LAYER_PACKAGES` → `RUNTIME_LAYER_PACKAGES` and `is_low_layer` → `is_runtime_layer` were in the plan; the prose was not, and it was the larger edit. "Low layer" / "high layer" was swept out of the guard, both hub docstrings, `class_registry_access.py`, the guard's success panel (it printed `Low layer: …` to the user), `hub-layering.md`, `architecture-overview.md` and the CHANGELOG. The historical checkpoint records in *this* file deliberately keep the old vocabulary, with a reading key in the header note — rewriting them would falsify what was decided when.

**Judgment calls made while sweeping the docs**, none of them mechanical:

- `hub-layering.md` gained an opening section naming the two layers as the language-implementation split, so a reader meets the vocabulary before the rule. The headline property was restated from "importing the inference layer must not load the interpreter" to **"importing the Pipelex runtime loads zero interpreter modules"** — the same measurement, phrased as the outward-facing claim.
- The `runtime_bridge` clarifier the plan asked for landed in two places, not one: `hub-layering.md`'s intro and the guard's module docstring, since `plugins → runtime_bridge` appears in that file's Known-inversions list.
- **D1 was preserved verbatim rather than swept.** Mechanically renaming it would have produced a decision record whose rejected alternatives argued about names that were no longer the subject. It is now marked SUPERSEDED, quotes the original in full, and notes that its own "conscious call against the brand-boundary rule" caveat is precisely what Louis acted on.
- `.drift/acks/keyword-only-convention.toml` was **left alone** — an ack is an on-the-record review decision, and rewriting the rationale of a past review to mention a module that did not exist at review time would be falsifying the record.

**One trigger file changed, so `keyword-only-convention` re-opened** — `keyword_only_guard.py`'s docstring names the hub. Reviewed and acked as import-path/prose-only; no guard behavior, registry schema, or carve-out changed.

**Cross-repo is retargeted, not extended.** The sweep tables in this file now name `pipelex.runtime_hub` / `pipelex.interpreter_hub` directly. External repos still import `pipelex.hub`, so they are rewritten exactly once — the intermediate names never reach them, and never shipped.

#### The plan's premise was wrong: `core/` is two layers

Phase 4 assumed all of `pipelex/core/` could join the low layer once five straddlers were converted. Measurement said otherwise, and the correction is the main finding of this checkpoint.

Beyond the five hub straddlers, **seven `core/` modules import the interpreter *directly*** — no hub involved, so no amount of dependency injection touches them:

| module | pulls | why it is irreducible |
| --- | --- | --- |
| `core/registry_models.py` | every pipe + factory | it *is* the registry of pipe kinds |
| `core/bundles/pipelex_bundle_blueprint.py` | 12 pipe blueprints | a discriminated union over every pipe kind |
| `core/interpreter/bundle_elaborator.py` | 4 pipe blueprints | it is the interpreter |
| `core/pipes/pipe_abstract.py` | `libraries.library_crate`, `pipe_signature.exceptions` | the base class every pipe extends |

Measured: `pipelex.core.pipes.pipe_abstract` alone loads **30** interpreter modules while importing no hub at all. So the honest boundary is not `pipelex.core` — it is **"if it names a `Pipe`, it is high."**

Louis' call (option A of three): declare core's data-model packages low, leave the Pipe-touching remainder high. Rejected: threading a provider through `PipeFactory.make_from_blueprint` too — that is **337 call sites (332 in tests, ~85 files)** and buys *no* additional closure property, since `pipe_factory` stays interpreter-bound either way.

#### What landed

**Two read-side contracts, new in `core/`:**

- `ConceptProviderAbstract` (`core/concepts/concept_provider_abstract.py`) — `get_required_concept`, `get_native_concept`, `get_required_concept_from_concept_ref_or_code`, `is_compatible`.
- `PipeProviderAbstract` (`core/pipes/pipe_provider_abstract.py`) — `get_required_pipe`.

`ConceptLibraryAbstract` / `PipeLibraryAbstract` now **extend** these, keeping add/remove/list/setup/teardown high. The split is the point: core depends on resolution, never on a library lifecycle. Both abstracts already named only `core` types, so this was an inverted dependency waiting to be undone.

**Injected, not looked up.** `StuffFactory.{make_stuff_from_stuff_content_or_data, make_from_blueprint, make_from_concept_ref}`, `InputShaper.{shape, resolve_input_kind}`, `WorkingMemoryFactory.make_from_pipeline_inputs`, `InputStuffSpecsFactory.{make_from_blueprint, make_from_string}`, `StuffSpecFactory.make_from_blueprint` all take a required `concept_provider`. Injection happens in the high half: `pipe_factory`, `input_renderer`, `output_renderer` call the hub themselves and hand the result down, as does `pipeline/execution_seams.py`.

**One import was simply wrong**: `stuff_factory.py` imported `ConceptLibraryConceptNotFoundError` from `libraries.concept.concept_library` — a re-export path. The class already lived in `core/concepts/exceptions.py`. A one-line fix deleted a whole interpreter edge.

**Two placement fixes** (the H-3 pattern again):

- `codegen/resolved_fields.py` → `core/concepts/resolved_fields.py`. It names nothing outside `pipelex.core`, yet put `pipelex.codegen` into the closure of every core module reaching structure generation.
- `core/pipes/inputs/input_renderer.py` + `core/pipes/output/output_renderer.py` → **`core/pipes/rendering/`**. Both render a `PipeAbstract`, so both are high; leaving `input_renderer` beside the low input-spec modules would have forced the low-layer declaration to enumerate *modules* instead of packages. `core/pipes/output/` is gone. Tests mirrored to `tests/unit/pipelex/core/pipes/rendering/`.

#### Measured after

| | baseline | H-1 | H-3 | **H-4** |
| --- | --- | --- | --- | --- |
| interpreter modules loaded by `cogt.content_generation.content_generator` | 50 | 0 | 0 | **0** ✅ |
| pipelex modules loaded | 357 | 275 | 268 | **268** |
| SLOC loaded | 29,193 | 21,186 | 20,304 | **20,304** |

The inference-layer numbers are unchanged by design — Phase 4 widened *which* modules are guaranteed clean, it did not touch `cogt`'s own weight. The new numbers are the six core entry points, each measured at **0 interpreter modules and no `pipelex.interpreter_hub`**, up from 50 each before this phase:

| entry point | interpreter modules before → after |
| --- | --- |
| `core.stuffs.stuff_factory` | 50 → **0** |
| `core.memory.input_shaper` | 50 → **0** |
| `core.memory.working_memory_factory` | 50 → **0** |
| `core.pipes.stuff_spec.stuff_spec_factory` | 50 → **0** |
| `core.pipes.inputs.input_stuff_specs_factory` | 50 → **0** |
| `core.concepts.structure_generation.generator` | 2 → **0** |

#### Housekeeping done at H-4

- **Grants**: 4 new (the provider-abstract getters), recorded **before** any check ran; 6 migrated with `resolved_fields`; 15 migrated with the two renderers; **4 deleted as dead** (`ConceptLibraryAbstract.get_{native_concept,required_concept,required_concept_from_concept_ref_or_code}`, `PipeLibraryAbstract.get_required_pipe`) — those defs moved to the provider abstracts, and staleness is symmetric so `make cko` hard-failed until the registry was cleaned.
- **Test call sites**: 74 across 12 files gained `concept_provider=get_concept_library()`, applied by an AST-driven fixer keyed off pyright's own `Argument missing` report so no unrelated `make_from_blueprint` was touched. ⚠ The first pass mangled 3 files: for a multi-line call the closing-paren line is whitespace-only, so a "does the preceding text end in a comma?" check must look back **across newlines**, not within the line. Reverted and redone.
- **Docs**: `docs/contribute/hub-layering.md` gained a "Where core splits" section (the two halves, the `if it names a Pipe, it is high` rule, and the injected-provider pattern), two new "Placement, not coupling" entries, a corrected low-layer list under Enforcement, and a rewritten `core/` bullet under Known inversions. `docs/under-the-hood/architecture-overview.md` gained a paragraph on core straddling the line. `docs/under-the-hood/codegen-projections.md` updated for the `resolved_fields` move.
- **CHANGELOG**: the breaking-change note that had been deferred since H-1 is now written under `[Unreleased]`, covering all four phases — the `pipelex.hub` split, the moved types, and the injected providers.

#### Still open

- **The cross-repo sweep is still untouched and release-gated.** It now has a **third** wave on top of the `pipelex.hub` split and the Phase 3 type moves — see [Cross-repo impact added by Phase 4](#cross-repo-impact-added-by-phase-4).
- ~~**The `hub-layering-convention` drift contract decision is still Louis'**~~ — **resolved: approved and landed** after the rename. See [Proposed, reverted, then landed](#proposed-reverted-then-landed).
- A plausible sequel, now much cheaper to argue for than at H-2: a general layering ratchet. The remaining measured inversions are in [Known inversions](#known-inversions-not-fixed-here).

#### Cross-repo impact added by Phase 4

| old | new |
| --- | --- |
| `pipelex.codegen.resolved_fields` | `pipelex.core.concepts.resolved_fields` |
| `pipelex.core.pipes.inputs.input_renderer` | `pipelex.core.pipes.rendering.input_renderer` |
| `pipelex.core.pipes.output.output_renderer` | `pipelex.core.pipes.rendering.output_renderer` |

Plus the signature changes: any external caller of `StuffFactory.make_stuff_from_stuff_content_or_data`, `WorkingMemoryFactory.make_from_pipeline_inputs`, `InputShaper.shape`, `InputStuffSpecsFactory.make_from_*` or `StuffSpecFactory.make_from_blueprint` must now pass `concept_provider=get_concept_library()`. Do all three waves in one pass per repo.

## Exit criteria — measured, not asserted

The headline property is that the inference layer must stop importing the interpreter. Measure it directly, from the repo root on a synced venv:

```bash
.venv/bin/python - <<'PY'
import sys
from pathlib import Path

import pipelex.cogt.content_generation.content_generator  # noqa: F401

INTERPRETER = {"libraries", "pipe_operators", "pipe_controllers", "codegen", "builder"}
loaded = {name: mod for name, mod in sys.modules.items() if name.startswith("pipelex.")}
interpreter = sorted(n for n in loaded if n.split(".")[1] in INTERPRETER)
sloc = 0
for mod in loaded.values():
    file = getattr(mod, "__file__", None)
    if file:
        sloc += sum(1 for line in Path(file).read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#"))
print(f"pipelex modules: {len(loaded)} | sloc: {sloc} | interpreter modules: {len(interpreter)}")
print("offenders:", interpreter)
PY
```

If Phase 1 lands and `interpreter modules` is not 0, the snippet prints the offenders: something imports the interpreter outside the hub, and the shortest import path to it is what to fix. Swap the imported module to measure any other entry point (`pipelex.pipelex`, `pipelex.runtime_hub`, …).

The module/SLOC targets come from importing exactly the types a low-only hub would annotate — 236 modules / 17,683 SLOC with the interpreter subpackages at zero — plus headroom for cogt's own modules.

## Findings in passing

> **Both are resolved as of H-1** — see [Findings in passing — both resolved, one bigger than recorded](#findings-in-passing--both-resolved-one-bigger-than-recorded). The `_observer` one turned out to be more than dead code: a public doc page documented the inert setter as the supported API.

Both surfaced while inventorying the boot sequence. Neither is caused by this refactor; both are in its blast radius, and the repo's flag-and-fix rule applies.

- **Duplicate `set_library_manager` in `Pipelex.setup`.** Lines 364–365 and 474–475 are the identical pair `self.library_manager = library_manager or LibraryManager()` + `self.pipelex_hub.set_library_manager(...)`. Nothing between them touches `library_manager` (verified), so when the caller passes no manager the first `LibraryManager()` is constructed, registered, and then silently discarded and replaced by a second instance. Delete the earlier pair — it is dead, and removing it is what makes the low/high boot split clean with no reordering (step 1.5).
- **`_observer` is write-only state.** `PipelexHub.set_observer` is called at `pipelex.py:503`, but there is no `get_observer` on the container and no module-level accessor — the live observer reaches its consumer directly via `PipeRouter(observer=multi_observer)` at line 531. The design doc lists "observer" among the `interpreter_hub` contents; it should be **deleted rather than moved**. Confirm no external consumer sets it before removing (see [Cross-repo sweep](#cross-repo-sweep)).

## Risks and containment

- **Big mechanical diff.** Contained by: the rewrite is scriptable from the partition table; `pipelex.hub` ceasing to exist means a missed site is an import error, not a silent wrong-layer resolution; and full `make agent-test` is the zero-behavior-change bar. The 29 multi-line import blocks are the one place a careless script does real damage — rewrite via `ast`, not regex.
- **Two singletons, two lifecycles, two teardowns.** Contained by the tiny construction surface. Watch `Pipelex.teardown` / `teardown_if_needed` and the fixtures that reset hub state — a half-reset hub between tests is the realistic failure mode, and it surfaces as cross-test pollution rather than a clean failure. Step 1.7 exists for this; make the "both hubs reset" assertion explicit rather than implied.
- **D5's resolver slot is installed at boot, not imported.** If a consumer builds a `RuntimeHub` without ever populating a `InterpreterHub` (the doctor path, some tests), `get_class_registry` must degrade to the unscoped `KajsonManager` registry rather than raise. Default the slot to a function returning `None`, never to an unset attribute.

## Cross-repo sweep

Release-gated follow-up — `pipelex.hub` is imported outside this repo and every one of these breaks the moment the module disappears.

| repo | files importing `pipelex.hub` |
| --- | --- |
| `pipelex-temporal/` (private) | 35 |
| `pipelex-mistralai-workflows/` | 11 |
| `pipelex-api/` | 9 |
| `pipelex-cookbook/` | 2 |
| `cocode/` | 2 |

Clean (no action): `pipelex-worker/`, `pipelex-starter-python/`, `pipelex-relay/`, `n8n-nodes-pipelex/`, `sandbox/`.

Symbols crossing the repo boundary today, which is the surface whose new home is a published contract change:

`clear_current_library`, `get_bundle_validator_registry`, `get_class_registry`, `get_console`, `get_content_generator`, `get_current_library`, `get_current_library_id_or_none`, `get_library_manager`, `get_model_deck`, `get_orchestrator_registry`, `get_pipe_func_executor_registry`, `get_pipe_library`, `get_pipe_router`, `get_pipelex_hub`, `get_report_delegate`, `get_required_concept`, `get_required_pipe`, `get_secret`, `get_storage_provider`, `get_storage_provider_registry`, `is_dry_run_forced`, `scoped_current_library`, `set_current_library`

Two notes on that list: `get_pipelex_hub` splits into two accessors, so every external site must pick a half; and `set_pipe_router` / `teardown_current_pipe_router` / `scoped_pipe_router` are documented as depended upon by our Mistral Workflows plugin, so their move is a contract change to announce, not just to make.

**Rewrite straight to the final names — there is no intermediate step.** `service_hub` / `method_hub` never shipped, so external repos go directly from `pipelex.hub` to:

| old | new |
| --- | --- |
| `from pipelex.hub import <runtime symbol>` | `from pipelex.runtime_hub import …` — everything in the [`runtime_hub` partition table](#-pipelexruntime_hubpy-runtime-layer) |
| `from pipelex.hub import <interpreter symbol>` | `from pipelex.interpreter_hub import …` — everything in the [`interpreter_hub` partition table](#-pipelexinterpreter_hubpy-interpreter-layer) |
| `get_pipelex_hub` | `get_runtime_hub` **or** `get_interpreter_hub` — pick the container the call site actually meant |
| `PipelexHub` | `RuntimeHub` **or** `InterpreterHub` |

**Phase 3 added a second wave of breakage to the same sweep** — the moved types, not the hub accessors. The per-repo counts and the complete old→new import table are in [Cross-repo impact added by Phase 3](#cross-repo-impact-added-by-phase-3). Do both waves in one pass per repo.

## Known inversions — not fixed here

Named so the docs stay honest, not scheduled.

- `plugins/pipe_func/pipe_func_plugin.py` and `plugins/pipe_func_executor_registry.py` import from `pipe_operators/`; `plugins/direct/direct_plugin.py` imports from `pipeline/`. None import the hub, so the guard will not flag them — but they mean "plugins is a low layer" is not yet unconditionally true. This is D3's underlying inversion.
- A general layering ratchet ("no low module may import any high module", with an allowlist) is out of scope. The measured inversion set is real but larger than this change should carry. **Re-measured at H-3**, after Phase 3 removed the two biggest clusters: `cogt → core` (21), `system → cogt` (7), `plugins → runtime_bridge` (6), `tools → cogt` (3 — the pdf renderer reaching for `cogt.extract` / `cogt.image` types, the same misfiling pattern Phase 3 fixed elsewhere), and one genuine wart — `cogt/model_backends/model_lists.py` importing `pipelex.cli.exceptions.PipelexCLIError`. `cogt → pipeline` (18) is gone. The general rule is now a more plausible sequel than it was at H-2.
- Eager optional-SDK imports: `pipelex/tracing/event_log_factory.py` imports `dynamodb_event_log` at module level, which runs a module-level `try: import boto3`, so `boto3`/`botocore`/`jmespath`/`dateutil`/`six` load in every process that touches the tracing factory. A three-line fix (import `DynamoDBEventLog` inside the factory branch, the pattern already used for `pypdfium2` in `cogt/content_generation/render_generate.py`), entirely independent of this plan. Most other heavy roots (`posthog`, `pypdfium2`, `pillow`, `polyfactory`, `datamodel-code-generator`) are **base** dependencies, not extras — not the same kind of finding.
