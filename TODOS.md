# Boot split — the composition root gets the same layer seam as everything else

**Execution target:** this worktree, branch `refactor/Boot`, already cut off `dev` at `96b992786`. This document is the working tracker: update the checkpoint sections as phases complete.

## Verdict (why this is worth doing)

Pipelex has two layers and one hub each, and the boundary is now enforced two ways — the `check-hub-layering` guard owns the rule, `tests/unit/pipelex/test_runtime_layer_import_closure.py` owns the property ("importing the Pipelex runtime loads zero interpreter modules"). Every package in the tree has been placed on one side of that line, and the last three tracks (the hub split, the plugin-manifest split, the layer-placement completion) each ended by declaring one more package and pinning it.

**One module never got the treatment: the composition root.** `pipelex/pipelex.py` is a single 780-line class that boots both layers in one interleaved sequence. It is interpreter-layer by construction, so it sits entirely *outside* the layer declaration — and an undeclared module is not neutral, it is unpoliced. Nothing enforces which half of that sequence belongs to which layer, and there is no way to boot the runtime layer at all: the only entry point in the tree constructs an `InterpreterHub`, a `LibraryManager`, a `PipelineManager`, a `PipeRouter` and a `PipeRun` whether the caller will ever load a method or not.

Three reasons this is the cheapest large win available:

1. **The property the two guards buy is currently unreachable from the only way in.** `check-hub-layering` proves no runtime-layer module imports `interpreter_hub`; the closure test proves ten runtime-layer entry points load zero interpreter modules. Both are true. But the entry point every embedder actually calls — `Pipelex.make()` — loads the interpreter unconditionally, so the property is real for *library imports* and vacuous for *booting*. Splitting the module makes "boot the runtime layer without the method interpreter" an entry point that exists, is measured, and is pinned by the same instrument as the other ten.
2. **The interleaving is undocumented and unenforced, so it will rot.** Today the interpreter constructions are sprinkled through `setup()` at four separate points (`pipelex.py:439-440`, `460-473`, `484-499`, `504`, `537-552`) with no marker saying so. The next person adding a boot step has nothing telling them which half it belongs in, and no check that catches a wrong answer. After the split, the wrong answer is an import in a declared runtime-layer module and the guard says so by name.
3. **Three of the four pieces are already built, by the tracks that came before.** This is a placement refactor with a measured before/after, an in-tree precedent, and no new indirection. See "What already exists" below — the enabling work is done and one of its outputs currently has no importer at all.

**Honest scoping.** This fixes no bug and unblocks no feature. The guard is green today and stays green: nothing runtime-layer imports `pipelex.pipelex`, so there is no violation to remove — what changes is that a capability becomes expressible and a boundary that was maintained by discipline becomes maintained by a test. The reviewer's fair question is "who calls the runtime-only boot?", and the honest answer is: the pinned closure entry point in this PR, the doctor path if Phase 4's measurement says it is a strict de-dup, and any embedder that wants inference + storage + models without the method machinery. That is the same shape as `RUNTIME_BUILTIN_PLUGINS`, which the plugin split created with zero importers and which is load-bearing here.

## Measured payoff (dev `96b992786`, this worktree)

| | modules | interpreter modules | SLOC (non-blank) |
|---|---|---|---|
| `import pipelex.pipelex` (today) | 619 | 172 | 59,752 |
| the runtime-only import set (projected) | 356 | **0** | 26,957 |

The projected row was measured by importing, in a fresh interpreter, exactly the top-level `pipelex` imports of `pipelex/pipelex.py` minus the interpreter-only ones, then counting `sys.modules`. **The zero is the headline and it is measured, not hoped:** the runtime half of the boot sequence reaches no interpreter module today, so the split needs no deferred imports, no function-local `# noqa: PLC0415`, and no new indirection — every import stays at module top level. Re-derive after the split with:

```bash
.venv/bin/python -c "import importlib, sys; importlib.import_module('pipelex.runtime_boot'); print(len([m for m in sys.modules if m.startswith('pipelex')]))"
```

The module and SLOC deltas are context for the PR body, not a gate. The zero is the gate, via the closure test.

## What already exists (why this is cheap)

