# Boot split — the composition root gets the same layer seam as everything else

**Status: complete.** Branch `refactor/Boot`, cut off `dev` at `96b992786`. This document describes the change for review: what it does, why, what was decided and why, and where a reviewer should push hardest.

## What this branch does

`pipelex/pipelex.py` is split into two composition roots:

- **`pipelex/runtime_boot.py`** (new) — `RuntimeBoot`: config, logging, the secrets provider, telemetry, the Kajson class registry + `CoreRegistryModels`, the template sets, `sdk_client_manager`, the model deck, the plugin-derived runtime registries, storage, the content generator, the inference manager, the reporting delegate, the observers, and the runtime slot claims. **Loads zero interpreter modules.**
- **`pipelex/pipelex.py`** — `Pipelex`, unchanged address and unchanged public surface, now `class Pipelex(RuntimeBoot)`. It adds the `InterpreterHub`, the composed plugin manifests, the `PipeFuncExecutorRegistry` and its executor, the `LibraryManager` and default library dirs, the `PipelineManager`, the `PipeRegistryModels` registration, the `PipeRouter` and the `PipeRun`.

## Why

Pipelex has two layers and one hub each, enforced two ways: `check-hub-layering` owns the rule (no runtime-layer module imports `interpreter_hub`) and `test_runtime_layer_import_closure.py` owns the property it buys (importing the Pipelex runtime loads zero interpreter modules). Every package in the tree had been placed on one side of that line and pinned there.

**The composition root never got the treatment.** It boots both layers in one interleaved sequence, so it is interpreter-layer by construction and sat entirely *outside* the declaration — and an undeclared module is not neutral, it is unpoliced. Two consequences:

1. **The property was real for importing and vacuous for booting.** The entry point every embedder actually calls — `Pipelex.make()` — loaded the interpreter unconditionally. There was no way to boot the runtime layer at all.
2. **The interleaving was undocumented and unenforced, so it would rot.** The interpreter constructions were sprinkled through `setup()` at four separate points with no marker saying so. Nothing told the next person which half a new boot step belonged in, and nothing caught a wrong answer. Now the wrong answer is an import in a declared runtime-layer module, and the guard names it.

The shape has a worked in-tree precedent: the built-in plugin manifests were split exactly this way (runtime half in a declared runtime-layer home, interpreter half importing it downward and welding the two), which `docs/contribute/hub-layering.md` §"Placement, not coupling" prescribes and the layer-placement track applied three more times.

## Measured payoff

| | modules | interpreter modules | SLOC (non-blank) |
|---|---|---|---|
| `import pipelex.pipelex` | 619 | 172 | 60,026 |
| `import pipelex.runtime_boot` | **356** | **0** | 27,630 |

**The zero is the gate**, via a new closure entry point. The module and SLOC deltas are context, not gates. Reproduce:

```bash
.venv/bin/python -c "import importlib, sys; importlib.import_module('pipelex.runtime_boot'); print(len([m for m in sys.modules if m.startswith('pipelex')]))"
```

The projection made before any code was written was 356 / 0. It matched exactly, because the runtime half of the boot sequence already reached no interpreter module — so the split needed **no** deferred imports, no function-local `# noqa: PLC0415`, and no new indirection. Every import stays at module top level.

## The load-bearing decisions

**Inheritance, not composition.** `Pipelex` subclasses `RuntimeBoot` rather than holding one.

- Every attribute address is preserved — `self.models_manager`, `self.class_registry`, `self.telemetry_manager`, `self.kajson_manager`, `self._plugin_registrar` all read the same from both halves — so no consumer inside or outside this repo changes. Composition would rename all of them for no architectural gain.
- It reads as what it is: the interpreter boot *is* the runtime boot plus the interpreter constructions.

**The singleton resolves by subclass.** `RuntimeBoot` carries `MetaSingleton` too, and the class-level accessors go through `MetaSingleton.get_subclass_instance` (in-tree precedent: `TelemetryManagerAbstract`, `GraphTracerManager`). Each `make()` asks the **base** class whether a boot exists — not `cls`. That is what makes the two mutually exclusive in *both* directions: asking `cls` would let `Pipelex.make()` boot on top of a live bare `RuntimeBoot`, because `get_subclass_instance(Pipelex)` cannot see one, and it would then quietly serve that boot's half-populated class registry. `set_runtime_hub`, `KajsonManager` and `log.configure` are all once-per-process.

