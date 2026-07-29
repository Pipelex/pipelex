# PR #1062 — `/review` follow-ups

**Status: [Phase A](#phase-a--in-pr-fixes), [Phase B](#phase-b--test-hardening) and the [F1](#f1--the-layer-rule-is-only-enforced-one-hop-deep) remedy (the A1-PR) are APPLIED.** PR [#1062](https://github.com/Pipelex/pipelex/pull/1062) merged to `dev` on 2026-07-27 (squash `6fbdcb2fd`), carrying Phases A and B — recorded at [Checkpoint A](hub-split-tracker.md#checkpoint-a-record--pr-1062-review-follow-ups) and [Checkpoint B](hub-split-tracker.md#checkpoint-b-record--test-hardening). The A1-PR — remedy (d)+(c) per [D-R4](#decisions-taken) — is applied on branch `refactor/Hub-2` and recorded at [Checkpoint A1](#checkpoint-a1-record--the-f1-remedy). **[Phase C](#phase-c--release-wave-additions) is the only phase left**, and it is release-gated. This document is the executable follow-up plan from a full `/review` pass, written so it can be picked up cold in a new session.

**Related:** [`../pr-1062-review-notes.md`](../pr-1062-review-notes.md) records the earlier Codex thread triage (the closure-predicate widening, the `pipe_output` reclassification, and one deliberately-deferred item). That file is about *one* review thread; this one is the whole review. They do not overlap except where noted.

## Cold start — read in this order

1. This section, then [Decisions taken](#decisions-taken) — what was chosen and what was declined. Every decision is taken, including [D-R4](#decisions-taken) (decided 2026-07-27, applied the same day).
2. [Checkpoint A1](#checkpoint-a1-record--the-f1-remedy) — **start here for the current state**: what the remedy actually did, what it measured, and where it differed from the plan.
3. [F1](#f1-the-layer-rule-is-only-enforced-one-hop-deep) — the finding the remedy closed. Kept in full as the record: the measurement, the three routes, and why the headline property was never damaged. It is history now, not open work.
4. [Phase A](#phase-a--in-pr-fixes) and [Phase B](#phase-b--test-hardening) — applied, every Phase B item mutation-verified. [Phase C](#phase-c--release-wave-additions) is the only phase left here, and it is release-gated.

Every finding below was **verified by running it**, not by reading alone. The reproduction command is quoted with each one; re-run it first if you doubt a claim, because several of them contradict what the tracker and the shipped docs currently say.

## What the review confirmed as sound

Recorded so nobody re-audits it. Each of these was independently re-measured, not taken on trust:

- `make check-hub-layering`, `make drift-check`, `make tb`, the new hub tests, and all PR CI checks pass.
- **The headline property reproduces exactly**: importing `cogt.content_generation.content_generator` loads **0** interpreter modules, down from 50. All eight closure-test entry points measure 0.
- **`subject_grants.toml`'s 221/221 churn is a faithful re-sort.** 1758 → 1759 grants; the six dropped and six added pair up exactly as the tracker documents (four library-abstract methods moving to the provider abstracts, `set_observer` deleted, `set_pipelex_hub` splitting in two). No grant lost, no rationale silently rewritten.
- **The TOML config shape is unchanged** — `pipelex.toml` is byte-identical to base.
- Enum completeness is clean: one new enum (`HubLayeringViolationKind`), exhaustive `match`, no unhandled consumer.
- Of 498 changed `.py` files, 437 are pure import-line churn. The reviewer map in the PR body is accurate about where judgment lives.

## Decisions taken

- **D-R1 — the cross-repo/spec work is recorded, not done.** Louis' call: keep PR #1062 as-is and fold [Phase C](#phase-c--release-wave-additions) into the existing release-gated sweep rather than widening this PR. The sweep tables in `TODOS.md` stay as they are for now; this document is the delta.
- **D-R2 — the in-PR fixes ([Phase A](#phase-a--in-pr-fixes)) and the full test hardening ([Phase B](#phase-b--test-hardening)) are approved to apply.** They were deferred out of this session only because they want a cold context, not because they were declined.
- **D-R3 — `Pipelex.teardown`'s process-global scoping reset is accepted as designed.** See [Considered and not changed](#considered-and-not-changed).
- **D-R4 — DECIDED 2026-07-27: the [F1](#f1-the-layer-rule-is-only-enforced-one-hop-deep) remedy is [(d)](#remedy-d--split-the-built-ins-by-layer) paired with a minimal (c), in its own PR after #1062 merges.** Rationale: (d) is the only option that *removes* the defect — (a) re-describes it (enumerate ~24 subpackages and maintain the list forever), (b) hides it behind deferred imports with the false claim standing, (c) alone cannot land (red on today's tree). (d) deletes a weld rather than adding machinery, and moves the built-ins onto the seam external plugins (Temporal, Daytona) already use from outside the repo. (c) rides along because this exact failure mode — transitive breach with both gates green — already occurred invisibly in the PR that introduced the guard, so prevention is not speculative; at ~0.8 s it is cheaper than the guard's current run. The two formerly-blocking questions are settled: **the relocated plugins get one interpreter-side home** (e.g. `pipelex/interpreter_plugins/`, matching the `runtime_hub`/`interpreter_hub` vocabulary) — see [Resolutions](#remedy-d--resolutions-2026-07-27) under Remedy (d) for why "next to what they adapt" was never actually available and how the two-places-to-look smell dissolves; and **(d)+(c) is its own PR** — #1062 carries only [A1](#phase-a--in-pr-fixes)'s doc-honesty fix. A1.1's broad entry-point additions are **superseded by (c)** and consciously skipped; the (d) PR adds a single `pipelex.plugins` entry point as a runtime-truth check. All four candidates and their measurements remain under [Remedy options](#remedy-options-with-what-was-measured-about-each) for the record.

## F1 — the layer rule is only enforced one hop deep

> ✅ **RESOLVED 2026-07-27** by remedy (d)+(c) — see [Checkpoint A1](#checkpoint-a1-record--the-f1-remedy). Everything below is kept verbatim as the record of what was measured and why; the tree now reports **0 of 473** declared runtime-layer modules reaching `interpreter_hub`, and the guard follows the import graph so this class of breach cannot recur silently. Read it for the reasoning, not for open work.

**This is the finding that matters most, and it is not what the earlier review thread was about.**

The guard checks whether a runtime-layer module *directly* imports `pipelex.interpreter_hub`. It does not follow the import graph. `pipelex.plugins` is a declared runtime-layer package, and four of its modules reach `interpreter_hub` transitively. Both gates stay green.

> **Re-verified 2026-07-26**, two independent ways — runtime import measurement, and a static module-level import graph over all of `pipelex/`. The defect is confirmed, but three specifics in the original write-up were wrong and are corrected below. Re-read this section rather than the first draft; the corrections change what the remedy has to cover.

Measured on the branch tip:

```
pipelex.plugins.direct.direct_plugin          interpreter_hub=True  interp_modules= 57 total=462
pipelex.plugins.discovery                     interpreter_hub=True  interp_modules= 67 total=516
pipelex.plugins.builtins                      interpreter_hub=True  interp_modules= 67 total=515
pipelex.plugins.pipe_func.pipe_func_plugin    interpreter_hub=True  interp_modules= 58 total=371

$ .venv/bin/pipelex-dev check-hub-layering --quiet
✓ Hub-layering check: PASSED
```

### F1.a — the blast radius is exactly `pipelex.plugins`

A static sweep of **every** declared runtime-layer module (module-level imports only, `TYPE_CHECKING` and function-body imports excluded, matching what actually loads):

```
declared runtime-layer modules scanned: 476
reaching pipelex.interpreter_hub transitively: 4

  pipelex.cogt                    0 / 130      pipelex.core.concepts          0 /  18
  pipelex.plugins                 4 / 131  ←   pipelex.core.domains           0 /   6
  pipelex.reporting               0 /   6      pipelex.core.memory            0 /   7
  pipelex.system                  0 /  46      pipelex.core.pipes.inputs      0 /   4
  pipelex.tools                   0 /  96      pipelex.core.pipes.stuff_spec  0 /   4
                                               pipelex.core.stuffs            0 /  28
```

Ten of the eleven declared packages are clean across 345 modules; the uncovered ones were also spot-checked at runtime (`reporting.reporting_manager`, `system.configuration.configs`, `core.domains.domain_factory` — all `interp=0`). **The remedy decision is only ever about `plugins`.**

### F1.b — there are three routes, not one

The original write-up named `pipelex.runtime_bridge` as *the* intermediary. It is one of three, and **cutting it alone fixes nothing**:

```
plugins.direct.direct_plugin       → runtime_bridge.direct_orchestrator            → interpreter_hub
plugins.direct.direct_plugin       → pipeline.direct_bundle_validator → pipeline.validate_in_process → interpreter_hub
plugins.pipe_func.pipe_func_plugin → pipe_operators.func.direct_pipe_func_executor → interpreter_hub
plugins.builtins   → both plugins above     (builtins.py:6, builtins.py:16)
plugins.discovery  → builtins               (discovery.py:5; on the boot path, pipelex.py:53)
```

`direct_plugin` has **two independent routes** (`direct_plugin.py:1` and `:4`), so severing the `runtime_bridge` one leaves it breaching through `pipeline`. And `pipe_func_plugin.py:1-2` imports `pipe_operators` **directly** — no hub, no `runtime_bridge`, never touched by that cut.

The structure simplifies the remedy, though: **only two modules are leaves.** `builtins` and `discovery` breach purely as aggregators — `builtins.py` imports every built-in plugin, `discovery.py` imports `builtins` — so they carry no edge of their own. Fix `direct_plugin` and `pipe_func_plugin` and all four clear; leave either one and both aggregators stay breached.

### F1.c — the headline property is *not* damaged

The original write-up called this "a live breach of the property the guard exists to protect," which reads as if the shipped 0-interpreter-modules measurement is invalidated. It is not:

```
pipelex.config                                    interp=0   plugins.builtins loaded=False
pipelex.cogt.content_generation.content_generator interp=0   plugins.builtins loaded=False
pipelex.runtime_hub                               interp=0   plugins.builtins loaded=False
```

Nothing on the inference-layer or `runtime_hub` path reaches the four modules; they are reachable only from full boot, where the interpreter loads anyway. What is actually wrong is narrower and still worth fixing:

- **The scope claim is false.** `docs/contribute/hub-layering.md:184` — *"Every declared package is compliant"* — is true of the direct-import rule only, and reads as a claim about the property. The Known-inversions preamble at `:217` is honest that *"`plugins` is a runtime layer is not yet unconditionally true"*, but files it as placement; it does not say the inversion loads `interpreter_hub` and 67 interpreter modules today. It also understates both instances: `pipe_func_plugin` is described as *"typed by protocols from `pipe_operators/`"* when it imports the concrete `DirectPipeFuncExecutor` at module level, and `direct_plugin` is described as importing *"from `pipeline/`"* with no mention of the `runtime_bridge` route. `plugins/discovery.py` and `plugins/builtins.py` are not listed at all.
- **The guard cannot see this class of breach at all.** Any future runtime-layer module can reach `interpreter_hub` through any undeclared intermediary (`runtime_bridge`, `pipeline`, `pipe_run`, `graph`, `observer`, `tracing`, `config`, `libraries`) with both gates green. This is the generalizable defect; the four modules are just today's instance.

### F1.d — why it was invisible: the closure test covers 6 of 11 packages

The closure test is the only thing that checks the property, and it does so at eight hand-picked entry points. Mapped against the declaration:

```
pipelex.cogt                    COVERED          pipelex.core.concepts         COVERED
pipelex.plugins                 NO ENTRY POINT   pipelex.core.domains          NO ENTRY POINT
pipelex.reporting               NO ENTRY POINT   pipelex.core.memory           COVERED
pipelex.system                  NO ENTRY POINT   pipelex.core.pipes.inputs     COVERED
pipelex.tools                   NO ENTRY POINT   pipelex.core.pipes.stuff_spec COVERED
                                                 pipelex.core.stuffs           COVERED
```

`pipelex.plugins` is the largest declared package (131 modules) and has no entry point. The four uncovered-but-clean packages are a latent gap, not a live one — but they are the reason nothing caught `plugins`.

### The structural read that should inform the remedy

The two leaf modules ([F1.b](#f1b--there-are-three-routes-not-one)) are precisely the ones whose job is to **construct interpreter-layer objects**: `direct_plugin` registers a `DirectOrchestrator` + `DirectBundleValidator`, `pipe_func_plugin` registers a `DirectPipeFuncExecutor`. The other ~127 modules in `plugins/` are inference backends (anthropic, openai, bedrock, gateway, …) and are genuinely runtime. That is not an arbitrary line — it is the same one as *"if it names a `Pipe`, it belongs to the interpreter layer."*

The repo already sanctions the deferral pattern one level down: `pipe_func_executor_registry.py:7-14` defers its `pipe_operators` protocol under `TYPE_CHECKING`, with a comment stating exactly this reasoning. The *plugin* cannot use that trick — it needs the concrete class at runtime, because it constructs it.

### Remedy options, with what was measured about each

**Decided 2026-07-27 — (d) paired with a minimal (c); see [D-R4](#decisions-taken).** The four candidates and their measurements are kept for the record.

- **(a) Declare `plugins` subpackage-by-subpackage**, the treatment `pipelex.core` already got for the same reason. Honest about what the package is, and the structural read above says the split falls on a real line. Wrinkle the original draft did not mention: `builtins.py` imports *every* plugin, so it cannot be runtime-layer while any built-in plugin is interpreter-touching, and `discovery.py` imports `builtins`. So (a) means enumerating `plugins`' ~14 backend subpackages + ~10 registry modules and excluding `direct/`, `pipe_func/`, `builtins.py`, `discovery.py` — noticeably more churn than `core`'s six lines.
- **(b) Defer the imports in the four modules.** Largely **cosmetic**: the modules still load at boot, in the same process, one call later — `register()` runs on the boot path either way. Nothing that does not already import the interpreter would import less; the closure test would go green on an unchanged property. Also needs ~4 function-level imports with `# noqa`, against the house import rule, and must cover all three routes from F1.b.
- **(c) Teach the guard the transitive check** — resolve each runtime-layer module's module-level `pipelex` import closure and flag any path reaching `interpreter_hub`. The only option that closes the generalizable hole. **Cheaper than "a real feature" suggests**: a prototype builds the whole graph and does reachability over all 476 modules in **0.83 s**, against the current guard's own 2.79 s run. It does not stand alone — it would fail on the four modules today, so it forces (a), (b) or (d) alongside it.
- **(d) Split the built-ins by layer and move the weld to the composition root** — Louis' proposal, and a strictly better (a). See [Remedy (d) in full](#remedy-d--split-the-built-ins-by-layer) below; it is the leading candidate.

Whichever is chosen, `docs/contribute/hub-layering.md:184` and the Known-inversions preamble at `:217` need correcting per F1.c.

### Remedy (d) — split the built-ins by layer

**The smell it names.** `builtins.py` is a *composition root smuggled into a leaf package*. Welding the two layers is legitimate work — something has to do it — but it belongs at the boot entrypoint, which sits in no declared layer and is free to weld. Instead it happens inside a module the declaration claims is runtime, which is exactly why both gates stay green while the claim is false.

**The boundary already exists in the code; (d) only makes it visible.** The registrar's slots are *ports* — `OrchestratorProtocol`, `BundleValidatorProtocol` and `PipeFuncExecutorFactoryFn` all live in runtime-layer modules under `plugins/*_registry.py` — and `pipelex.py:427-433` sets every derived registry, orchestrators and bundle validators included, on **`self.runtime_hub`**. So the runtime hub already holds slots whose *adapters* are interpreter-layer. That is ports-and-adapters, and it is what the guard's own remedy text already prescribes: *"have the interpreter layer install it downward at boot"* (`hub_layering_guard.py:130-132`).

**The consistency argument that clinches it.** External plugins already use this seam: our Temporal plugin contributes an orchestrator and our Daytona plugin a PipeFunc executor — both interpreter-touching, both living entirely outside this repo, both arriving through the entry-point mechanism without welding anything. The in-tree built-ins are the *only* ones welding. (d) makes them use the seam externals already use.

**Four moves.** Splitting `builtins.py` alone is *not* enough — `direct/` and `pipe_func/` still sit under `pipelex.plugins` and still breach on their own ([F1.b](#f1b--there-are-three-routes-not-one)):

1. Split `builtins.py`; the runtime half keeps the seventeen backend / storage / secrets plugins.
2. Relocate `plugins/direct/` and `plugins/pipe_func/` to the interpreter side (3 modules).
3. Invert `discovery`'s dependency: `build_registrar` takes the plugin list as a **parameter** instead of importing `BUILTIN_PLUGINS` — the same injection pattern this refactor already applied to `concept_provider` in `core`.
4. `pipelex.py` composes both halves. It is in no declared layer (verified) — the composition root, where welding belongs.

**Simulated against the real import graph** (same graph builder as the [F1.a sweep](#reproduction-commands), with those edges rewritten):

```
AFTER the simulated split+relocation:
  pipelex.plugins modules in scope : 128  (relocated out: 3)
  still reaching interpreter_hub   : 0
  interpreter-package leaks        : 0
```

That is the payoff over (a): it converts *"drop `pipelex.plugins` and enumerate ~24 subpackages"* into **"keep the one declared line and make it true."** Three modules move instead of two dozen getting enumerated.

**Honest counterarguments, so this is not adopted on enthusiasm:**

- **The immediate payoff is honesty and enforceability, not a smaller closure.** `pipelex.py` is the only caller of `build_registrar` and needs everything, so nothing loads less on day one — the same criticism levelled at (b). The difference is real but should be stated precisely: (b) hides the weld behind a deferred import and leaves the false claim standing; (d) removes the weld and makes the claim true. Removing a false claim is not a speculative addition — but do not expect boot to get faster.
- **Where the relocated plugins live was unresolved, and was the weakest part.** A `pipelex/interpreter_plugins/` sibling creates two places to look for a plugin, which is its own smell; housing them next to what they adapt scatters them. **Resolved — see [Resolutions](#remedy-d--resolutions-2026-07-27) below.**
- **`CORE_UNCONDITIONAL_PLUGIN_NAMES` splits along the same line** — `{direct, pipe_func}` interpreter, `{storage, secrets, openai}` runtime — and is consumed by `discovery._skip_if_disabled`, so it must be injected or split alongside move 3. A second thing welded in the same file.
- **It constrains the plugin contract.** (d) assumes no single plugin contributes both a runtime and an interpreter adapter. True today; one that wanted both would have to become two plugin classes. Probably healthy, but it is a real constraint and should be written into the contract rather than left implicit.
- **It does not replace (c).** Nothing in (d) stops the *next* runtime-layer module from welding the same way. (d) fixes today's instance properly; (c) prevents recurrence. Pair them.
- **Scope.** Relocating packages is a real refactor with import churn across the tree. #1062 is already 498 files and green, so (d) most likely wants its own PR rather than widening this one.

### Remedy (d) — resolutions (2026-07-27)

The decisions that unblocked D-R4, so the (d) PR starts from settled ground:

- **Location: one interpreter-side home, not scattered next to the adapters.** The "house them next to what they adapt" option was never actually available — `DirectOrchestratorPlugin` spans two packages (its orchestrator lives in `runtime_bridge`, its bundle validator in `pipeline`), so it has no single adapter-adjacent home. A small dedicated package (e.g. `pipelex/interpreter_plugins/`, consistent with the `runtime_hub`/`interpreter_hub` vocabulary) is the right shape.
- **The two-places-to-look smell dissolves.** The interpreter-side package is *allowed* to import downward, so its builtins module imports the runtime half and exports the single composed list. Exactly one place still answers "what are the built-in plugins" — it just lives in the layer permitted to do the welding. Both callers of `build_registrar` (boot in `pipelex.py`, and the `pipelex plugins list` diagnostic) consume that one list, so the composition is not duplicated.
- **`CORE_UNCONDITIONAL_PLUGIN_NAMES` is passed as a parameter** alongside the plugin list — the same inversion as move 3, two lines more. No split constant left behind in a runtime module.
- **The one-plugin-one-layer constraint is one sentence in `contract.py`'s docstring**, not machinery. If a plugin ever genuinely needs adapters in both layers, decide then.
- **(c) stays minimal**: module-level imports only, with today's `TYPE_CHECKING` carve-outs — matching what actually loads, per the sweep script that found F1. No exclusion/allowlist machinery in the guard to keep `direct/`/`pipe_func/` under `pipelex.plugins`; relocation is the fix, not declaration surgery.
- **Entry points: one, not five.** With (c) doing static transitive coverage of all declared runtime-layer modules, the broad A1.1 additions are redundant cost. The (d) PR adds a single `pipelex.plugins` closure-test entry point as a runtime-truth check (static analysis cannot see dynamic imports) for the package that bit us, and skips the other four uncovered packages.
- **Own PR, after #1062 merges.** #1062 is 498 files, green, and reviewed; widening it re-opens the review for no benefit. #1062 carries only the A1.3 doc-honesty fix; the (d) PR rewrites that doc section again when the inversion actually disappears — a few sentences, acceptable churn.

## F2 — the guard does not enforce its own rule on `runtime_hub.py`

Narrower than F1 and independent of it. `RUNTIME_LAYER_PACKAGES` omits `pipelex.runtime_hub`, so `is_runtime_layer(module_qname="pipelex.runtime_hub")` is `False` and the module at the centre of the rule is exempt from it. Verified by injecting the forbidden import in memory (the file on disk was not touched):

```
runtime_hub.py WITH a forbidden interpreter_hub import  -> NONE (guard says PASS)
same import in a real runtime-layer module              -> [(35, 'interpreter-hub-import')]
```

18 modules in `runtime_hub`'s real 225-module closure sit outside the layer rule. The closure test does catch this one (`pipelex.runtime_hub` is an entry point asserting `pipelex.interpreter_hub not in sys.modules`), so the architecture holds — the hole is in the fast, well-named gate.

The fix is one tuple entry and was verified zero-risk: with `"pipelex.runtime_hub"` added, violations across `pipelex/` + `tests/` are still **0**, and the injected import is caught at line 35.

Also correct `docs/contribute/hub-layering.md:110`, which says `pipe_output` is *"the one runtime-layer module the guard's declaration does not cover"*. `runtime_hub` itself is another, and it is the load-bearing one.

## Phase A — in-PR fixes

Ordered so each step leaves the tree green. **A1, A2 and A6 touch `hub-layering-convention` drift triggers** (`pipelex/cli/dev_cli/commands/hub_layering_guard.py`, `pipelex/runtime_hub.py`), so the contract re-opens: `git add` the trigger files, then `make drift-ack CONTRACT=hub-layering-convention RATIONALE="…"` with an honest sentence.

**A1 is the only item that changes what the boundary actually guarantees. Per [D-R4](#decisions-taken) (decided 2026-07-27) it is now split: only the doc-honesty fix below stays in #1062; the remedy — (d)+(c) — is its own follow-up PR.** Everything else in the phase is independent of A1 and of each other, and can be done in any order.

- [x] **A1 (in #1062) — correct the doc.** ✅ Applied. Per [F1.c](#f1c--the-headline-property-is-not-damaged): `docs/contribute/hub-layering.md:184` ("Every declared package is compliant") is true only of the direct-import rule and reads as a claim about the property — the branch must not merge shipping a claim the measurement contradicts; the Known-inversions preamble at `:217` needs the measurement (the inversion loads `interpreter_hub` and 67 interpreter modules today), not just the placement note, and understates both listed instances; `plugins/discovery.py` + `plugins/builtins.py` are not listed there at all despite pulling `builder` and `codegen`. State that the fix is decided and planned ([D-R4](#decisions-taken)). Do **not** repeat the original draft's framing that the headline property is broken — it is not.
- [x] **A1-PR (own branch `refactor/Hub-2`, off the #1062 merge commit) — apply remedy (d)+(c).** ✅ Applied 2026-07-27, exactly the scope [D-R4](#decisions-taken) and the [Resolutions](#remedy-d--resolutions-2026-07-27) set, with no scope added. Full record at [Checkpoint A1](#checkpoint-a1-record--the-f1-remedy).
- [x] **A2 — close the [F2](#f2-the-guard-does-not-enforce-its-own-rule-on-runtime_hubpy) guard gap.** ✅ Applied; re-verified both ways (0 violations tree-wide, injected import caught). Add `"pipelex.runtime_hub"` to `RUNTIME_LAYER_PACKAGES`; fix the `:110` sentence in `hub-layering.md`. Note the tuple is named `..._PACKAGES` but `is_runtime_layer` matches a bare module fine (`==` or `startswith(pkg + ".")`); add a line to its docstring saying so. Verified zero-risk: still 0 violations, and it catches an injected `interpreter_hub` import at line 35.
- [x] **A3 — delete write-only `RuntimeHub._class_registry`.** ✅ Applied, grant dropped. Remove the field, `set_class_registry`, `get_required_class_registry`, the `pipelex/pipelex.py:339` call, and the now-stale grant `pipelex/runtime_hub.py::RuntimeHub.set_class_registry` (grant staleness is symmetric — `make cko` hard-fails until the registry is cleaned). `get_required_class_registry` has **zero callers** in this repo or any sibling repo; verified. It is pre-existing, but this PR deleted `_observer` for exactly this reason, so the twin is a missed sweep. It is also a live trap: it returns the boot-time global while the module-level `get_class_registry()` returns the **library-scoped** registry, so under `scoped_current_library(...)` the two differ — and the PR's own new test pins that divergence.
- [x] **A4 — hoist the loop-invariant lookup.** ✅ Applied. `pipelex/core/pipes/rendering/input_renderer.py:134` calls `get_concept_library()` once per `_delighten_template` iteration. Hoist it above the `for`. It also defeats `resolve_input_kind`'s `DYNAMIC` early return, which used to skip the lookup entirely.
- [x] **A5 — resolve `PipeProviderAbstract`.** ✅ **Deleted** (the first of the two options), `get_required_pipe` back on `PipeLibraryAbstract`, grant re-recorded there, docstring + `hub-layering.md` + CHANGELOG updated to state the absence is deliberate. Rationale in the [Checkpoint A record](hub-split-tracker.md). It has zero consumers, and its docstring describes the opposite of what the code does: it says core declares pipe resolution *"as a parameter instead of reaching for `interpreter_hub.get_required_pipe`"*, while `core/pipes/rendering/output_renderer.py:51` (a condition's mapped pipes) and `:84` (a sequence's last step) — the two cases the docstring names — both call `interpreter_hub.get_required_pipe` directly. It buys no closure property either, since `core.pipes` is not runtime-layer. **Either delete it** and put `get_required_pipe` back on `PipeLibraryAbstract` (smallest correct surface, consistent with the repo's no-speculative-additions rule), **or** keep it for symmetry with `ConceptProviderAbstract` and rewrite the docstring to say it is not consumed yet. Deleting also means dropping its subject grant.
- [x] **A6 — doc/comment/CHANGELOG accuracy.** ✅ Applied. Five independent one-liners:
    - `pipelex/runtime_hub.py:9-11` forbids naming `core.concepts` and `core.pipes`, but `core.concepts` is a **declared runtime-layer package** and is in `runtime_hub`'s own closure — as line 415 of the same file says. Match the canonical doc: `core.bundles`, `core.interpreter`, and the Pipe-touching modules of `core.pipes`.
    - `pipelex/pipelex.py:122-124` claims RuntimeHub must be installed first because the scoping install *"needs a RuntimeHub already in place"*. It does not — `class_registry_scoping.install` lives in a module that imports nothing from `pipelex`, and `_resolve_scoped_class_registry` reads only the contextvar and the library manager, lazily. State the real reason (runtime is the lower layer, so it reads first) or drop the clause.
    - `CHANGELOG.md:8` maps `TextFormat` / `TemplatingStyle` / `TagStyle` to `pipelex.tools.templating`, whose `__init__.py` is **0 bytes**: `from pipelex.tools.templating import TextFormat` raises `ImportError`. Name the exact modules, as every other entry in the same sentence does. This is the artifact external consumers read.
    - `concept_provider_abstract.py:5` and `pipe_provider_abstract.py:8` still say *"stays high"* — the only two survivors of the low/high → runtime/interpreter vocabulary sweep. **Correction found while applying: there were four.** `libraries/concept/concept_library_abstract.py:11` and `libraries/pipe/pipe_library_abstract.py:11` carried "stays here, high"; the grep that found the first two did not match that phrasing. All four are swept (`pipe_provider_abstract.py` via A5's deletion).
    - `TODOS.md:339` and `:500-501` are off by one. Measured at HEAD: **269 modules / 20,305 SLOC** (claimed 268 / 20,304). The base and H-1 rows reproduce to the digit, so this is a stale re-take, not environment drift. The 0-interpreter-modules row is exact. **Confirmed at Checkpoint A** by re-reading every closure module at both revisions; both tables now carry the correction plus a fresh post-Phase-A column (269 / 20,299).
- [x] **A7 — regenerate the stale error page.** ✅ Applied; the generator also re-filed the index entry into "platform and tooling", following the class's new subsystem. `JobMetadataError` moved to `pipelex/system/exceptions.py`, but `docs/errors/job-metadata-error.md:16` still reports `pipelex.pipeline.exceptions`. It is the only stale page in the set, i.e. `make generate-error-pages` (alias `gep`) was never run in this PR. That page is the `type_uri` target users land on from a runtime error.
- [x] **A8 — restate the class-registry leaf-import rule.** ✅ Applied; the three-importer split was re-verified at HEAD (`concept.py` inside the closure, the other two outside). `docs/contribute/hub-layering.md:164` says to import `class_registry_access` directly *"only from inside `runtime_hub`'s import closure"* — but two of the three in-tree importers are **not** in that closure (`concept_factory.py` and `structure_generation/generator.py`; only `concept.py` is). The code is right and the rule is wrong: the real criterion is "a module that must stay import-light with respect to `runtime_hub` uses the leaf". As written the rule invites someone to "fix" `concept_factory.py` to import from `runtime_hub`, silently re-coupling `core.concepts` to the whole cogt/plugin stack. Nothing checks this mechanically.

> **CHECKPOINT A** — run `make agent-check`, then the full `make agent-test`, then `make drift-check` and ack the re-opened contract. Re-take the two `Measured after` tables in `TODOS.md` at that point rather than copying A6's numbers, since A2–A5 may move them. Push and let CI confirm before starting Phase B.
>
> Per [D-R4](#decisions-taken), the checkpoint covers A1's doc fix plus A2–A8 only — **no red entry point is added in #1062**; the remedy lands in the A1-PR after merge. [F1](#f1-the-layer-rule-is-only-enforced-one-hop-deep) plus the corrected Known-inversions section are the record that keeps the breach visible in the meantime.

## Phase B — test hardening

Additive; landed in one commit after Checkpoint A. B1 and B2 are the two that pin things the current tests only *appear* to pin.

**Every item was verified by mutation, not by watching it go green** — the pinned behavior was removed, the new test was confirmed to fail, and the mutation reverted. What each mutation showed is recorded per item.

- [x] **B1 — test the real teardown, not a simulation.** ✅ Applied. `tests/unit/pipelex/test_hub_lifecycle.py:70` calls `class_registry_scoping.reset()  # what Pipelex.teardown does`. Nothing pinned that the production lines in `Pipelex.teardown` / `teardown_if_needed` do anything — delete them and the suite stayed green, because a stale `_library_id` resolves to `None` and falls back to the global registry rather than raising. Added a real boot → pin a scoped library → `Pipelex.teardown_if_needed()` → assert unscoped → fresh `Pipelex.make()` → assert the resolver is re-installed. The simulation test is kept (it pins `reset()`'s own semantics) with its comment corrected so it no longer claims to cover the wiring. **Mutation-verified**: deleting `class_registry_scoping.reset()` from `Pipelex.teardown` fails the new test and *only* it — the other three in the module still pass, which is exactly the finding.
- [x] **B2 — give the closure detector a negative control.** ✅ Applied. `_CLOSURE_SCRIPT` is a `textwrap.dedent` string, so no linter sees `INTERPRETER_PACKAGES` / `is_interpreter`; a typo makes all entry points pass vacuously, forever. Parametrized `(entry_point, expected_returncode)` with `pipelex.interpreter_hub` as the dirty case. **One thing the plan did not anticipate, and it changes the assertion**: asserting `returncode == 1` alone would *not* have pinned the predicate, because the script's second check (`pipelex.interpreter_hub in sys.modules`) exits 1 for that entry point regardless. The test asserts the **offender message** as well, so the control fails when `is_interpreter` stops working. **Mutation-verified**: typo-ing `INTERPRETER_PACKAGES` and emptying `INTERPRETER_CORE` fails the control while all eight clean entry points pass vacuously — the exact failure mode.
- [x] **B3 — cover `check_hub_layering_cmd`.** ✅ Applied as `tests/unit/pipelex/cli/dev/test_check_hub_layering_cmd.py`, mirroring `test_check_keyword_only_cmd_fix.py`'s mocked-console/mocked-scanner shape. Covers both `sys.exit(1)` paths, the quiet/panel split both ways, the per-kind grouping with its remedy, and that the success panel names every declared runtime-layer package. The missing-root case asserts the scanner is **never called** — scanning nothing must not read as a pass. **Mutation-verified**: removing both `sys.exit(1)` calls fails four of the six tests.
- [x] **B4 — cover the guard's filesystem surface.** ✅ Applied as `tests/unit/pipelex/cli/dev/test_hub_layering_guard_filesystem.py`, a tmp tree in the style of `test_keyword_only_guard_single_file.py`. Covers `collect_all_violations` over both roots (a runtime-layer breach reported, the identical import in `pipeline/` correctly *not*, a `tests/` dead-hub string reported), `iter_source_files`' `__pycache__` exclusion, and `module_qname_for`'s `__init__`-stripping both directly and end to end through a real scan. **Mutation-verified**: dropping the `__pycache__` skip fails two tests.
- [x] **B5 — test `concept_provider` as an actual injection.** ✅ Applied as `tests/unit/pipelex/core/memory/input_shaper/test_provider_injection.py`. A `mocker.Mock(spec=ConceptProviderAbstract)` whose `is_compatible` only ever matches `Number` moves a `Text` concept from the TEXT arm to the NUMBER arm — an outcome unreachable through the real library. **Mutation-verified**: making `resolve_input_kind` accept the parameter and then call `get_concept_library()` anyway fails this test alone, with all 69 other `input_shaper` tests green.
- [x] **B6 — tighten the `TYPE_CHECKING` carve-out.** ✅ Applied — tightened, not pinned-as-deliberate. `_is_type_checking_test` now requires the receiver to be `Name(id="typing")` (new `TYPING_MODULE_NAME` constant), with a test asserting three unrelated receivers stay violations. Verified safe first: nothing in `pipelex/` or `tests/` uses the attributed form at all, let alone under an alias. **Mutation-verified**: reverting to `ast.Attribute(attr=attr)` fails the new test and nothing else.
- [x] **B7 — bound the closure subprocess.** ✅ Applied. `subprocess.run` gained `timeout=SUBPROCESS_TIMEOUT_SECONDS`, wrapped in a `_run_closure` helper that turns `TimeoutExpired` into an `AssertionError` naming the entry point and the bound.

> **CHECKPOINT B** ✅ **CLEARED** — `make agent-check` ✅ · full `make agent-test` ✅ · `make drift-check` ✅.
>
> **Correction to this plan: B6 *does* re-open a drift contract.** `pipelex/cli/dev_cli/commands/hub_layering_guard.py` is a `hub-layering-convention` trigger, so the note that said "nothing here re-opens a drift contract" was wrong. Reviewed and acked: `docs/contribute/hub-layering.md`'s `TYPE_CHECKING` bullet now states the receiver constraint, and its two test-module sentences were refreshed for B1/B2/B7. Worth carrying forward — the review caught staleness the contract's own triggers **cannot** see: the two test modules are deliberately not triggers, so the contract fired on the guard and the read-through found the spillover. Logged in `wip/drift-contracts/dogfood-log.md` as the second consecutive `real-catch` for this contract.
>
> Per [D-R4](#decisions-taken) the property-side fix is in the A1-PR, not here: no new green entry point landed in #1062, and B2's control is dirty by definition so it survives the remedy unchanged.

## Checkpoint A1 record — the F1 remedy

Branch `refactor/Hub-2`, off `6fbdcb2fd` (the #1062 merge). Gates: `make agent-check` ✅ (pyright 0 errors, mypy 2,361 files, keyword-only PASSED, hub-layering PASSED) · full `make agent-test` ✅ · `make tb` ✅ · `make drift-check` ✅ (two contracts reviewed and acked — see below).

### What landed, against what was planned

The [four moves of (d)](#remedy-d--split-the-built-ins-by-layer) plus [(c)](#remedy-options-with-what-was-measured-about-each), and nothing else:

- **`pipelex/interpreter_plugins/`** is the new interpreter-side home. `plugins/direct/` and `plugins/pipe_func/` moved there wholesale (`git mv`, subpackage shape preserved, so the only churn is the parent path). Its `builtins.py` imports the runtime half — downward, which the interpreter layer may do — and exports the composed `BUILTIN_PLUGINS` / `CORE_UNCONDITIONAL_PLUGIN_NAMES`.
- **`pipelex/plugins/builtins.py`** keeps the seventeen runtime adapters as `RUNTIME_BUILTIN_PLUGINS` / `RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES`. The composed list keeps the canonical names, so exactly one symbol still answers "what are the built-in plugins".
- **`build_registrar` takes both as required keyword parameters.** No default, so a caller cannot silently boot with half the plugins. Both call sites — `pipelex.py` and the `pipelex plugins list` diagnostic — pass the composed lists.
- **The guard learned the transitive rule** (`collect_transitive_violations`): build the module-level import graph of `pipelex/`, reverse-BFS once from `interpreter_hub` to find every module that reaches it, then report the runtime-layer ones with the shortest chain and the line of the first hop. Module-level imports only, `TYPE_CHECKING` and function bodies excluded; a *direct* import is left to rule 1 rather than double-reported; no escape hatch.
- **`pipelex.plugins.builtins` joined the closure test's entry points** — one, as decided, not the broad five-package addition.
- **`PipelexPlugin`'s docstring carries the one-plugin-one-layer invariant**, as a sentence, not machinery.

### Measured

```
                                        before        after
declared runtime-layer modules              477          473   (4 relocated)
  ... reaching interpreter_hub                4            0
pipelex.plugins modules                     131          127
pipelex.plugins.discovery   interp=          67            0
pipelex.plugins.builtins    interp=          67            0
```

The plan's simulation predicted **128** modules left in `pipelex.plugins`, not 127: its `RELOCATED` filter used the prefix `pipelex.plugins.pipe_func.` with a trailing dot, which misses the package's own `__init__`. Four files moved, not three.

The *before* figure is **477**, not the 476 the [F1.a sweep](#f1a--the-blast-radius-is-exactly-pipelexplugins) printed: that table has one row per declared runtime-layer **package** and so omits `pipelex.runtime_hub`, which is a bare *module* entry in `RUNTIME_LAYER_PACKAGES` — and the one module the whole rule exists to protect. Its reaching count was 0 either way, so no conclusion moves; the sweep's own rows are kept verbatim above as the record. Re-measured on the base commit with the shipped guard's helpers: per-entry sum and distinct count both 477, `pipelex.runtime_hub → 1`. 477 → 473 is the same four relocated modules the `pipelex.plugins 131 → 127` row already counts.

**What the transitive rule costs, measured honestly.** Do not difference against the 2.79s in the [remedy options](#remedy-options-with-what-was-measured-about-each) — that was taken in an earlier session on a different tree, and comparing to it understates the cost. Measured back-to-back on this tree, same binary, with the transitive pass enabled and then disabled:

```
with    3.06s / 2.87s / 2.83s        in-process: per-file rules (both roots)  1.50s
without 2.46s / 2.48s / 2.47s                    transitive rule (pipelex/)   0.38s
```

**+0.38s, or +15% of the command** (+25% of the scan work; the remaining ~1.0s is process startup). Under the 0.83s the prototype suggested, but not free.

**All of it is re-parsing.** Over 956 modules and 4,403 edges: the reverse-BFS reachability is **0.5ms**, and the graph visitor is cheaper than the per-file collector (it skips function bodies and walks no string constants). So the honest description is not "reachability is cheap because it runs once in reverse" — it is "the pass parses the tree a second time, and parsing is the whole bill."

That is also where the optimization is, if the cost ever matters: the per-file pass already parses every `pipelex/` module, so feeding one parse to both collectors would recover most of the 0.38s. **Deliberately not done.** It would couple two passes that are currently independent and independently testable — `find_violations_in_source` takes *source text* and is what the snippet tests drive, while the graph builder needs an AST plus a resolved qname per file — and 0.38s on a gate whose parent (`make agent-check`) is dominated by pyright and mypy is not worth that. Revisit only if `pipelex/` grows enough to make the guard a felt cost in CI.

### Verified by reproducing the defect, not only by going green

A rule that reports nothing is indistinguishable from a rule that sees nothing. So the new check was run against **`HEAD` — the pre-remedy tree** (`git archive HEAD pipelex`, scanned with the new guard from the working tree): it reproduces F1 exactly — the same four modules, with the same three routes [F1.b](#f1b--there-are-three-routes-not-one) documented, including both of `direct_plugin`'s independent routes. On the fixed tree it reports 0. The ten unit tests in `tests/unit/pipelex/cli/dev/test_hub_layering_transitive.py` were mutation-verified: dropping the function-body skip fails the two deferred-import cases, dropping the runtime-layer filter fails two more, and reporting direct imports fails the no-double-report case.

### The existing tests this touched, and why

- `test_plugin_discovery.py` patched `discovery.BUILTIN_PLUGINS`, a module global that no longer exists. Its helper now passes the list in — which is the honest shape anyway, since that is how production calls it. It gained one test pinning that the composed list *is* both halves in order, with unique names: the failure mode the split introduces is a half silently dropping out, which would present as a plugin quietly missing at boot rather than as an import error.
- `test_import_light_boot.py` imports the composed list inside its blocked-SDK subprocess. Loading it pulls the interpreter, which is expected and is exactly why discovery takes the list as a parameter; the assertion — that registering the built-ins imports no backend SDK — is unchanged and still passes.
- `test_check_hub_layering_cmd.py` now mocks **both** scans. Mocking only the per-file one would have left the transitive pass walking the real tree inside a unit test. Two tests were added: the merged report, and a transitive finding failing the gate on its own.

### Drift

Both re-opened contracts were reviewed for real and acked, with entries in `wip/drift-contracts/dogfood-log.md`:

- **`hub-layering-convention` — real-catch (third consecutive non-import-churn opening).** This one is a new mode worth naming: the doc honestly recorded the defect *and* announced the planned fix, so landing the fix falsified two of its sections by design. A doc that records a known defect accrues a debt only a trigger can call in. The contract's two prescribed mechanical checks both passed unchanged (33 + 32 hub symbols covered, 12 declared packages named) and again saw none of it — three for three.
- **`cli-docs` — clean-pass, but the first on a genuinely behavior-adjacent trigger** rather than an import sweep: `plugins_cmd.py`'s call actually changed shape. Reviewed against the live CLI: same subcommand, same options, same five columns, all 19 built-ins in the same order.

### What this does *not* do

- **Nothing loads less.** `pipelex.py` is still the only caller that needs everything, so boot's closure is unchanged — as [the counterargument](#remedy-d--split-the-built-ins-by-layer) said it would be. The payoff is that the declaration is now true and mechanically kept true.
- **`plugins/pipe_func_executor_registry.py`'s placement inversion is still unfixed** — it is type-only under `TYPE_CHECKING`, so it breaches neither rule. Still recorded in Known inversions.
- **Phase C is untouched** and still release-gated.

## Phase C — release-wave additions

Per **D-R1**, none of this lands in PR #1062. Fold it into the existing release-gated cross-repo sweep in `TODOS.md`.

### C1 — `pipelex.hub` is a governed, spec'd, conformance-tested surface

`docs/specs/pipelex-transport-boundary.md` §A declares it: *"The `pipelex.hub` module is the intended cross-boundary seam; these accessors are stable by design."* It is verified by `conformance/tests/pipelex_transport/test_provider_surface.py`, which carries **no skip marker** — it is active. Running that suite's own `ALLOWED_SURFACE` against this branch:

```
governed surface entries: 41
BROKEN by this branch:     7
   MODULE DELETED   pipelex.hub::get_orchestrator_registry
   MODULE DELETED   pipelex.hub::get_required_pipe
   MODULE DELETED   pipelex.hub::get_library_manager
   MODULE DELETED   pipelex.hub::scoped_current_library
   MODULE DELETED   pipelex.hub::get_current_library_id_or_none
   MODULE DELETED   pipelex.pipeline.job_metadata::JobMetadata
   MODULE DELETED   pipelex.graph.trace_context::TraceContext
```

The workspace `CLAUDE.md` rule is explicit: *"When you change a documented surface in `docs/specs/` or its verifying test in `conformance/`, update both sides in the same change and run `make check-spec-links`."* Strictly, this PR is already out of compliance with that rule; D-R1 accepts that consciously because the whole consumer sweep is release-gated and splitting spec-from-consumers would be worse. **The release wave must update section A of the spec** (all five accessors are interpreter-layer), retarget the `JobMetadata` / `TraceContext` rows to `pipelex.system.*`, update `conformance/tests/pipelex_transport/test_data.py` in lockstep, and run `make check-spec-links` in `conformance/`.

### C2 — five consumer repos are missing from the sweep tables

Every count the tables *do* list reproduces exactly (temporal 35, mistralai-workflows 11, api 9, cookbook 2, cocode 2). They are simply incomplete:

| repo | `pipelex.hub` files | moved-type files | pipelex pin | why it matters |
| --- | --- | --- | --- | --- |
| `pipelex-transport` | **8** (2 production) | 7 | `>=0.40.0` | `pipelex_transport/bridge.py:165` calls `WorkingMemoryFactory.make_from_pipeline_inputs` **without the now-required `concept_provider`** — the only production call site of a changed signature outside this repo |
| `pipelex-daytona-sandbox` | 1 | 3 | `>=0.40.0` | **entry-point plugin** (`[project.entry-points."pipelex.plugins"]`), so it fails inside a *host* pipelex process at registration, not in its own tests |
| `pipelex-demo-mistral` | 9 | 5 | `>=0.35.0` | 4+ example workflows call the changed signature |
| `pipelex-demo-vibe` | 9 | 5 | `>=0.35.0` | same (both are checkouts of `pipelex-demos.git`) |
| `conformance` | — | 1 | dynamic | C1 above |

All unbounded `>=` pins, so all resolve to the new release. `pipelex-workshop` (`==0.20.3`) and `pipelex-demos` / `pipelex-demo-frostbeam` (`==0.34.0`) also import `pipelex.hub` but are version-pinned, so they are safe — list them for completeness, not urgency. `test-bed` has one test-only import at `>=0.18.3`.

Note that `pipelex-transport` and `pipelex-daytona-sandbox` are **absent from the workspace `CLAUDE.md` repo table too**, which is why they were missed. Adding them there is the durable fix; otherwise the next sweep misses them again.

### C3 — the moved types are a wire-format change, not only an import change

`CHANGELOG.md:8` says *"only the Python homes moved."* For `JobMetadata` and `TraceContext` that undersells it: kajson embeds `__module__` in the serialized payload, and the Temporal data converter kajson-encodes every `BaseModel` crossing the workflow/activity boundary — `PipeJob.job_metadata: JobMetadata` is on that path. Verified: encoding now emits `"__module__": "pipelex.system.job_metadata"`, and decoding an old payload raises `KajsonDecoderError`.

**This is not a bug** — Temporal has never shipped to production, and the repo's no-backward-compat policy is explicit. It is worth one changelog sentence so a plugin maintainer knows the runner and worker must roll forward together rather than independently.

## Considered and not changed

Recorded so these are not re-litigated. Each was investigated and is a deliberate tradeoff, not an oversight:

- **`class_registry_scoping.reset()` in `Pipelex.teardown` is process-global while `_library_id` is a ContextVar.** A run still in flight when teardown fires loses its per-run scoped registry and falls back to the shared one (which `KajsonManager.teardown()`, twelve lines earlier, has already re-minted empty). Pre-refactor this window did not exist. Reachability is narrow — process shutdown or a failed boot with concurrent in-flight runs — and everything else is being demolished at that moment anyway. **D-R3: accepted as designed**; the reset is what makes a torn-down library unreachable, which is the property step 1.7 was written for.
- **boto3 loads eagerly in every booted process.** `pipelex/tracing/event_log_factory.py:5` imports `dynamodb_event_log`, which runs a module-level `try: import boto3` unconditionally — even for the default NDJSON backend. It is **not** in the guarded runtime closure, so the headline property is unaffected, but it *is* in `import pipelex.pipelex`'s closure: ~41 ms and ~150 modules, against the ~27 ms this entire refactor buys on full boot. A three-line fix (move the import into the `case TracingBackend.DYNAMODB:` branch, the pattern `render_generate.py` already uses for pypdfium2). Out of scope here, but the tracker should stop filing it under "not scheduled" when it dominates the number the tracker headlines.
- **The D5 indirection costs ~32 ns per `get_class_registry()` call** (213 ns → 245 ns, three frames instead of one). Not on any hot path — the call sites are per-concept-resolution, not per-item. No action; recorded so nobody collapses the layering later on a hunch, since the indirection is what makes the zero-interpreter closure possible.
- **Wall-clock is a smaller win than the module count suggests.** `content_generator` improves 412 ms → 359 ms (-13%), but `import pipelex.pipelex` only 718 ms → 691 ms (-4%), because third-party imports dominate and are untouched (767 non-pipelex modules remain: pydantic 70, faker 66, rich 63, markdown_it 62, polyfactory 28). Nothing in the PR overstates this; the tracker simply does not state it. The win is architectural and accrues to runtime-only embedders, not to CLI startup.
- **The published `hub-layering.md` points at `wip/pr-1062-review-notes.md`**, and two test docstrings do the same. `wip/` is outside `docs_dir`, so the reference is unreachable for a reader on docs.pipelex.com, and the file is by convention archived once the PR lands. Fold the wart into one in-place sentence in the published doc and keep the pointer only in `TODOS.md`. Low priority; batch it with A5 if convenient.
- **`drift.toml`'s `hub-layering-convention` omits `pipelex/system/registries/class_registry_access.py`** from its triggers, though the doc it protects devotes a named section to that module. Renaming `class_registry_scoping` or changing the default-resolver semantics would silently falsify it. One line to add whenever the contract is next touched.
- **`hub_layering_guard` duplicates two filesystem helpers from `keyword_only_guard`.** The stated rationale is half right: `keyword_only_guard` genuinely is stdlib-only and has a by-path `__main__` entry, so a shared third module would defeat its cold-start budget — but that does not explain why `hub_layering_guard` could not import *from* it, since it has no `__main__` and its only importer already pulls `pipelex.runtime_hub`. The copies have already drifted (positional vs keyword-only signatures). Either import them or correct the docstring.

## Reproduction commands

Everything above was measured with these. Run from `_hub/`.

```bash
# F1 — a declared runtime-layer module reaching interpreter_hub transitively.
# Swap in pipelex.config / pipelex.cogt.content_generation.content_generator / pipelex.runtime_hub
# for the F1.c control: those measure interp=0 and never load plugins.builtins.
for m in pipelex.plugins.direct.direct_plugin pipelex.plugins.discovery; do
  .venv/bin/python -c "
import sys, importlib
importlib.import_module('$m')
INTERP={'libraries','pipe_operators','pipe_controllers','codegen','builder'}
mods=[n for n in sys.modules if n.startswith('pipelex.')]
print('$m', 'interpreter_hub=', 'pipelex.interpreter_hub' in sys.modules,
      'interp=', len([n for n in mods if n.split('.')[1] in INTERP]),
      'builtins=', 'pipelex.plugins.builtins' in sys.modules)"
done
.venv/bin/pipelex-dev check-hub-layering --quiet   # still PASSED

# F1.b — the shortest real import path to each offender, traced rather than guessed
.venv/bin/python -c "
import importlib, sys
chain, stack = {}, []
real = importlib._bootstrap._find_and_load
def traced(name, import_):
    if stack and name not in chain: chain[name] = stack[-1]
    stack.append(name)
    try: return real(name, import_)
    finally: stack.pop()
importlib._bootstrap._find_and_load = traced
importlib.import_module('pipelex.plugins.discovery')
for target in ('pipelex.interpreter_hub', 'pipelex.libraries', 'pipelex.builder', 'pipelex.codegen'):
    path, cur = [target], target
    while cur in chain: cur = chain[cur]; path.append(cur)
    print(' <- '.join(path))"

# F1.a / F1.d — the static sweep: which declared runtime-layer modules reach interpreter_hub,
# and which declared packages have no closure-test entry point.
.venv/bin/python - <<'PY'
import ast, sys
from collections import deque
from pathlib import Path
sys.path.insert(0, ".")
from pipelex.cli.dev_cli.commands.hub_layering_guard import RUNTIME_LAYER_PACKAGES, is_runtime_layer

def qname(p):
    parts = list(p.with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)

class V(ast.NodeVisitor):
    def __init__(self, pkg): self.pkg, self.out, self.tc = pkg, set(), 0
    def visit_If(self, n):
        t = n.test
        if (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING"):
            self.tc += 1
            for s in n.body: self.visit(s)
            self.tc -= 1
            for s in n.orelse: self.visit(s)
        else: self.generic_visit(n)
    def visit_FunctionDef(self, n): pass          # deferred imports do not load
    def visit_AsyncFunctionDef(self, n): pass
    def visit_Import(self, n):
        if not self.tc:
            self.out.update(a.name for a in n.names if a.name.startswith("pipelex"))
    def visit_ImportFrom(self, n):
        if self.tc: return
        if n.level:
            parts = self.pkg.split(".") if self.pkg else []
            base = ".".join(parts[: len(parts) - (n.level - 1)])
            base = f"{base}.{n.module}" if n.module else base
        else: base = n.module or ""
        if base.startswith("pipelex"):
            self.out.add(base); self.out.update(f"{base}.{a.name}" for a in n.names)

edges, all_mods = {}, set()
for p in sorted(Path("pipelex").rglob("*.py")):
    if "__pycache__" in p.parts: continue
    q = qname(p); all_mods.add(q)
    v = V(".".join(p.parent.parts)); v.visit(ast.parse(p.read_text(encoding="utf-8")))
    edges[q] = v.out

def resolve(c):
    while c:
        if c in all_mods: return c
        if "." not in c: return None
        c = c.rsplit(".", 1)[0]

TARGET = "pipelex.interpreter_hub"
runtime_mods = sorted(m for m in all_mods if is_runtime_layer(module_qname=m))

# --- Remedy (d) simulation: uncomment the four edits to measure the split+relocation ----
# Must run BEFORE the BFS below, since it rewrites the edges the BFS walks.
# Expect: 128 scanned, 0 reaching interpreter_hub (against 476 / 4 unsimulated).
# RELOCATED = {m for m in all_mods if m.startswith(("pipelex.plugins.direct", "pipelex.plugins.pipe_func."))}
# edges["pipelex.plugins.builtins"] = {e for e in edges["pipelex.plugins.builtins"]
#     if not e.startswith(("pipelex.plugins.direct", "pipelex.plugins.pipe_func."))}   # builtins splits
# edges["pipelex.plugins.discovery"] = {e for e in edges["pipelex.plugins.discovery"]
#     if not e.startswith("pipelex.plugins.builtins")}                                 # discovery takes a param
# runtime_mods = [m for m in runtime_mods if m.startswith("pipelex.plugins") and m not in RELOCATED]

bad = {}
for start in runtime_mods:
    seen, q = {start}, deque([(start, [start])])
    while q and start not in bad:
        cur, path = q.popleft()
        for raw in edges.get(cur, ()):
            m = resolve(raw)
            if m is None or m in seen: continue
            if m == TARGET: bad[start] = path + [m]; break
            seen.add(m); q.append((m, path + [m]))

print(f"scanned {len(runtime_mods)} declared runtime-layer modules; {len(bad)} reach {TARGET}")
EPS = ["pipelex.cogt.content_generation.content_generator", "pipelex.runtime_hub",
       "pipelex.core.concepts.structure_generation.generator", "pipelex.core.memory.input_shaper",
       "pipelex.core.memory.working_memory_factory", "pipelex.core.pipes.inputs.input_stuff_specs_factory",
       "pipelex.core.pipes.stuff_spec.stuff_spec_factory", "pipelex.core.stuffs.stuff_factory"]
for pkg in RUNTIME_LAYER_PACKAGES:
    inside = lambda m: m == pkg or m.startswith(pkg + ".")
    n = len([m for m in bad if inside(m)])
    tot = len([m for m in runtime_mods if inside(m)])
    ep = "COVERED" if any(inside(e) for e in EPS) else "NO ENTRY POINT"
    print(f"  {pkg:38s} {n:4d} / {tot:4d} breaching   {ep}")
for m, path in sorted(bad.items()): print("   ", " -> ".join(path))
PY

# F2 — the guard exempts runtime_hub.py from its own rule
.venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from pipelex.cli.dev_cli.commands.hub_layering_guard import is_runtime_layer
print('runtime_hub is runtime layer:', is_runtime_layer(module_qname='pipelex.runtime_hub'))"

# C1 — the governed surface, broken
.venv/bin/python -c "
import ast, importlib
from pathlib import Path
p = Path('/Users/lchoquel/repos/Pipelex/conformance/tests/pipelex_transport/test_data.py')
for node in ast.walk(ast.parse(p.read_text())):
    if isinstance(node, ast.AnnAssign) and getattr(node.target, 'id', '') == 'ALLOWED_SURFACE':
        surface = [tuple(ast.literal_eval(e)) for e in node.value.elts]; break
for mod, sym, _ in surface:
    try: importlib.import_module(mod)
    except ModuleNotFoundError: print('MODULE DELETED', f'{mod}::{sym}')"

# The headline property (unchanged, still exact) — full snippet in TODOS.md 'Exit criteria'
```