1. **`build_registrar` takes the plugin manifests as parameters**, not module globals (`pipelex.py:301-305`, `plugins/discovery.py:25-30`) — and its docstring already says why: "some built-ins adapt interpreter-layer ports, and this module is runtime-layer".
2. **`pipelex/providers/builtins.py` already exports the runtime-only half** — `RUNTIME_BUILTIN_PLUGINS` and `RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES` — and `interpreter_plugins/builtins.py` composes both into the `BUILTIN_PLUGINS` boot uses. The runtime-only argument for step 1 exists and **has no importer in the tree**. This PR is its first caller.
3. **`class_registry_scoping` already degrades to the process-global registry when no `InterpreterHub` is installed** — documented in `docs/contribute/hub-layering.md` §"Library scoping crosses downward" as the intended behaviour for "a process that only ever builds a `RuntimeHub`".
4. **The pinning instrument exists**: `RUNTIME_LAYER_ENTRY_POINTS` in the closure test. Adding one string is how the new module gets policed, in the same subprocess-per-entry-point harness the other ten use.

And there is a worked precedent for the shape: the plugin manifests were split exactly this way — runtime half in a declared runtime-layer home, interpreter half in an interpreter-layer home that imports it downward and welds the two. `docs/contribute/hub-layering.md` §"Placement, not coupling" prescribes it, and the layer-placement track applied it three more times.

## Target end state

- `pipelex/runtime_boot.py` — a new top-level module holding `RuntimeBoot`: construct the `RuntimeHub`, config, logging, secrets, telemetry, the Kajson class registry + `CoreRegistryModels`, the template sets, `sdk_client_manager.setup()`, `models_manager.setup()`, the plugin-derived runtime registries, storage, the content generator, the inference manager, the reporting delegate, the observers, and the runtime slot claims. Top-level imports only. Declared in `RUNTIME_LAYER_PACKAGES` as a **module** entry, beside `pipelex.runtime_hub`, and listed in `RUNTIME_LAYER_ENTRY_POINTS`.
- `pipelex/pipelex.py` — unchanged address, unchanged public class name. `Pipelex` becomes the interpreter-layer boot: it imports `runtime_boot` downward, adds the `InterpreterHub`, the composed plugin manifests, the `PipeFuncExecutorRegistry` and executor, the `LibraryManager` and default library dirs, the `PipelineManager`, the `PipeRegistryModels` registration, the `PipeRouter` and the `PipeRun`.
- **Every `Pipelex` boot behaves identically to today**, verified by `make tb` and the full suite. This is a placement refactor; the only intended behaviour changes are the two named under "Deliberate behaviour changes" below, each with its own test.
- Booting `RuntimeBoot` loads zero interpreter modules and installs no `InterpreterHub` — pinned twice: by the closure test entry point, and by a lifecycle test beside the existing ones in `tests/unit/pipelex/test_hub_lifecycle.py`.
- `docs/contribute/hub-layering.md` gains the boot split beside the plugin split it mirrors, and the `hub-layering-convention` drift contract is acked (the guard file is one of its triggers).

## Composition shape (the load-bearing decision)

`Pipelex(RuntimeBoot, metaclass=MetaSingleton)` — inheritance, as a template-method boot. `RuntimeBoot` owns each lifecycle phase as its own method; `Pipelex` overrides `__init__` / `setup` / `teardown`, calls the runtime phase, and adds the interpreter constructions.

Why inheritance rather than composition (`Pipelex` holding a `self.runtime: RuntimeBoot`):

- **Every attribute address is preserved.** `self.models_manager`, `self.inference_manager`, `self.class_registry`, `self.telemetry_manager`, `self.kajson_manager`, `self._plugin_registrar` keep working from both halves, so no consumer inside or outside this repo changes. Composition renames all of them for no architectural gain.
- **The singleton stays keyed on `Pipelex`.** No change to `MetaSingleton.instances`, `is_fully_booted()`, or `ensure_pipelex_booted` in `runtime_bridge/bootstrap.py`.
- **It reads as what it is**: the interpreter boot *is* the runtime boot plus the interpreter constructions.

Three mechanical consequences, each with a decided answer:

- **Singleton identity.** `RuntimeBoot` carries `metaclass=MetaSingleton` too, and the class-level accessors (`get_optional_instance`, `is_fully_booted`, `get_instance`, `teardown_if_needed`) resolve **by subclass** via `MetaSingleton.get_subclass_instance(RuntimeBoot)` rather than by exact class. Without this, `RuntimeBoot.is_fully_booted()` answers `False` while a `Pipelex` owns the process-global runtime hub — a footgun for exactly the embedder this module is for. In-tree precedent: `TelemetryManagerAbstract` and `GraphTracerManager` both resolve their singleton this way. Consequence: `Pipelex.make()` now also refuses when a bare `RuntimeBoot` is booted, which is correct (`set_runtime_hub`, `KajsonManager` and `log.configure` are all once-per-process) and gets a test.
- **Teardown ordering is delicate and must be preserved exactly.** Today the plugin teardown callbacks run LIFO *before* `pipeline_manager.teardown()` (`pipelex.py:575-580`), deliberately, so a worker's in-flight resources release first. Express this as explicit protected phases on `RuntimeBoot` (`_teardown_plugin_callbacks()`, then the runtime teardown), which `Pipelex.teardown()` sequences with its own step in between. Explicit sequencing beats a base-calls-derived template hook for a lifecycle this order-sensitive.
- **`make()` duplication.** Both classes need a typed `make()` with their own parameter list; that is the price of two typed entry points. What must *not* be duplicated is the delete-on-failure release block (`pipelex.py:719-738`) — the subtle part, and the part with a comment explaining what leaks without it. Factor it into a `RuntimeBoot` classmethod that releases the process globals a partial boot acquired, and have both `make()` bodies call it.

## Measured inventory (dev `96b992786`)

**Interpreter-only, and therefore what stays in `pipelex/pipelex.py`:**

- `InterpreterHub()` + `set_interpreter_hub` (`__init__`, 130-131); the `library_manager` attribute declaration (159).
- The composed plugin manifests handed to `build_registrar` (303-304) — `Pipelex` passes `BUILTIN_PLUGINS` / `CORE_UNCONDITIONAL_PLUGIN_NAMES` where `RuntimeBoot` defaults to the `RUNTIME_*` pair.
- `PipeFuncExecutorRegistry` on the interpreter hub (439-440) and the `pipe_func_executor` resolution + set (460-473).
- `LibraryManager` + the default-library-dirs resolution (484-495).
- `PipelineManager` + `setup()` (497-499); `pipeline_manager.teardown()` in teardown (580).
- `PipeRegistryModels.get_all_models()` registration (504).
- `PipeRouter` (537-545) and `PipeRun` (547-552).

**Everything else moves to `RuntimeBoot`**, in today's order: the hub construct + config + logging (128-144), the registry/registrar/manager attribute declarations (147-157), `SdkClientManager` (153-154); then in `setup`: the boot-orchestrator config write (220-221), the gateway service / terms / remote-config block (223-288), `build_registrar` + the unknown-orchestrator gate (290-315), the secrets registry and provider (317-324), telemetry (326-341), the class + func registries and `KajsonManager` (345-350), the template sets (356-375), `sdk_client_manager.setup()` (379), the models manager and its error translation (381-420), the plugin-derived runtime registries (433-438), storage (441-447), forced dry-run (449), the content generator (450-458), the inference manager (475-476), the reporting delegate (480-482), the `CoreRegistryModels` and test-model registrations (503, 505-507), the observers (509-515), the task-manager slot (517-524) and the isolated-execution probe (526-535); plus `_resolve_hub_slot` (556-568), the context-manager methods (608-612), and the class-level accessors (746-779).

**Two seams the split creates** (both are why the interpreter tail can be a tail at all):

- `multi_observer` (511-515) is built from runtime-layer parts and consumed by `PipeRouter` (544). `RuntimeBoot` builds it and exposes it; the interpreter tail reads it.
- `_resolve_hub_slot` + `_plugin_registrar` live on `RuntimeBoot` and are used by the interpreter tail for the `PIPE_FUNC_EXECUTOR`, `PIPE_ROUTER` and `PIPE_RUN` slots.