**Teardown ordering is explicit, not a template hook.** The plugin-contributed callbacks must run LIFO *before* `pipeline_manager.teardown()`, so a worker's in-flight resources release first. `RuntimeBoot` exposes `_teardown_plugin_callbacks()` and `_teardown_runtime()` as separate phases; `Pipelex.teardown` sequences them with its own step between. For a lifecycle this order-sensitive, explicit sequencing beats a base-calls-derived hook.

**The failed-boot release path is shared, not duplicated.** Both `make()`s call `_release_after_failed_boot()`. That block is the subtle part — a partial boot must release process globals it acquired or the next boot raises "LogConfig is already set" and serves a stale registry — and it deliberately touches only entry points safe on a half-built instance. Its docstring records *why* it cannot just call `teardown()`: `teardown` reads `self.inference_manager` (and `self.pipeline_manager`) unguarded, and both are assigned partway through `setup()`. That is intentional — guarding them would let a half-built teardown look successful.

## Deliberate behaviour changes

Each has a test; each is in the changelog.

- **A second boot on top of an existing one fails loud.** `Pipelex.make()` refuses when a bare `RuntimeBoot` holds the process globals, and vice versa. The error message names the class that actually holds them, not a hardcoded "Pipelex".
- **`config_dir` at boot reaches `setup_config`.**
- **Breaking:** `Pipelex.__init__` takes keyword-only `config_dir` in place of the inert positional `config_dir_path`. Nothing in the workspace constructed `Pipelex` positionally.

## Pre-existing bugs fixed (flag-and-fix)

- **`config_dir` was silently ignored.** Stored at `pipelex.py:123` as `config_dir_path` and never read again; `setup_config` was called without a `config_dir` even though `runtime_hub.setup_config` accepts one. An embedder passing an explicit config dir got ordinary project/global layering and no error.
- **`is_pipelex_service_enabled` was permanently a lie.** Assigned `False` in `__init__` with the comment "Will be set during setup", but `setup()` only ever assigned a **local** of the same name. Nothing in the tree or any sibling repo read it. Deleted rather than wired — a public attribute that always answers `False` is worse than no attribute.
- **`make()`'s `pipeline_manager` was annotated with the concrete `PipelineManager`** while `setup()`'s was `PipelineManagerAbstract`. Aligned on the abstract, as every other injected manager is.

Also noted and deliberately left alone: `teardown()` reads `self.pipeline_manager` and `self.inference_manager` unguarded, so teardown on a half-built instance raises `AttributeError`. That is *why* `make()` carries its own release path; guards there would let a half-built teardown look successful. The reason is now recorded in the release helper's docstring so the next reader finds the reason rather than the symptom.

## How it is pinned

- **Declared:** `pipelex.runtime_boot` in `RUNTIME_LAYER_PACKAGES`, a **module** entry beside `pipelex.runtime_hub`. Declaring it is the entire reason the rule reaches it.
- **Membership asserted both ways:** `test_the_boot_split_left_the_runtime_half_declared` requires the runtime half to stay declared *and* `pipelex.pipelex` to stay undeclared. Deletion is the silent regression — the neighbouring checks all *iterate* the tuple and say nothing about a name that is simply gone. And declaring `pipelex.pipelex` would make the layer rule fail by design, so "surely the boot should be runtime-layer" is a plausible future edit worth catching.
- **Import closure:** `"pipelex.runtime_boot"` added to `RUNTIME_LAYER_ENTRY_POINTS`.
- **Boot closure:** `tests/unit/pipelex/test_runtime_boot_closure.py` *runs* `RuntimeBoot.make()` in a subprocess and asserts zero interpreter modules loaded, no `InterpreterHub` installed, and `class_registry_scoping` left at its unscoped default.

  **The subprocess is required, not preferred.** Both hubs are sticky class-attribute singletons (`RuntimeHub._instance` / `InterpreterHub._instance`) that teardown deliberately never clears, so once anything in a process has booted a `Pipelex`, an in-process `InterpreterHub.get_optional_instance()` answers with the stale hub forever and the assertion **passes vacuously**. And *booting* rather than importing is what catches a boot step resolving out of an interpreter-contributed registry — see the next section.

