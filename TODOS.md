# Boot split — the composition root gets the same layer seam as everything else

**Status: complete.** Branch `refactor/Boot`, cut off `dev` at `96b992786`. This document describes the change for review: what it does, why, what was decided and why, and where a reviewer should push hardest.

## ⏸ RESUME HERE — session paused 2026-07-30

**Everything is committed and pushed. Nothing is in flight locally.** `git status` is clean; branch `refactor/Boot` == `origin/refactor/Boot` at `e0ebf6b42`.

**PR:** https://github.com/Pipelex/pipelex/pull/1073 → `dev`. Eight commits.

**State at pause:**

- Local gates green on the pushed tree: `make agent-check`, full `make agent-test`, `make drift-check`.
- Last full CI round (on `f7186e7`'s predecessor) was **23 pass / 0 fail**, Greptile **5/5 "safe to merge"**, 0 unresolved threads.
- Two more commits landed after that round (`f7186e736`, `e0ebf6b42`) with both review threads replied to and resolved. **CI and the bots have NOT yet run on `e0ebf6b42`.**

### ⚠ Procedural gaps to close on resume — read this before continuing

The work landed, but the **prescribed procedure was not followed in two places.** The resuming session must close these; they are not optional and not already done.

1. **Bot-feedback triage was never fanned out.** The instruction was: when CI and the review bots report, fan out an **Opus sub-agent** to check their feedback, deduplicate, verify each item, and arbitrate — solving only clear wins, guarding no impossible scenarios. Instead all seven rounds of bot feedback were triaged inline, directly. **On resume: for the next round, spawn an Opus sub-agent for the triage** rather than reading the threads yourself. Give it the PR number, the unresolved-thread list, the repo conventions, the strict no-over-engineering bar, and the instruction to defer doubts as `.md` in `wip/inputs/`.
2. **The final gstack `/review @TODOS.md` pass is still owed.** One was run, but *mid-stream* — before the bots were quiet — and its five findings then triggered three further bot rounds. The instruction is to run it **after** the bots are all happy, as the finalizing step. **On resume: once CI is green and Greptile/Codex are quiet on the head commit, fan out a sub-agent to run gstack `/review @TODOS.md`, apply its findings under the same bar, and only then finalize the PR.**

A third, lesser deviation, already documented below and defensible but worth knowing: the plan's CHECKPOINT 1 and CHECKPOINT 2 were merged into one commit, so the Sonnet-5 `/code-review` fan-out happened **once** rather than per checkpoint. That one fan-out did run correctly — fresh agent, no inherited context, pointed only at the staged diff — and Phases 3–5 were additionally covered by the gstack pass.

**The immediate open action:** wait for CI + Greptile + Codex on `e0ebf6b42` / `a4362a13e`, then triage **via the Opus sub-agent per gap 1 above**. A re-trigger comment (`@greptileai please re-review.` / `@codex review`) has been posted.

**How the review loop has been run** (worth continuing, because it kept finding real things — six of the seven rounds produced at least one genuine defect):

1. Read every unresolved thread; **verify the claim against the source before acting** — several bot findings were right about the mechanism but wrong about severity, and two were right about a mechanism I had reasoned about incorrectly.
2. Fix only clear wins. Defer genuine design tradeoffs as `.md` in `wip/inputs/` with an analysis and a suggested shape.
3. For every behavioural fix, **write the negative control**: revert the fix and confirm the new test fails. This caught a vacuous test and confirmed four real ones.
4. Reply on the thread with the reasoning (including where my own earlier reasoning was wrong), resolve it, re-run gates, commit, push, ping both bots.

**Two recurring mistakes of mine, if more findings arrive** — both cost a round each:

- **Cost misjudgement drove two wrong deferrals.** The telemetry singleton I deferred as "needs its own test matrix" was one guarded call; the `config_dir` propagation I estimated as four lines turned out to need a public abstract interface widened. *Write the patch to price it*, then decide.
- **Reasoning from a concrete class's guarantees about a call through an injectable abstract type.** Bit twice on the same method (rounds 6 and 7). Anything typed `…Abstract` that a caller can inject must be treated as unbounded.

**Three deferrals are recorded** in `wip/inputs/`: `runtime-boot-external-interpreter-orchestrator.md`, `config-dir-does-not-scope-inference-paths.md`, `failed-boot-does-not-release-every-resource.md`. Each has the analysis and a suggested remedy.

**One required cross-repo follow-up** (separate repos, out of scope for this PR): `pipelex-temporal/tests/conftest.py:86` and `pipelex-transport/tests/conftest.py:89` patch `"pipelex.pipelex.load_pipelex_service_config_if_exists"` in autouse session fixtures; that symbol is now in `pipelex.runtime_boot`, so both suites break at session start once they pick this up. ⚠ Use `git -C <repo> grep` for any cross-repo sweep here — the environment's `grep` is a **shell function** that does not traverse sibling repos and silently returns zero.

**When the bots are finally quiet:** the remaining planned step is the gstack `/review` pass, which was already run once (its five findings are all applied — see the triage sections below).

---

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

**The zero is the gate**, via a new closure entry point. The module and SLOC deltas are context, not gates. Reproduce — note the trailing dot in `'pipelex.'`, which is the convention the closure test uses; dropping it also counts the bare `pipelex` package and gives 357/620:

```bash
.venv/bin/python -c "import importlib, sys; importlib.import_module('pipelex.runtime_boot'); print(len([m for m in sys.modules if m.startswith('pipelex.')]))"
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
- **Breaking:** `teardown()` no longer propagates a plugin teardown callback's exception. The callbacks are attempted individually and failures are logged, so one bad plugin cannot strand another's resources.

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
- **Cross-repo**, redone with `git -C <repo> grep` over repos enumerated from disk. `pipelex-transport`'s `ALLOWED_SURFACE` names no boot/runtime module, and zero references anywhere outside this repo touch either removed surface (`config_dir_path`, `is_pipelex_service_enabled`). Most downstream references are `from pipelex.pipelex import Pipelex` or `pipelex.pipelex.Pipelex.make(...)` — the *class*, which does not move — and keep working.

  ⚠️ **Two real downstream breaks, which the first sweep missed.** `pipelex-temporal/tests/conftest.py:86` and `pipelex-transport/tests/conftest.py:89` each `session_mocker.patch("pipelex.pipelex.load_pipelex_service_config_if_exists", …)` in an **autouse session fixture**. That symbol now lives in `pipelex.runtime_boot`, so both suites `AttributeError` at session start — total suite failure, not a subtle one. Both pin `pipelex>=0.40.0` as a floor with no `tool.uv.sources` override, so it arrives at the next routine lockfile refresh rather than only at a deliberate bump. **Required cross-repo follow-up** (separate repos, so out of scope for this PR): repoint both strings to `pipelex.runtime_boot.load_pipelex_service_config_if_exists`.

  **Why the first sweep missed them — the methodology matters more than the result.** `grep` in this environment resolves to a **shell function**, not `/usr/bin/grep`, and it does not traverse sibling repos: a recursive `grep -r` from the workspace root returned zero and read as a clean bill of health. That is the same failure shape as a hardcoded repo list — a repo the instrument never reached is indistinguishable from one that came back clean. `git -C <repo> grep` per enumerated repo is both correct and fast, and is the instrument to use for any future cross-repo sweep here.

**Test-side fallout was mechanical:** six `mocker.patch` targets named `pipelex.pipelex.<symbol>` for symbols that now live in `runtime_boot`, repointed, with the shared four-file constant renamed `RUNTIME_BOOT_MODULE`. Those string references are invisible to every import lint — the hazard the guard's own docstring calls out.

## Review already applied

An independent reviewer with no context on the plan raised four findings against the staged diff. Three were accepted and fixed:

1. **Three `TestClass`es in one module** — violates `pytest_standards.md` ("NEVER EVER put more than one TestClass into a test module"), which is not lint-gated. Split into `test_runtime_boot_closure.py`, `test_runtime_boot_exclusivity.py`, `test_runtime_boot_config_dir.py`. The 2-line `_test_integration_mode()` helper is duplicated across the two files needing it rather than hoisted — that is what `test_hub_lifecycle.py` already does with the same helper, so a shared helper module would be the novel thing, not the duplication.
2. **A fresh dead attribute `self.config_dir`** — set in `__init__`, read nowhere. Not a functional bug (the local parameter is what reaches `setup_config`), but it re-created the exact trap this PR removes twice over. Deleted, with a comment recording why the boot deliberately keeps no copy.
3. **Hardcoded "Pipelex" in `RuntimeBoot`'s error messages** — a lie for an embedder that never touched `Pipelex`. Both messages now name the real class. The sharpest part of the finding was that *nothing caught it*, since the test asserted only the exception type; the exclusivity test now asserts the wording, and a second test pins the reverse direction.

The fourth was the registration-order consequence above — verified inert, not fixable without misplacing `test_extras`, and explicitly not a requested fix. Recorded so it is known rather than rediscovered.

Codex then raised a fifth on the PR, **verified correct and deliberately deferred**: a runtime-only boot rejects an interpreter-layer orchestrator contributed by a *built-in* (it is never registered, since `builtin_plugins` defaults to the runtime half) but **not** one contributed by an *external* entry-point plugin, because `build_registrar` discovers externals unconditionally. Such a boot would apply the plugin's runtime claims — including `TASK_MANAGER` — never apply its `PIPE_ROUTER` / `PIPE_RUN` / `PIPE_FUNC_EXECUTOR` claims, and still report ready.

Not fixed here for three reasons: it needs an external interpreter-side orchestrator installed *and* configured *and* a caller of `RuntimeBoot.make()`, of which there are none; every remedy needs a layer signal the runtime layer deliberately does not have (a `PipelexPlugin` carries no layer field, by design); and the nearest clean remedy is a flag on the very class pair that exists to avoid flags — which would contradict the doctor-adoption decision taken twenty lines away in the same file. The gate's comment now states the hole precisely instead of overclaiming (it previously said the runtime-only boot "also rejects an interpreter-contributed orchestrator name, which is correct" — true for built-ins, false for externals, so the comment was the actual defect). Full analysis and two candidate remedies: [`wip/inputs/runtime-boot-external-interpreter-orchestrator.md`](wip/inputs/runtime-boot-external-interpreter-orchestrator.md).

### Round 7 — the same mistake twice, named

Codex found a third defect on the failed-boot path, and it is worth recording because it is the **same reasoning error** as the round-6 one, one line away.

My telemetry release call sat as the first statement in the `finally`, justified by a comment citing the built-in `TelemetryManager`'s "telemetry teardown must never break the app" property. But `self.telemetry_manager` is whatever the *factory* produced, and `telemetry_manager` is a public `make()` injection point typed only as `TelemetryManagerAbstract` — so an injected implementation carries no such guarantee. Unisolated, a raising one skips every release below it and replaces the boot error going out.

**The generalisable mistake: reasoning from a concrete class's guarantees about a call made through an injectable abstract type.** Round 6 was the granularity version of it (catching around a loop over unbounded callbacks); this is the identity version. Both are now isolated per-call, and the comments say why rather than asserting safety.

Pinned by `test_an_injected_telemetry_manager_that_raises_does_not_abort_the_other_releases`. Two things about its construction are deliberate: it patches `TelemetryFactory.make_telemetry_manager` rather than passing `telemetry_manager=`, because the injection is only adopted in some telemetry/integration modes and the subject is the resulting *state*; and it proves the suite completed by asserting the **singleton de-registration**, which is the suite's last statement, rather than by re-booting — which also keeps the patched factory from leaking into a second boot. Verified as a real control: reverting the isolation fails it.

### Round 6 — Greptile back to 5/5; Codex found the granularity bug in my round-4 fix

Codex's last finding is a consequence of the fix I made two rounds earlier, and it is a good one: my `except Exception` sat around the **loop** rather than inside it, so the first raising callback (LIFO, i.e. the last registered) ended the loop and every remaining callback was skipped. With two plugins registered — Temporal plus a sandbox executor is the realistic pair — the second one's runtime stayed live while the log said only that one callback had failed.

"Catch around the loop" and "catch per iteration" look equivalent and are not, which is exactly why this needed a test rather than a re-read. Fixed by moving the catch inside the loop; the outer one became dead and was removed, though the `try`/`finally` stays, because `except Exception` does not cover `BaseException` and the state releases must still run if a teardown is interrupted.

Pinned by `test_one_raising_teardown_callback_does_not_skip_the_others`, which registers the raiser **last** so LIFO reaches it first — the ordering that strands the others. Verified as a real control: restoring the around-the-loop catch fails it with "a raising callback skipped the remaining teardown callbacks".

**Third deliberate behaviour change, now declared:** `teardown()` no longer propagates a plugin callback's exception. That follows from making the loop best-effort, and it is the right semantics — no caller can act on "plugin B failed to release", while every caller is harmed by B never being asked. Same shape as `TelemetryManager.teardown`, which wraps each of its own shutdown steps for the same reason.

### Round 5 — Greptile blocked on the deferred telemetry leak, and it was right to

Greptile dropped from 5/5 to **3/5** and said the PR should not merge until the failed-boot cleanup clears the telemetry singleton — the item the pre-landing review had raised and I had deferred. Two independent reviewers on the same defect, one of them blocking, so I re-examined the deferral and **it was wrong on cost**.

`TelemetryManager.teardown()` already ends with `TelemetryManagerAbstract.clear_instance()`, and its internals are each wrapped defensively with the comment "telemetry teardown must never break the app". So the fix is **one guarded call** on a path that already guards the same attribute — not the "change to failure-path semantics with its own test matrix" I had described. I had conflated the narrow fix (release the singleton) with the broad one (collapse the two teardown paths), and deferred both on the strength of the broad one's cost.

Fixed, and pinned by `tests/unit/pipelex/test_runtime_boot_failed_boot_release.py`: an injected models manager whose `setup()` raises reproduces the real shape (telemetry is already live by then), and the test asserts no telemetry singleton survives. Verified as a real control — with the release reverted it fails on exactly that assertion.

What remains deferred is genuinely narrower and of a different kind: `sdk_client_manager`, `reporting_delegate` and `func_registry` are still not released on a failed boot. Those leave resources dangling rather than corrupting the next boot, and adding three more calls would widen a second hand-maintained copy of the teardown list. The right fix is to collapse the two paths, which is a lifecycle decision — [`wip/inputs/failed-boot-does-not-release-every-resource.md`](wip/inputs/failed-boot-does-not-release-every-resource.md).

### Codex round 4 — two more, one fixed and one deferred after being attempted

1. **Fixed: the `try`/`finally` still let a teardown error replace the boot error.** The `finally` guaranteed the releases, but a raising plugin callback propagated out of `_release_after_failed_boot()`, so `make()`'s bare `raise` was never reached and the caller saw the *teardown* failure instead of the one that killed the boot. This refines a judgement I had made and stated on the previous round — I declined to catch, reasoning that "the five existing operations have the same property, so it's all six or none." That reasoning was wrong on its own terms: only the plugin callbacks are **unbounded third-party code**, everything in the `finally` is ours, so catching exactly one of the six is principled rather than inconsistent — and it is case (2) of this repo's own `except Exception` carve-out (a user-registered callback whose exception surface cannot be enumerated), which requires a naming comment and gets one.
2. **Deferred after being attempted: `config_dir` scopes the main TOML load but not the inference file paths.** Real: `models_manager.setup()` is called without path arguments, so backends, routing profiles and the model deck still resolve through the layered `config_manager.*` properties — an alternate `config_dir` combines its own main settings with whatever tree is detected. `ModelManager.setup`'s comment already names the remedy, and doctor's `--global` path implements it.

   The four-line propagation was written and tested, then **backed out**: those path overrides exist on the concrete `ModelManager`, not on `ModelManagerAbstract`, which is what the boot is typed against *and* a documented `make()` injection point. Pyright rejects the call, and this repo forbids the `cast`/`isinstance` shortcut — the honest fix is to widen the abstract interface, which is a change to a public injection contract and does not belong in a placement refactor claiming unchanged behaviour. Two things learned while attempting it and worth carrying: completing the scoping makes an explicit `config_dir` **require a complete config directory** (verified — a dir holding only `pipelex.toml` then fails with `InferenceBackendLibraryNotFoundError`), which is the correct contract but a deliberate behavioural decision; and doctor spells the four paths as inline literals while `config_loader` already owns them as constants, so a second copy would double a drift risk that should be collapsed instead.

   What shipped instead: both `make()` docstrings now state the limit explicitly rather than promising "only this directory is read", the boot carries a `NOTE:` at the call site, and the analysis plus a four-step suggested shape is in [`wip/inputs/config-dir-does-not-scope-inference-paths.md`](wip/inputs/config-dir-does-not-scope-inference-paths.md) — including that the negative test for it was written on this branch and verified to fail on a reverted propagation, so it can be lifted from history.

### Pre-landing review triage (second independent reviewer)

A pre-landing review then found five more, **four of them in the two commits that fixed the earlier findings** — a reminder that a fix commit deserves the same scrutiny as the change it fixes. All five accepted:

1. **`_release_after_failed_boot` ran unbounded plugin code before the un-poisoning, with no `try`/`finally`.** Introduced by the leak fix itself. If a plugin teardown callback raised, the state releases below it never ran — logging stayed configured (every later boot dies on "LogConfig is already set"), `KajsonManager` kept a half-populated registry, the singleton stayed registered — *and* the teardown error replaced the exception that actually killed the boot. The method's entire purpose is to leave the process re-bootable. Now `try: callbacks / finally: releases`, which is the shape `AGENTS.md` prescribes for required cleanup — and the same rule Codex had cited when reporting the leak.
2. **The exclusivity guard and the release resolved at different classes.** `make()` asked the base (so it saw any boot) but `teardown_if_needed()` asked `cls`, so `Pipelex.teardown_if_needed()` silently no-opped against a live bare `RuntimeBoot` while `Pipelex.make()` kept refusing — a deadlock with no recovery path, reachable from every existing `teardown_if_needed()` call site. Both now resolve at the base: a release must be able to clear everything its matching guard refuses on.
3. **`__init__` took `RuntimeHub._instance` before any exclusivity check.** `set_runtime_hub` overwrites unconditionally, so constructing a second boot directly clobbered a live boot's hub and only then failed at `log.configure`, orphaning it. `MetaSingleton` used to make this unreachable *by accident* — a second `Pipelex(...)` short-circuits on the registry and never re-runs `__init__` — but a subclass is a different registry key, so the accident stopped covering it. The exclusivity check moved into `__init__`, which holds on every path including direct construction; both `make()` guards were deleted as redundant rather than duplicated.
4. **The `config_dir` test bypassed `make()`.** Construct-then-`setup()` re-implements what `make()` wraps, and `teardown()` on a half-built instance raises `AttributeError` — masking the real error and leaving the singleton registered for the rest of the xdist worker. Now goes through `RuntimeBoot.make(config_dir=…)`, which already accepts it.
5. **The booted-runtime test had lost its negative control.** Its sweep lives in a `textwrap.dedent` string, so nothing type-checks the predicate; the sibling import-closure module carries a `DIRTY_ENTRY_POINT` for exactly this reason and the copy dropped it. Verified rather than assumed: changing the sweep's `split(".")[1]` to `[0]` made the module green forever. A control case now treats `cogt` — which the runtime boot loads by definition — as an interpreter package and requires a failure. Re-verified: with the predicate broken, the real case passes and **the control fails**.

A sixth was **pre-existing and deferred**: a failed boot leaves the `TelemetryManager` singleton live, so the next boot in the process adopts the dead one (reachable via `ensure_pipelex_booted`'s per-call lazy boot, since the commonest boot failure — `models_manager.setup()` on a missing deck or credentials — fires *after* telemetry setup). Unchanged from `dev`, and widening the release path is a change to failure-path semantics with its own test matrix, not a comment fix — so it is written up in [`wip/inputs/failed-boot-leaks-telemetry-singleton.md`](wip/inputs/failed-boot-leaks-telemetry-singleton.md) with a suggested shape. What *was* fixed is the docstring, which claimed this path "releases the same process-global state `teardown()` does": it releases a subset, and the "only safe entry points" rationale never explained the omission, since `reporting_delegate` and `telemetry_manager` are already guarded.

Codex raised a **sixth** on the re-review, and this one was accepted and fixed: **a failed boot leaked a plugin runtime.** `_release_after_failed_boot()` released process-global state but never ran the plugin teardown callbacks, so a boot dying after the `TASK_MANAGER` thunk left a live runtime running. Verified that the boot split genuinely widened the window — pre-split the thunk ran at `pipelex.py:524`, *after* the pipe-func executor resolution (471), `pipeline_manager.setup()` (499) and the pipe-class registration (504); all three now follow it. The most reachable trigger is a plain config error (`pipe_func_config.execution_mode` naming an unregistered mode). Fixed by running `_teardown_plugin_callbacks()` first on that path, mirroring the normal teardown ordering. Pinned by `test_a_failed_interpreter_tail_still_runs_plugin_teardown_callbacks`, which asserts the thunk ran *and* the callback ran so it cannot pass vacuously — and which was confirmed to fail with the fix removed.