**The interleaving looks incidental, not causal** — reading the sequence, nothing in the runtime half after line 440 consumes anything the interpreter half builds. That is the plan's central assumption and Phase 2 must *verify* it rather than assert it, per-site, with the full suite as the safety net.

**Pre-existing bugs to fix while there** (flag-and-fix rule):

- **`Pipelex(config_dir_path=…)` silently does nothing.** The parameter is stored at `pipelex.py:123` and never read again; `setup_config` is called without `config_dir` (135), even though the hub method accepts one (`runtime_hub.py:141`). Nothing in the workspace passes it. Fix by wiring it through as `config_dir` — which is exactly what makes the doctor path expressible (see Phase 4) — and drop the misleading name.
- **`make()`'s `pipeline_manager` is annotated with the concrete `PipelineManager`** (629) while `setup()`'s is the abstract `PipelineManagerAbstract` (209). Align on the abstract, as every other injected manager does.
- **`teardown()` reads `self.pipeline_manager` and `self.inference_manager` unguarded** (580, 585) although both are assigned in `setup()`, so teardown on a half-built instance raises `AttributeError`. This is *why* `make()` carries its own release path. Leave the semantics alone — do not add guards that would let a half-built teardown look successful — but note it in the release helper's docstring so the next reader finds the reason instead of the symptom.

**Deliberate behaviour changes** (each gets a test, each goes in the changelog):

- `Pipelex.make()` refuses to boot when a bare `RuntimeBoot` already holds the process globals (from the subclass-resolved singleton accessors).
- `config_dir` at boot actually reaches `setup_config`.

**Tests that touch this** (blast radius): `tests/unit/pipelex/test_hub_lifecycle.py` (boot installs both hubs; the real teardown releases scoping and a fresh boot re-installs it) is the file to extend; `tests/unit/pipelex/test_registry_models_split.py` pins that the core and pipe manifests are disjoint (relevant because the two registration calls end up in different halves); `tests/unit/pipelex/test_config_pre_boot.py`; the session conftest's boot fixture. Test files importing `from pipelex.pipelex import Pipelex` keep working unchanged — the address does not move.

---

## Phase 0 — red tests and the two verifications the plan rests on ✅

- [x] Venv synced; `make tb` (14 passed) and `make check-hub-layering` green before any edit.
- [x] **Verified: the runtime half needs no plugin the interpreter half contributes.** Read every construction in the old `pipelex.py:433–553`. Only **two** runtime-half sites resolve out of a plugin-derived registry, and both are runtime-contributed *and* core-unconditional: `secrets_provider_registry.get_required(...)` (old line 324) and `storage_provider_registry.get_required(...)` (446) — `StoragePlugin`/`SecretsPlugin` are in `RUNTIME_BUILTIN_PLUGINS`, and `storage`/`secrets`/`openai` are in `RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES`. `OrchestratorRegistry` and `BundleValidatorRegistry` are only *constructed and set* on the hub, never resolved at boot; the `TASK_MANAGER` / `ISOLATED_EXECUTION_PROBE` / `CONTENT_GENERATOR` slots are `slot_claims` lookups that no-op (or fall to a core default) when unclaimed. `build_registrar` uses `core_unconditional_plugin_names` **only** as a may-not-be-denylisted guard, so passing the `RUNTIME_*` pair requires nothing interpreter-side to be present. **No finding; Phase 1 unchanged.**
- [x] **Verified: the boot-orchestrator gate behaves.** `plugins.boot_orchestrator` defaults to `None` (`configs.py:250`, absent from every TOML), so the gate does not fire on a default runtime-only boot. When config *does* name an interpreter-contributed orchestrator, the existing check raises `UnknownBootOrchestratorError` unchanged — which is the decided behaviour (the requested runtime genuinely cannot be honoured by a process with no interpreter). **No code change needed**; the reason is now a comment at the gate.
- [x] **Red test — the runtime-only boot installs no interpreter hub.** Written, but in **new files** (`tests/unit/pipelex/test_runtime_boot_closure.py` and siblings) and as a **subprocess** test rather than in `test_hub_lifecycle.py` — see "Deviations" under Checkpoint 1–2 for why both changes were forced.
- [x] **Red test — the runtime-only boot loads zero interpreter modules.** `"pipelex.runtime_boot"` added to `RUNTIME_LAYER_ENTRY_POINTS`.
- [x] **Red test — a runtime boot and a full boot cannot coexist.** Plus the sibling that pins *why* it works: the subclass-resolved accessors see a `Pipelex` through `RuntimeBoot`.
- [x] **Red test — `config_dir` reaches the config loader.** A scoped load is package defaults + the given dir, so one overridden leaf (`log_config.default_log_level`) tells the two apart.