## The one thing worth reviewing hardest

**Empty registries on a runtime-only boot.** A runtime-only `build_registrar` sees `RUNTIME_BUILTIN_PLUGINS` alone, so the `direct` orchestrator, the direct bundle validator and the built-in PipeFunc executor modes are all absent: `OrchestratorRegistry` and `BundleValidatorRegistry` are constructed **empty**. That is harmless only because nothing in the runtime half *resolves* out of them at boot. Verified per-site rather than assumed:

- The only two runtime-half sites that resolve out of a plugin-derived registry are secrets (`secrets_provider_registry.get_required`) and storage (`storage_provider_registry.get_required`). Both are runtime-contributed *and* core-unconditional — `StoragePlugin`/`SecretsPlugin` are in `RUNTIME_BUILTIN_PLUGINS`, and `storage`/`secrets`/`openai` are in `RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES`.
- `OrchestratorRegistry` / `BundleValidatorRegistry` are only constructed and set on the hub, never resolved at boot; they are looked up at run time by the interpreter.
- The `TASK_MANAGER`, `ISOLATED_EXECUTION_PROBE` and `CONTENT_GENERATOR` slots are `slot_claims` lookups that no-op or fall to a core default when unclaimed.
- `build_registrar` uses `core_unconditional_plugin_names` **only** as a may-not-be-denylisted guard, so passing the `RUNTIME_*` pair requires nothing interpreter-side to be present.

The closure test cannot catch a *runtime resolution* failure, which is exactly why the booted-runtime test boots instead of importing.

**Boot-orchestrator gate on a runtime-only boot.** `plugins.boot_orchestrator` defaults to `None` (`configs.py:250`, absent from every TOML), so the gate does not fire on a default runtime-only boot. When config *does* name an interpreter-contributed orchestrator, the existing check raises `UnknownBootOrchestratorError` unchanged — the decided behaviour, since a process with no interpreter genuinely cannot honour that runtime. No code change; the reason is a comment at the gate.

**The interleaving assumption.** The whole plan rested on the interpreter constructions being deferrable to the tail. They were, confirmed per-site and then by the full suite. Two specific confirmations: `PipelineManager.setup()` is a literal `pass`, and `LibraryManager.__init__` is pure dict initialisation — so neither depends on the class registry being populated, which is what makes it safe for them to move *after* the `CoreRegistryModels` registration they used to precede. The two values that cross the seam go the other way (`self._plugin_registrar` and `self.multi_observer`, built by the runtime half and read by the tail).

**A registration-order consequence, verified inert.** Old order was Core → Pipe → Test; it is now Core → Test (runtime half) → Pipe (interpreter tail). `kajson`'s `register_classes` is name-keyed dict insertion, `TestRegistryModels` holds only `FictionCharacter`, and `test_registry_models_split.py` already pins the manifests pairwise name-disjoint *order-independently*. It is also not fixable without making the layering wrong: `test_extras` is declared runtime-layer, so its registration belongs beside `CoreRegistryModels`.

## Deliberate non-goals

- **No `boot/` package.** Two top-level modules mirroring `runtime_hub.py` / `interpreter_hub.py` — the tree's strongest naming precedent for a layered pair, and it needs no top-level-package accounting in the guard's docstring.
- **`Pipelex` does not move and is not renamed.** It is the public entry point every consumer and sibling repo imports; the boundary never required moving it.
- **No parameter-list refactor.** `setup()`/`make()` duplicate a long typed parameter list and the split adds a second copy of the runtime subset. That is the cost of two typed entry points; a kwargs-forwarding fix would trade typing for brevity.
- **No new abstraction over the two boots.** No protocol, no factory, no registry. The interpreter boot subclasses the runtime boot; that is the whole mechanism.
- **Doctor was assessed and deliberately not adopted.** `setup_doctor_runtime` is the tree's only other bare-`RuntimeHub` builder, but its needs are **not** a strict subset: it requires `log.configure_if_unset` rather than `configure` (pinned by `tests/unit/pipelex/tools/test_log_idempotence.py`), a `log_config_overrides` deep-merge the agent doctor uses to keep its JSON envelope clean, and specifically *not* an `SdkClientManager` — doctor exists to report on models/plugins/inference without standing them up. Two flag parameters and an unwanted construction to de-duplicate ~10 lines is a worse outcome than two short sequences that differ honestly.

