# TODOS — split `pipelex.hub` into `service_hub` + `method_hub`

**Worktree:** `_hub/` · **Branch:** `refactor/Hub` (off `origin/dev`, base `f23fda7a0` = v0.40.0) · **Target:** normal PR back to `dev`.

**Status:** **CHECKPOINT H-2 reached** — branch `refactor/Hub`, not pushed.

Phases 0, 1 and 2 are complete: the split is landed, the headline property is measured at **0 interpreter modules**, and the boundary is now mechanically enforced by `make check-hub-layering` plus a subprocess import-closure test. **Phase 3 (the placement residue) is next** — and unlike Phases 1 and 2 it is genuinely optional: both of its items are types living in the wrong package, and "explicitly deferred with a recorded rationale" is a sanctioned outcome.

### Cold start — read in this order

1. [The one rule](#the-one-rule) and [Symbol partition](#symbol-partition) — the settled boundary.
2. [Checkpoint H-2 record](#checkpoint-h-2-record) — what the guard actually enforces (two rules, not one), its two carve-outs, and two CI wiring traps.
3. [Checkpoint H-1 record](#checkpoint-h-1-record) — the split itself, including the two places reality forced a change to the plan (the D5 slot could not live on `ServiceHub`; boot was deliberately not reordered).
4. [`docs/contribute/hub-layering.md`](docs/contribute/hub-layering.md) — the shipped specification of the boundary, now including the enforcement it describes.
5. Then start at [Phase 3](#phase-3--the-placement-residue).

Gates at H-2: `make agent-check` ✅ (pyright 0 errors, mypy 2,352 files, keyword-only PASSED, hub-layering PASSED) · `make agent-test` ✅ (full suite) · `make drift-check` ✅ (no contract opened — `cli-docs` excludes `pipelex/cli/dev_cli/**`).

Three notes for whoever picks this up:

- **`pipelex.hub` is already gone, but the CHANGELOG entry is not written** — the plan schedules it at H-4. If this branch merges earlier, write it first (see [Still open at H-1](#still-open-at-h-1)). The guard now enforces that the module stays gone, which makes the missing release note the only loose end on that front.
- **One decision is waiting on Louis**: whether to add a `hub-layering-convention` drift contract. It was built and reverted on purpose — see [Proposed, then reverted](#proposed-then-reverted-pending-louis-say-so).
- **Phase 4 widens the guard's low layer** to include `pipelex/core/**`. That is a one-line change to `LOW_LAYER_PACKAGES` in `hub_layering_guard.py`, and the guard will tell you immediately whether 4.1 is actually finished.

Design rationale, alternatives considered, and the full measured argument live in [`wip/hub-split-refactor.md`](wip/hub-split-refactor.md). This file is the executable tracker: what to do, in what order, with the concrete tables the work needs. Where the two disagree, this file wins — it carries the settled decisions and the re-measured numbers.

## The one rule

`method_hub` may import `service_hub`. **`service_hub` must never import `method_hub`.** That single arrow is the whole architecture, and it is what the Phase 2 guard checks.

> At H-1 only the forbidden direction is load-bearing; the permitted one turned out to be unused, because the one low-layer thing `method_hub` needs (the class-registry scoping slot) lives below *both* hubs. Importing either hub loads the other in neither direction — stronger than the rule requires. Phase 2's guard should still check the forbidden direction, not assert the permitted one exists.

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

**D1 — module names. SETTLED: `pipelex/service_hub.py` + `pipelex/method_hub.py`,** both flat at the package root, `pipelex/hub.py` deleted. Rejected: keeping `hub.py` for one half (a stale import would silently succeed); `library_hub` (the high half also holds the router, the runner, and the pipeline manager); a `pipelex/hubs/` package (`pipelex.hubs.services` reads worse than `pipelex.service_hub` at 300+ call sites). Noted for review: `method_hub` borrows the MTHDS noun for a runtime container — acceptable because the object genuinely holds the loaded method's libraries, but it is a conscious call against the brand-boundary rule.

**D2 — one container or two. SETTLED: two** — `ServiceHub` and `MethodHub`, each its own singleton, each with its own module-level accessors. One container would have to live in the low module, forcing every high-level slot to a quoted `TYPE_CHECKING` annotation — that keeps the god-object and adds a fig leaf. Two is affordable: the construction surface is five sites total.

**D3 — where `get_pipe_func_executor_registry` lands. SETTLED: high (`method_hub`).** It is a plugin registry by kind but its protocol lives in `pipe_operators/func/`. The underlying inversion — `pipelex/plugins/pipe_func_executor_registry.py` importing from `pipe_operators/` — is recorded as a follow-up (see [Known inversions](#known-inversions-not-fixed-here)), not fixed here.

**D4 — does `core/` join the low layer now? SETTLED: no, not in Phase 1.** Five `core/` modules use high-hub symbols; converting them means passing resolved concepts in rather than looking them up, which is design work, not mechanical. Phase 4 does it, and the guard's low-layer set widens only when that lands.

**D5 — `get_class_registry` is low but reads the library manager. SETTLED: callable resolver slot, defaulting to "no scoping", installed downward at boot.** Not in the design doc; surfaced while building the partition table. It is the decision that makes Phase 1.6 possible at all, so it is recorded here in full.

> **Amended at implementation (H-1): the slot does not live on `ServiceHub`.** It lives in a new leaf module, `pipelex/system/registries/class_registry_access.py`, reached through the `class_registry_scoping` module singleton. The mechanism, the default, and the downward-at-boot crossing are all exactly as designed below — only the physical home moved, and it was forced by a measured cycle rather than chosen. See [Checkpoint H-1 record → D5 amendment](#d5-amendment-the-resolver-slot-could-not-live-on-servicehub).

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

Resolution: `ServiceHub` grows a `Callable[[], ClassRegistryAbstract | None]` slot — default returns `None`, and boot installs the library-scoped resolver once `MethodHub` is populated. `get_class_registry` calls the slot and falls back to `KajsonManager.get_class_registry()`. The `_library_id` ContextVar stays in `method_hub` with the rest of its family; the resolver closure is what crosses, and it crosses downward at boot, not as an import.

This is not a new pattern — it is exactly how `_isolated_execution_probe` already works (`HubSlot.ISOLATED_EXECUTION_PROBE`, defaulting to `_never_in_isolated_execution`), so the precedent, the naming, and the plugin-claim machinery are all in place.

Alternative considered and rejected: move the whole `_library_id` contextvar family down into `service_hub`. Simpler (no indirection) but it splits the "current library" concept across both modules and makes `pipelex.service_hub` export `set_current_library`, which reads wrong. Also rejected: drop the scoping from `get_class_registry` and expose a separate high `get_scoped_class_registry` — that is a behavior change, and `tests/unit/pipelex/test_hub_class_registry.py` pins the current semantics.

`tests/unit/pipelex/test_hub_class_registry.py` is the regression guard for D5 — it must keep passing unmodified except for its import lines.

## Symbol partition

Complete and verified: an `ast` sweep of every `from pipelex.hub import …` across `pipelex/` and `tests/` classified every imported name against these two sets with nothing left over.

### → `pipelex/service_hub.py` (low)

| group | symbols |
| --- | --- |
| container | `ServiceHub`, `get_service_hub`, `set_service_hub` |
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

### → `pipelex/method_hub.py` (high)

| group | symbols |
| --- | --- |
| container | `MethodHub`, `get_method_hub`, `set_method_hub` |
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
| `tests/unit/pipelex/test_hub_class_registry.py` | `get_class_registry` | `clear_current_library`, `get_library_manager`, `set_current_library` |

Note the shape of the `pipe_operators/` rows: every one of them straddles for the same reason — `get_class_registry` / `get_content_generator` / `get_model_deck` (low) next to `get_concept_library` / `get_native_concept` (high). That is the D4 boundary showing through, and it is what Phase 4 dissolves.

## Phases

### Phase 0 — declare the boundary ✅

- [x] 0.1 Confirm **D5**. Settled as recorded above, and amended at implementation (the slot's home moved; the mechanism did not).
- [x] 0.2 Baseline re-taken on the branch tip and confirmed identical to the table above (357 / 29,193 / 50).
- [x] 0.3 Wrote [`docs/contribute/hub-layering.md`](docs/contribute/hub-layering.md) — the two hubs, the partition, how to place a new symbol, the class-registry exception, the measurement, enforcement, and the known inversions. Modelled on `keyword-only-arguments.md`. Its "Enforcement" section describes what is true at H-1 and is rewritten by Phase 2 when the guard lands.
- [x] 0.4 Updated `docs/under-the-hood/architecture-overview.md` with a "What Keeps The Layers Apart: The Two Hubs" section naming the boundary and the one-arrow rule, linking to the contributor doc. Added both pages to the `mkdocs.yml` nav.

### Phase 1 — the split ✅

- [x] 1.1 Created `pipelex/service_hub.py`. Module-level imports verified to name nothing from `libraries`, `pipe_operators`, `pipe_controllers`, `codegen`, `builder`, `core.bundles`, `core.concepts`, or `core.pipes`.
- [x] 1.2 Created `pipelex/method_hub.py`, importing `service_hub`'s layer for the D5 install. `set_method_hub` installs the resolver, so scoping is live exactly when a MethodHub exists and a caller cannot forget to wire it.
- [x] 1.3 Deleted `pipelex/hub.py`.
- [x] 1.4 Rewrote all 309 call sites via an `ast` pass over the whole import statement (the 29 parenthesized blocks came through intact). The 36 straddlers each gained a second import line, as predicted. **Two string-literal references the AST pass could not see broke the suite and had to be found by running it** — see the record below.
- [x] 1.5 Re-wired boot. Both hubs are constructed and installed at the top of `Pipelex.__init__`; every setter was retargeted to its own container. **The setter sequence was deliberately NOT reordered** — see the record below.
- [x] 1.6 Replaced all three `importlib.import_module("pipelex.hub")` hacks with plain top-level imports and deleted the `_get_class_registry` shims. The import target is the new leaf module, not `service_hub` — that is the D5 amendment.
- [x] 1.7 `Pipelex.teardown` and the `make()` failure path now release both hubs' process-global state. Pinned by `tests/unit/pipelex/test_hub_lifecycle.py`, which asserts a boot installs both singletons and that the reset really drops the scoping a MethodHub installed.

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

#### D5 amendment: the resolver slot could not live on `ServiceHub`

D5 assumed `core/concepts/` could reach `get_class_registry` from `pipelex.service_hub`. It cannot. `core.concepts.concept` is **inside `service_hub`'s own import closure**:

```
service_hub → cogt.llm.llm_worker_abstract → system.telemetry.otel_factory
            → core.pipes.pipe_output → core.stuffs.stuff → core.concepts.concept
```

so a module-level `from pipelex.service_hub import get_class_registry` in `concept.py` is a hard cycle — and it fails in *both* import orders, which is why it could not simply be ordered around. The design doc's claim that "a hub that does not import `Concept` has no cycle with `concept.py`" was half right: the cycle is not via `Concept`, it is via `cogt → system → core`.

Resolution, which preserves every property D5 was chosen for:

- `pipelex/system/registries/class_registry_access.py` — a new leaf module importing nothing from `pipelex`. Holds the real `get_class_registry` plus the `class_registry_scoping` slot (a module singleton in the `config_manager` style; the resolver default returns `None`, so a ServiceHub-only process degrades to the global registry rather than raising, exactly as [Risks](#risks-and-containment) requires).
- `pipelex.service_hub.get_class_registry` delegates to it and stays the **public** accessor — so the symbol partition table above is unchanged and the cross-repo contract is still "low symbols come from `service_hub`".
- The three `core/concepts/` modules import the leaf directly, because they are the one place the public accessor is unreachable.
- `method_hub.set_method_hub` installs the library-scoped resolver; `Pipelex.teardown` calls `class_registry_scoping.reset()`.

`tests/unit/pipelex/test_hub_class_registry.py` (the D5 regression guard) passes unmodified except for its import lines, as required.

#### Boot was not reordered — deliberately

Step 1.5 predicted the setter sequence would "split cleanly at line 475 with no reordering" once the duplicate pair was deleted. It does not, and cannot: **D3 puts the PipeFunc executor on the high hub**, so `set_pipe_func_executor_registry` and `set_pipe_func_executor` are MethodHub calls sitting in the middle of the ServiceHub run, and `set_isolated_execution_probe` is a ServiceHub call sitting after the MethodHub ones.

Reordering to force a clean split would have moved setters across documented ordering dependencies (the storage-provider block explicitly resolves *after* secrets is on the hub so the GCP factory's secret read works) — a real behavior risk at a checkpoint whose bar is zero behavior change. So: **both hubs are constructed and installed at the top of `__init__`, and the setter sequence is otherwise byte-identical in order.** That delivers what "populate ServiceHub fully before MethodHub" was actually protecting against — no setter can ever run against a missing hub — without touching execution order. Untangling the interleave belongs with D3's inversion, not here.

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

- **Subject grants migrated**: 54 `pipelex/hub.py::` entries → 55 under `pipelex/service_hub.py::` / `pipelex/method_hub.py::` (`set_instance` and `set_pipelex_hub` each split in two; `set_observer` dropped with the state). `make cko` is green, and staleness is symmetric so a missed entry would have failed.
- **Doc references swept**: `docs/under-the-hood/{pipe-routing-and-execution,runtime-bridge-and-transport,execution-graph-tracing}.md`, `docs/advanced/{index,observer-provider-injection}.md`, `tests/CLAUDE.md`, and in-code docstrings in `signature_walk.py` / the keyword-only guard modules. CHANGELOG history entries were left alone (they are release records). No live `pipelex.hub` reference remains anywhere in `pipelex/`, `tests/`, or `docs/`.

#### Still open at H-1

- **The CHANGELOG breaking-change note is not written yet** — it stays scheduled at H-4 per the plan, but `pipelex.hub` is *already* gone as of this checkpoint. If this branch is ever merged before H-4, write it first.
- The **cross-repo sweep** is untouched and still release-gated.
- One semantic edge worth knowing: `class_registry_scoping` is process-global, so the doctor path (which installs a fresh `ServiceHub` but leaves any existing `MethodHub` in place) now keeps library scoping alive where the single hub would have raised. Strictly more coherent — the MethodHub genuinely is still installed — and unreachable in practice, since doctor runs in its own process. Noted rather than fixed.

### Phase 2 — enforce it ✅

- [x] 2.1 Added `pipelex-dev check-hub-layering` — guard in `pipelex/cli/dev_cli/commands/hub_layering_guard.py` (stdlib-only AST core), command in `check_hub_layering_cmd.py` (rich presentation), following the `keyword_only_guard.py` / `check_keyword_only_cmd.py` split exactly. Catches imports **and** string literals, and resolves relative imports against the importing module's own package. **The guard grew a second rule beyond the plan** — see the record below.
- [x] 2.2 Low layer declared as `pipelex.cogt`, `pipelex.plugins`, `pipelex.reporting`, `pipelex.system`, `pipelex.tools`. All five compliant; the guard hard-blocks with an empty exception list (one escape-hatch marker exists, on the guard's own declaration of the forbidden path).
- [x] 2.3 Wired into `make agent-check`, the `make check` aggregate, and both CI lint workflows, with the `chl` alias.
- [x] 2.4 `tests/unit/pipelex/cli/dev/test_hub_layering_guard.py` — layer membership, both directions of the arrow, every import spelling (plain / aliased / `from pipelex import method_hub` / relative), both string forms, the prose-is-not-a-reference and `service_hub`-is-not-`hub` boundary cases, the `TYPE_CHECKING` carve-out and its three non-exempt neighbours, the escape hatch, and the dead-module rule across all three layers.
- [x] 2.5 `tests/unit/pipelex/test_hub_import_closure.py` — imports each low-layer entry point in a subprocess and asserts zero interpreter modules **and** no `pipelex.method_hub` in `sys.modules`. Parametrized over two entry points: the inference layer and `service_hub` itself.

**CHECKPOINT H-2** — boundary declared, enforced, and regression-tested.

### Checkpoint H-2 record

Gates: `make agent-check` ✅ (pyright 0 errors, mypy 2,352 files, keyword-only PASSED, hub-layering PASSED) · `make agent-test` ✅ (full suite) · `make drift-check` ✅ (no contract opened — see below).

#### The guard enforces two rules, not one

The plan specified one rule (no `method_hub` in the low layer). The guard ships with a second: **no module anywhere in `pipelex/` or `tests/` may reference `pipelex.hub`.** That is the H-1 note about `mocker.patch` targets, generalized — and generalizing it is what makes it work. The plan framed the string check as an `importlib.import_module` special case; scanning *every* string constant for an exact-or-boundary match on the module path catches `importlib`, `mocker.patch`, `pkgutil.resolve_name`, and any config-driven dotted path in one mechanism, with no call-site special-casing.

Scope follows from the two rules being different: `tests/` is scanned for the dead-module rule **only**. `tests.*` is in no declared layer, so a test may still freely patch `pipelex.method_hub` — while a stale `pipelex.hub` patch target, the thing that actually broke 36 tests, now fails the check.

Matching is exact-or-boundary (`==`, or a `.`/`:` suffix), which is why `pipelex.service_hub` does not match `pipelex.hub` and why a docstring that merely *mentions* a module is not a reference. Two in-tree docstrings do exactly that and are correctly ignored. A path assembled at runtime from f-strings is beyond any AST scan; nothing does that today, and it is noted in the module docstring rather than defended against.

#### Two carve-outs, both deliberate

- **`if TYPE_CHECKING:` is exempt from the layer rule, not from the dead-module rule.** The rule is about what *loads*; a type-only import loads nothing, and H-1's own out-of-plan fix used exactly this deferral. Its `else` branch, `if not TYPE_CHECKING:`, and any `pipelex.hub` import inside a `TYPE_CHECKING` block all stay violations — each is pinned by a test.
- **`# hub-layering: ignore`** mirrors `# kw-only: ignore`. There is exactly one in `pipelex/` and one in the test suite, both on lines that *declare* the forbidden path as data. The guard flagged its own configuration on first run, which is a good sign about the matcher and the reason the hatch exists.

#### Verified by breaking it, not only by unit tests

Both forms were injected into a real low-layer module (`cogt/content_generation/content_generator.py`) and the CLI was confirmed to report them at the right lines with the right kinds, then the file was restored byte-identically. Snippet-level unit tests would not have caught a filesystem-walk or layer-membership mistake.

#### Two wiring traps worth knowing

- **The CI aggregator gates on an explicit bash result check, not on `needs`.** Adding `lint-hub-layering` to `lint-all`'s `needs` list is *not* enough — `if: always()` means the aggregator runs regardless, and the `[ "${{ needs.<job>.result }}" != "success" ]` chain is what actually fails the build. Both were updated. A new lint job added without touching that chain would be silently advisory.
- **A new job, not a step on `lint-keyword-only`.** Folding both AST guards into one job would have meant renaming it, and that job name may be a required status check — a rename silently un-requires it. The repo already runs one job per guard; this follows that.

#### Proposed, then reverted, pending Louis' say-so

A `hub-layering-convention` drift contract (triggers: the guard + both hub modules; review: `docs/contribute/hub-layering.md`) is the exact analogue of the existing `keyword-only-convention` contract, and it would mechanize the doc obligation Phase 4 already carries. It was added, confirmed to open correctly, then **reverted**: `.claude/skills/drift-review` states that during the pilot the manifest must not grow without the user's explicit say-so, because ack friction is the thing being measured. Left as a decision for Louis rather than a silent addition. Note that `cli-docs` legitimately did not fire on this work — it excludes `pipelex/cli/dev_cli/**`.

#### Docs updated

- `docs/contribute/hub-layering.md` — the "Enforcement" section was rewritten from "a guard is the next step" to the shipped two-rule specification: what each rule checks, why the string half is the load-bearing one, both carve-outs, the `tests/` scoping, and the rule-vs-property split.
- `docs/under-the-hood/architecture-overview.md` — one sentence stating the boundary is mechanically enforced rather than held up by review.

### Phase 3 — the placement residue

Neither item is coupling; both are types living in the wrong package, and each is independently correct.

- [ ] 3.1 **`JobMetadata`.** Lives in `pipelex/pipeline/job_metadata.py` but is an argument to essentially every cogt call — it accounts for 17 of the 18 `cogt → pipeline` import statements, and drags `graph.trace_context` → `graph.graph_config` into every closure that touches inference. Move it, and decide whether `trace_context` moves with it or stops depending on `graph_config`. Also move `JobMetadataError` out of `pipeline/exceptions.py` — the sole remaining `cogt → pipeline` edge, in `llm_worker_abstract.py`.
- [ ] 3.2 **`cogt.templating.*`.** `TemplateCategory`, `TemplatingStyle`, `TextFormat`, and `TagStyle` are imported by eight `tools/jinja2/` and `tools/mermaid/` modules — templating primitives sitting under `cogt/`, making `tools` (the intended bottom layer) depend on `cogt`. Decide: move them down to `tools`, or accept `cogt` as below `tools` and document that.

**CHECKPOINT H-3** — placement residue resolved, or explicitly deferred with a recorded rationale.

### Phase 4 — `core/` joins the low layer

- [ ] 4.1 Convert the five `core/` straddlers — `stuffs/stuff_factory.py`, `memory/input_shaper`, `pipes/stuff_spec/stuff_spec_factory`, `pipes/inputs/input_stuff_specs_factory`, `pipes/output/output_renderer` — to take resolved concepts/pipes as arguments instead of reaching for `get_concept_library` / `get_native_concept` / `get_required_concept` / `get_required_pipe`. Callers that have a library pass the resolved value; callers that do not are, by construction, already in the high layer.
- [ ] 4.2 Widen the guard's low layer: add `pipelex.core` to `LOW_LAYER_PACKAGES` in `pipelex/cli/dev_cli/commands/hub_layering_guard.py`, and add `pipelex.core.*` entry points to `LOW_LAYER_ENTRY_POINTS` in `tests/unit/pipelex/test_hub_import_closure.py`.

**CHECKPOINT H-4 = done** — update `docs/contribute/hub-layering.md` with the final layer set, and add the CHANGELOG breaking-change note under `[Unreleased]` (`pipelex.hub` is gone; importers choose `pipelex.service_hub` or `pipelex.method_hub`).

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

If Phase 1 lands and `interpreter modules` is not 0, the snippet prints the offenders: something imports the interpreter outside the hub, and the shortest import path to it is what to fix. Swap the imported module to measure any other entry point (`pipelex.pipelex`, `pipelex.service_hub`, …).

The module/SLOC targets come from importing exactly the types a low-only hub would annotate — 236 modules / 17,683 SLOC with the interpreter subpackages at zero — plus headroom for cogt's own modules.

## Findings in passing

> **Both are resolved as of H-1** — see [Findings in passing — both resolved, one bigger than recorded](#findings-in-passing--both-resolved-one-bigger-than-recorded). The `_observer` one turned out to be more than dead code: a public doc page documented the inert setter as the supported API.

Both surfaced while inventorying the boot sequence. Neither is caused by this refactor; both are in its blast radius, and the repo's flag-and-fix rule applies.

- **Duplicate `set_library_manager` in `Pipelex.setup`.** Lines 364–365 and 474–475 are the identical pair `self.library_manager = library_manager or LibraryManager()` + `self.pipelex_hub.set_library_manager(...)`. Nothing between them touches `library_manager` (verified), so when the caller passes no manager the first `LibraryManager()` is constructed, registered, and then silently discarded and replaced by a second instance. Delete the earlier pair — it is dead, and removing it is what makes the low/high boot split clean with no reordering (step 1.5).
- **`_observer` is write-only state.** `PipelexHub.set_observer` is called at `pipelex.py:503`, but there is no `get_observer` on the container and no module-level accessor — the live observer reaches its consumer directly via `PipeRouter(observer=multi_observer)` at line 531. The design doc lists "observer" among the `method_hub` contents; it should be **deleted rather than moved**. Confirm no external consumer sets it before removing (see [Cross-repo sweep](#cross-repo-sweep)).

## Risks and containment

- **Big mechanical diff.** Contained by: the rewrite is scriptable from the partition table; `pipelex.hub` ceasing to exist means a missed site is an import error, not a silent wrong-layer resolution; and full `make agent-test` is the zero-behavior-change bar. The 29 multi-line import blocks are the one place a careless script does real damage — rewrite via `ast`, not regex.
- **Two singletons, two lifecycles, two teardowns.** Contained by the tiny construction surface. Watch `Pipelex.teardown` / `teardown_if_needed` and the fixtures that reset hub state — a half-reset hub between tests is the realistic failure mode, and it surfaces as cross-test pollution rather than a clean failure. Step 1.7 exists for this; make the "both hubs reset" assertion explicit rather than implied.
- **D5's resolver slot is installed at boot, not imported.** If a consumer builds a `ServiceHub` without ever populating a `MethodHub` (the doctor path, some tests), `get_class_registry` must degrade to the unscoped `KajsonManager` registry rather than raise. Default the slot to a function returning `None`, never to an unset attribute.

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

## Known inversions — not fixed here

Named so the docs stay honest, not scheduled.

- `plugins/pipe_func/pipe_func_plugin.py` and `plugins/pipe_func_executor_registry.py` import from `pipe_operators/`; `plugins/direct/direct_plugin.py` imports from `pipeline/`. None import the hub, so the guard will not flag them — but they mean "plugins is a low layer" is not yet unconditionally true. This is D3's underlying inversion.
- A general layering ratchet ("no low module may import any high module", with an allowlist) is out of scope. The measured inversion set is real but larger than this change should carry: `tools → cogt` (15 statements), `cogt → core` (21), `system → cogt` (8), `plugins → runtime_bridge` (6), and one genuine wart — `cogt/model_backends/model_lists.py` importing `pipelex.cli.exceptions.PipelexCLIError`. Phase 3 removes the two biggest clusters; the general rule is a sequel worth considering once they are gone.
- Eager optional-SDK imports: `pipelex/tracing/event_log_factory.py` imports `dynamodb_event_log` at module level, which runs a module-level `try: import boto3`, so `boto3`/`botocore`/`jmespath`/`dateutil`/`six` load in every process that touches the tracing factory. A three-line fix (import `DynamoDBEventLog` inside the factory branch, the pattern already used for `pypdfium2` in `cogt/content_generation/render_generate.py`), entirely independent of this plan. Most other heavy roots (`posthog`, `pypdfium2`, `pillow`, `polyfactory`, `datamodel-code-generator`) are **base** dependencies, not extras — not the same kind of finding.