All four were confirmed **red on the missing module** before Phase 1 began.

## Phase 1 — extract `RuntimeBoot` ✅

- [x] `pipelex/runtime_boot.py` created with the runtime half per the inventory, code **moved** not rewritten: same order, same comments, same error translation. Module docstring states the layer contract and disambiguates the third `runtime_*` name.
- [x] Plugin manifests are parameters of `RuntimeBoot.setup()`, defaulting to `RUNTIME_BUILTIN_PLUGINS` / `RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES` — **their first importer**.
- [x] `config_dir` wired through `__init__` to `setup_config(config_dir=…)`; inert `config_dir_path` deleted.
- [x] `metaclass=MetaSingleton` + subclass-resolved accessors (`MetaSingleton.get_subclass_instance`); the failed-boot release block factored into `_release_after_failed_boot`, carrying its explanatory comment.
- [x] `teardown` split into `_teardown_plugin_callbacks()` + `_teardown_runtime()`.
- [x] `RuntimeBoot` holds no interpreter import — top-level imports only, no `TYPE_CHECKING` deferral of a runtime need, no function-local import. Enforced now by the guard declaration + closure entry point, not by discipline.
- [x] No new positional subjects, so no grants needed — `check-keyword-only` PASSED.

## Phase 2 — `Pipelex` becomes the interpreter boot ✅

- [x] `pipelex/pipelex.py` reduced to the interpreter half: `class Pipelex(RuntimeBoot)`, `__init__` → runtime `__init__` then `InterpreterHub`, `setup` → runtime `setup` with the composed manifests then the interpreter tail, `teardown` sequencing the three phases so the plugin callbacks still precede `pipeline_manager.teardown()`.
- [x] The interleaved interpreter blocks moved to the tail. **The interleaving was incidental, as the plan assumed** — confirmed per-site and then by the full suite. Two specific confirmations worth recording: `PipelineManager.setup()` is a literal `pass` and `LibraryManager.__init__` is pure dict initialisation, so neither depends on the class registry being populated — which is what makes it safe for them to move *after* the `CoreRegistryModels` registration they used to precede. The two `register_classes` calls now land in different halves and the ordering carries no meaning beyond disjointness (still pinned by `test_registry_models_split.py`).
- [x] `make()`'s public signature and docstring intact; the `PipelineManager` → `PipelineManagerAbstract` annotation mismatch fixed.
- [x] No import churn escaped. `from pipelex.pipelex import Pipelex` resolves unchanged; no positional `Pipelex(...)` construction exists anywhere in the tree, so making `__init__` keyword-only breaks nothing.

**CHECKPOINT 1–2 — DONE.** Combined deliberately: see Deviations below.

**Measured payoff — the projection was exact:**

| | modules | interpreter modules |
|---|---|---|
| `import pipelex.pipelex` | 619 | 172 |
| `import pipelex.runtime_boot` | **356** | **0** |

Gates at this checkpoint: `make agent-check` fully green (ruff, pyright 0 errors, mypy 2383 files clean, `check-keyword-only`, `check-hub-layering`), `make agent-test` **all passed**, `make tb` 15 passed.

**Deviations from the plan, and why:**