## Honest scoping

This fixes no bug in the layering and unblocks no feature. The guard was green before and stays green — nothing runtime-layer imports `pipelex.pipelex`, so there was no violation to remove. What changes is that a capability becomes expressible and a boundary maintained by discipline becomes maintained by a test.

The fair reviewer question is "who calls the runtime-only boot?" The honest answer: the pinned closure and booted-runtime entry points in this PR, and any embedder wanting inference + storage + models without the method machinery. That is the same shape as `RUNTIME_BUILTIN_PLUGINS`, which the plugin split created with zero importers — and which is load-bearing here, as its first caller.

## Verification performed

- `make agent-check` — ruff, `generate-mthds-schema`, plxt, pyright (0 errors), mypy (2385 files), `check-keyword-only`, `check-hub-layering`. All green.
- `make agent-test` — full suite passes. This is the proof the interleaving was incidental.
- `make tb` — green.
- `make drift-check` — green; `hub-layering-convention` reviewed and acked, with a dogfood-log entry. The contract's prescribed mechanical check **caught a real gap**: `pipelex.runtime_boot` was missing from the doc's enumeration of the declared runtime layer. Fixed. Seven consecutive rounds where an enumeration on that page was the rot, and three in a row where it was that same enumeration — the log now names automating it as the clearest candidate the pilot has produced.
- **Cross-repo**, done by *enumerating* the workspace directory rather than a hardcoded list (a repo in neither column would otherwise look checked-and-cleared): `pipelex-transport`'s `ALLOWED_SURFACE` names no boot/runtime module; every sibling reference is `from pipelex.pipelex import Pipelex`, whose address does not move; zero references anywhere to either removed surface; zero `"pipelex.pipelex.<symbol>"` patch targets outside this repo's own worktrees.

**Test-side fallout was mechanical:** six `mocker.patch` targets named `pipelex.pipelex.<symbol>` for symbols that now live in `runtime_boot`, repointed, with the shared four-file constant renamed `RUNTIME_BOOT_MODULE`. Those string references are invisible to every import lint — the hazard the guard's own docstring calls out.

## Review already applied

An independent reviewer with no context on the plan raised four findings against the staged diff. Three were accepted and fixed:

1. **Three `TestClass`es in one module** — violates `pytest_standards.md` ("NEVER EVER put more than one TestClass into a test module"), which is not lint-gated. Split into `test_runtime_boot_closure.py`, `test_runtime_boot_exclusivity.py`, `test_runtime_boot_config_dir.py`. The 2-line `_test_integration_mode()` helper is duplicated across the two files needing it rather than hoisted — that is what `test_hub_lifecycle.py` already does with the same helper, so a shared helper module would be the novel thing, not the duplication.
2. **A fresh dead attribute `self.config_dir`** — set in `__init__`, read nowhere. Not a functional bug (the local parameter is what reaches `setup_config`), but it re-created the exact trap this PR removes twice over. Deleted, with a comment recording why the boot deliberately keeps no copy.
3. **Hardcoded "Pipelex" in `RuntimeBoot`'s error messages** — a lie for an embedder that never touched `Pipelex`. Both messages now name the real class. The sharpest part of the finding was that *nothing caught it*, since the test asserted only the exception type; the exclusivity test now asserts the wording, and a second test pins the reverse direction.

The fourth was the registration-order consequence above — verified inert, not fixable without misplacing `test_extras`, and explicitly not a requested fix. Recorded so it is known rather than rediscovered.