1. **Phases 1 and 2 were done as one commit rather than two.** The plan's Checkpoint 1 permits `Pipelex` to be "untouched and duplicating it", but an extraction done as a genuine *move* necessarily removes the code from `pipelex.py` in the same edit. Taking the permitted route instead would have meant committing ~350 duplicated lines and deleting them one commit later — churn a reviewer would rightly flag. Nothing was skipped; both phases' checklists are complete.
2. **The "no interpreter hub" test is a subprocess test in a new file, not an in-process test in `test_hub_lifecycle.py`.** Both hubs are sticky class-attribute singletons (`RuntimeHub._instance` / `InterpreterHub._instance`) that `teardown` deliberately never clears — so once anything in a process has booted a `Pipelex`, an in-process `InterpreterHub.get_optional_instance()` answers with the stale hub forever and the assertion would **pass vacuously**. A fresh interpreter is the only place the question is answerable. This turned out to be a strict upgrade: the subprocess test *boots* (`RuntimeBoot.make()`) rather than merely importing, which is exactly the "booted-runtime test" the plan's own risk section asks for — an import-time check cannot notice a boot step resolving out of an empty interpreter-contributed registry. It lives outside `test_hub_lifecycle.py` because that file's teardown-and-reboot test is documented as "runs last in this class", and a second such test would create a fragile two-must-run-last ordering. It is `tests/unit/pipelex/test_runtime_boot_closure.py`, one of three sibling modules — see the review triage below for why three.
3. **`_release_after_failed_boot` is an instance method, not a classmethod.** The block it factors reads `self.runtime_hub`, so a classmethod would have to take the instance as a parameter anyway.
4. **`class Pipelex(RuntimeBoot)` without a restated `metaclass=MetaSingleton`.** A metaclass is inherited; restating it is redundant.
5. **`@override` added to `setup` / `teardown` / `make`** — required by the repo's `reportImplicitOverride` once these became real overrides.
6. **The `make()` "already initialized" guard asks the *base* class**, not `cls`. Asking `cls` would let `Pipelex.make()` boot on top of a live bare `RuntimeBoot` (its `get_subclass_instance(Pipelex)` cannot see one) and quietly serve its half-populated class registry — which is the exact refusal the plan asked for.

**A third pre-existing bug found and fixed** (beyond the three the plan lists): `self.is_pipelex_service_enabled` was assigned `False` in `__init__` with the comment "Will be set during setup", but `setup()` only ever assigned a **local** variable of the same name — so the attribute was permanently a lie, and nothing in the tree or in any sibling repo ever read it. Deleted rather than wired, per smallest-correct-surface; a public attribute that always answers `False` is worse than no attribute.

**Test-side fallout, all mechanical:** six `mocker.patch` targets named `pipelex.pipelex.<symbol>` for symbols that now live in `runtime_boot` (`is_pipelex_gateway_enabled`, `load_pipelex_service_config_if_exists`, `RemoteConfigFetcher`, `build_registrar`). Repointed, and the four-file `PIPELEX_MODULE` constant renamed `RUNTIME_BOOT_MODULE` so the target stays legible. These string references are invisible to every import lint — the hazard the guard's own docstring calls out.

### Code-review triage (independent reviewer, no inherited context)

Four findings. Three accepted and fixed; one recorded as a verified-inert tradeoff, per the reviewer's own recommendation.

1. **Accepted — three `TestClass`es in one module.** `pipelex/kit/agent_rules/pytest_standards.md` says "NEVER EVER put more than one TestClass into a test module", twice, and the rule is not lint-gated so nothing caught it. Split into `test_runtime_boot_closure.py` (the subprocess property test), `test_runtime_boot_exclusivity.py` (the two boots exclude each other) and `test_runtime_boot_config_dir.py`. The 2-line `_test_integration_mode()` helper is duplicated across the two files that need it rather than hoisted into a shared module — that is exactly what `test_hub_lifecycle.py` already does with the same helper, so a new helper module would be the novel thing here, not the duplication.
2. **Accepted — `self.config_dir` was a fresh dead attribute.** Set in `__init__`, read nowhere (verified: every other `.config_dir` in the tree belongs to `doctor_cmd`'s unrelated `ConfigLocation`). Not a functional bug — the *local* parameter is what reaches `setup_config` — but it re-created the precise trap this PR removes twice over, and a reader who assumed the attribute was authoritative would have reintroduced it. Deleted, with a comment recording why the boot deliberately does not keep a copy.
3. **Accepted — the boot error messages hardcoded "Pipelex".** `RuntimeBoot.make()` said "Pipelex is already initialized" and `RuntimeBoot.get_instance()` said "Pipelex is not initialized", which is a lie for an embedder that never touched `Pipelex`. Both now name the class that actually holds the globals (`type(existing_boot).__name__`) or is actually being asked (`cls.__name__`). The reviewer's sharpest point was that *nothing caught it* — the test asserted only the exception type — so the exclusivity test now asserts the wording in both directions, and a second test pins the reverse case (`RuntimeBoot.make()` on top of a live `Pipelex`).
4. **Recorded, not fixed — `TestRegistryModels` now registers before `PipeRegistryModels`.** Old order was Core → Pipe → Test; it is now Core → Test (runtime half) → Pipe (interpreter tail). Verified inert: `kajson`'s `register_classes` is name-keyed dict insertion, `TestRegistryModels` holds only `FictionCharacter`, and `test_registry_models_split.py` already pins the manifests pairwise name-disjoint *order-independently*. It is also not fixable without making the layering wrong — `test_extras` is declared runtime-layer, so its registration belongs beside `CoreRegistryModels` in the runtime half; moving it to the interpreter tail to preserve a cosmetic order would misplace it. The reviewer explicitly did not ask for a fix. Noting it here so it is a known consequence rather than a rediscovered surprise.

## Phase 3 — declare it, pin it, document it

- [x] `"pipelex.runtime_boot"` added to `RUNTIME_LAYER_PACKAGES`, beside the `pipelex.runtime_hub` module entry, with the docstring note extended: why a *module* entry is right for both, and that `pipelex.pipelex` is deliberately undeclared.
- [x] Membership assertion added — `test_the_boot_split_left_the_runtime_half_declared`, in the shape of `test_the_plugin_split_left_both_halves_declared`. It asserts **both** directions: the runtime half must stay declared, and `pipelex.pipelex` must **not** be (declaring it would make the layer rule fail by design, and "the boot should surely be runtime-layer" is a plausible future edit).
- [x] `docs/contribute/hub-layering.md` updated: a new §"Where the boot splits" beside §"Where the built-in plugins split", and every stale mention corrected — the `Pipelex.setup`-installs-the-registries sentence (now split across the two halves), who passes the composed plugin lists, who calls `class_registry_scoping.reset()` (now the runtime teardown phase), the `RuntimeHub`-only process gaining a real entry point under §"Library scoping crosses downward", who imports `test_extras` at boot, and §"Enforcement" gaining the booted-runtime test with the reason a subprocess is required rather than preferred.
- [ ] `git add` the trigger files, then `make drift-plan` and `make drift-ack CONTRACT=hub-layering-convention RATIONALE="…"`. **Deliberately deferred to the final gate pass** so the ack digest is taken over the finished tree — the digest reads the git index, so acking mid-change would record a review of a state that no longer exists.
- [x] Changelog under `[Unreleased]`: added (`runtime_boot.py` with the measured before/after), changed (`Pipelex` is the interpreter boot; the two breaking details — keyword-only `config_dir` replacing the inert `config_dir_path`, and the dead `is_pipelex_service_enabled` removed; subclass-resolved accessors), fixed (`config_dir` reaching the loader; a second boot failing loud).

## Phase 4 — the first in-tree consumer (measured) — **assessed, NOT adopted** ✅

- [x] Assessed `setup_doctor_runtime`. Its needs are **not** a strict subset, and the plan's own stop condition is met on the nose.
- [x] **Verdict: leave doctor alone.** Three differences, and the first two are exactly the shape the plan said to stop on:
  1. **`log.configure_if_unset(...)` vs `RuntimeBoot.__init__`'s `log.configure(...)`.** Doctor *must* no-op when logging is already configured — its docstring says so, and `tests/unit/pipelex/tools/test_log_idempotence.py` exists to pin it. Closing this gap means a boolean flag parameter on the boot, which the plan names as the stop signal.
  2. **A `log_config_overrides` merge** (`deep_update` + `LogConfig.model_validate`) that the agent doctor uses to pin its log fields to stderr so the JSON envelope on stdout stays clean. That is a second parameter added for one caller.
  3. Doctor does **not** want an `SdkClientManager`, which `RuntimeBoot.__init__` constructs and sets on the hub. So adoption would also mean doctor acquiring something it deliberately avoids — doctor exists to *report on* models/plugins/inference without standing them up.

  Two flag parameters and an unwanted construction to de-duplicate roughly ten lines is a worse outcome than two short sequences that differ honestly. Recording the reason is the deliverable here, per the plan.

## Phase 5 — gates + PR

- [ ] `make agent-check` (grants recorded first), `make agent-test`, `make tb`, `make check-hub-layering`, `make drift-check`.
- [ ] Re-run the closure measurement and put the real before/after table in the PR body.
- [x] **Cross-repo sanity check — done by enumerating the workspace directory** (`ls -d */`, not a hardcoded list, so a repo in neither column cannot look checked-and-cleared). Result: **clean, verified not assumed.**
  - `pipelex-transport`'s `ALLOWED_SURFACE` (`conformance/tests/pipelex_transport/test_data.py:22`) names **no** boot/runtime module, so the transport boundary is untouched by this change.
  - Many sibling repos reference `pipelex.pipelex`, and every one of them is `from pipelex.pipelex import Pipelex` — the address does not move, so all keep working.
  - Zero references anywhere outside this repo to either removed surface (`config_dir_path`, `is_pipelex_service_enabled`), and zero `"pipelex.pipelex.<symbol>"` patch/attr targets outside this repo's own worktrees. The only `is_pipelex_service_enabled` hits in the workspace are in `docs/history/offline-mode/…`, an archive describing past state — correctly left alone.
  - The `_bg` / `_byok` / `_run` / `_run2` / `_workflows` hits are worktrees of this same repo and pick the change up on merge; `pipelex/` is the main checkout of it.
- [ ] PR to `dev`, argued on its own merits: the composition root gets the layer seam every other package already has, the runtime-only boot becomes an entry point that is measured and pinned, and the built-in-plugin split's runtime half gets its first caller.

## Non-goals (deliberate)

- **No new `boot/` package.** Two top-level modules, mirroring `runtime_hub.py` / `interpreter_hub.py` — the strongest naming precedent in the tree, and it needs no top-level-package accounting in the guard's docstring.
- **`Pipelex` does not move and is not renamed.** It is the public entry point every consumer and sibling repo imports. Moving it would be churn without architectural payoff, and the layer boundary does not require it.
- **No parameter-list refactor.** `setup()`/`make()` duplicate a long typed parameter list, and the split adds a second copy of the runtime subset. That is the cost of two typed entry points; a kwargs-forwarding fix would trade typing for brevity. Out of scope.
- **No behaviour change to a full `Pipelex` boot** beyond the two named above. Anything else that changes is a bug in the refactor.
- **No new abstraction over the two boots.** No protocol, no factory, no registry. The interpreter boot subclasses the runtime boot; that is the whole mechanism.

## Risks / watch items

- **The interleaving assumption.** Phase 2 rests on the interpreter constructions being deferrable to the tail. Reading says they are; the full suite is the proof. If a site turns out to be causal, the remedy is a named seam like `multi_observer` (the runtime half builds it, the tail consumes it), never a call back up into the interpreter layer from the runtime boot.
- **Empty registries on a runtime-only boot.** `OrchestratorRegistry`, `BundleValidatorRegistry` and the PipeFunc executor modes are all interpreter-contributed. Nothing runtime-layer should resolve out of them at boot — Phase 0 verifies it, and the closure test will not catch a *runtime* resolution failure, so this one needs reading plus a booted-runtime test.
- **The subclass-resolved singleton changes `make()`'s refusal semantics.** Intended and tested, but it is the change most likely to surface in an unexpected test — triage each surfacing as a finding, not a regression.
- **`pipelex.py` is central and several worktrees are in flight.** The edits are mostly moves, but land this in a quiet merge window: a rebase over a `setup()` change is a genuinely awkward conflict.
- **The auto-fixer keyword-onlys ungranted positional subjects silently** — record grants before running checks.
- **Comments must travel with their code.** Several inline comments in `setup()` are the only record of a non-obvious ordering constraint. A move that drops or strands one of them loses the reason and invites the next person to reorder it.
