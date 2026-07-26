# PR #1062 — `/review` follow-ups

**Status:** nothing below is applied. The branch `refactor/Hub` is pushed, PR [#1062](https://github.com/Pipelex/pipelex/pull/1062) is open against `dev`, and **all 25 CI checks are green** at `aef0da638`. This document is the executable follow-up plan from a full `/review` pass, written so it can be picked up cold in a new session.

**Related:** [`../pr-1062-review-notes.md`](../pr-1062-review-notes.md) records the earlier Codex thread triage (the closure-predicate widening, the `pipe_output` reclassification, and one deliberately-deferred item). That file is about *one* review thread; this one is the whole review. They do not overlap except where noted.

## Cold start — read in this order

1. This section, then [Decisions taken](#decisions-taken) — what was chosen and what was explicitly declined.
2. [F1](#f1-the-layer-rule-is-only-enforced-one-hop-deep) — the biggest finding, and the only one that changes how the boundary is enforced. It invalidates a claim the shipped doc makes.
3. [Phase A](#phase-a--in-pr-fixes) — the code changes, in dependency order.
4. [Phase B](#phase-b--test-hardening) and [Phase C](#phase-c--release-wave-additions) — additive; neither blocks the other.

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

## F1 — the layer rule is only enforced one hop deep

**This is the finding that matters most, and it is not what the earlier review thread was about.**

The guard checks whether a runtime-layer module *directly* imports `pipelex.interpreter_hub`. It does not follow the import graph. `pipelex.plugins` is a declared runtime-layer package, and four of its modules reach `interpreter_hub` through `pipelex.runtime_bridge`, which sits in no declared layer and is therefore scanned for the dead-module rule only. Both gates stay green.

Measured on the branch tip:

```
pipelex.plugins.direct.direct_plugin          interpreter_hub=True  interp_modules= 57 total=462
pipelex.plugins.discovery                     interpreter_hub=True  interp_modules= 67 total=516
pipelex.plugins.builtins                      interpreter_hub=True  interp_modules= 67 total=515
pipelex.plugins.pipe_func.pipe_func_plugin    interpreter_hub=True  interp_modules= 58 total=371

$ .venv/bin/pipelex-dev check-hub-layering --quiet
✓ Hub-layering check: PASSED
```

The edge:

```
pipelex/plugins/direct/direct_plugin.py:4   from pipelex.runtime_bridge.direct_orchestrator import DirectOrchestrator
pipelex/runtime_bridge/direct_orchestrator.py:13   from pipelex.interpreter_hub import scoped_pipe_router   # module level
```

`plugins.discovery` is on the boot path (`Pipelex.setup` runs it), and it pulls `pipelex.builder`, all of `pipelex.codegen.emitters`, `pipelex.libraries`, `pipe_operators` and `pipe_controllers`.

Two things follow, and they should be separated when fixing:

- **The measurement is worse than the doc admits.** `docs/contribute/hub-layering.md`'s Known-inversions section is already honest that `plugins → runtime_bridge` exists and that *"`plugins` is a runtime layer is not yet unconditionally true."* What it does not say is that the inversion **loads `interpreter_hub` and 67 interpreter modules today** — it is described as a placement wart, but it is a live breach of the property the guard exists to protect. Line 184's *"Every declared package is compliant"* is true only of the direct-import rule, and reads as a claim about the property.
- **Any future runtime-layer module can do the same thing** through any undeclared intermediary (`runtime_bridge`, `pipeline`, `pipe_run`, `graph`, `observer`, `tracing`, `config`, `libraries`) with both gates green. This is the generalizable defect; the four current modules are just the instance.

**Recommended fix, cheapest first:**

1. Add one closure-test entry point per declared runtime-layer package — `pipelex.plugins.discovery` at minimum. It costs a line and **fails today**, which is exactly the point: it converts an invisible breach into a red test.
2. Then decide the real remedy: either drop `pipelex.plugins` from `RUNTIME_LAYER_PACKAGES` and declare only its genuinely-runtime subpackages (the package-by-package treatment `pipelex.core` already got, for the same reason), or fix the four modules by deferring the `runtime_bridge` import.
3. Optionally teach the guard the transitive check — for a runtime-layer module, resolve the closure of its module-level `pipelex` imports and flag any path reaching `interpreter_hub`. Strictly better, but it is a real feature, not a review fix.

Whichever is chosen, correct `docs/contribute/hub-layering.md:184` and the Known-inversions preamble at `:217`, and name `plugins/discovery.py` + `plugins/builtins.py` there — they pull the two heaviest interpreter packages and are not listed at all.

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

**Do A1 first.** It is the only item that changes what the boundary actually guarantees; everything after it is independent and can be reordered freely.

- [ ] **A1 — resolve [F1](#f1-the-layer-rule-is-only-enforced-one-hop-deep): the layer rule is enforced only one hop deep.** Three sub-steps, in order:
    1. **Make the breach visible.** Add one closure-test entry point per declared runtime-layer package — `pipelex.plugins.discovery` at minimum — to `RUNTIME_LAYER_ENTRY_POINTS` in `tests/unit/pipelex/test_runtime_layer_import_closure.py`. **It fails today**, which is the point: it converts an invisible breach into a red test before anything is changed. (This is the same edit [B2](#phase-b--test-hardening) wants; do it here and B2 only adds the known-dirty negative control on top.)
    2. **Pick the remedy** — a real decision, not a mechanical fix. Either (a) drop `pipelex.plugins` from `RUNTIME_LAYER_PACKAGES` and declare only its genuinely-runtime subpackages, the package-by-package treatment `pipelex.core` already got for exactly this reason; or (b) fix the four modules by deferring the `runtime_bridge` import; or (c) teach the guard the transitive check (resolve the module-level `pipelex` closure of each runtime-layer module and flag any path reaching `interpreter_hub`). (c) is strictly best and is a feature, not a review fix — if it is chosen, it is its own phase.
    3. **Correct the doc.** `docs/contribute/hub-layering.md:184` ("Every declared package is compliant") is true only of the direct-import rule and reads as a claim about the property; the Known-inversions preamble at `:217` needs the measurement, not just the placement note; and `plugins/discovery.py` + `plugins/builtins.py` are not listed there at all despite pulling `builder` and `codegen`.
- [ ] **A2 — close the [F2](#f2-the-guard-does-not-enforce-its-own-rule-on-runtime_hubpy) guard gap.** Add `"pipelex.runtime_hub"` to `RUNTIME_LAYER_PACKAGES`; fix the `:110` sentence in `hub-layering.md`. Note the tuple is named `..._PACKAGES` but `is_runtime_layer` matches a bare module fine (`==` or `startswith(pkg + ".")`); add a line to its docstring saying so. Verified zero-risk: still 0 violations, and it catches an injected `interpreter_hub` import at line 35.
- [ ] **A3 — delete write-only `RuntimeHub._class_registry`.** Remove the field, `set_class_registry`, `get_required_class_registry`, the `pipelex/pipelex.py:339` call, and the now-stale grant `pipelex/runtime_hub.py::RuntimeHub.set_class_registry` (grant staleness is symmetric — `make cko` hard-fails until the registry is cleaned). `get_required_class_registry` has **zero callers** in this repo or any sibling repo; verified. It is pre-existing, but this PR deleted `_observer` for exactly this reason, so the twin is a missed sweep. It is also a live trap: it returns the boot-time global while the module-level `get_class_registry()` returns the **library-scoped** registry, so under `scoped_current_library(...)` the two differ — and the PR's own new test pins that divergence.
- [ ] **A4 — hoist the loop-invariant lookup.** `pipelex/core/pipes/rendering/input_renderer.py:134` calls `get_concept_library()` once per `_delighten_template` iteration. Hoist it above the `for`. It also defeats `resolve_input_kind`'s `DYNAMIC` early return, which used to skip the lookup entirely.
- [ ] **A5 — resolve `PipeProviderAbstract`.** It has zero consumers, and its docstring describes the opposite of what the code does: it says core declares pipe resolution *"as a parameter instead of reaching for `interpreter_hub.get_required_pipe`"*, while `core/pipes/rendering/output_renderer.py:51` (a condition's mapped pipes) and `:84` (a sequence's last step) — the two cases the docstring names — both call `interpreter_hub.get_required_pipe` directly. It buys no closure property either, since `core.pipes` is not runtime-layer. **Either delete it** and put `get_required_pipe` back on `PipeLibraryAbstract` (smallest correct surface, consistent with the repo's no-speculative-additions rule), **or** keep it for symmetry with `ConceptProviderAbstract` and rewrite the docstring to say it is not consumed yet. Deleting also means dropping its subject grant.
- [ ] **A6 — doc/comment/CHANGELOG accuracy.** Five independent one-liners:
    - `pipelex/runtime_hub.py:9-11` forbids naming `core.concepts` and `core.pipes`, but `core.concepts` is a **declared runtime-layer package** and is in `runtime_hub`'s own closure — as line 415 of the same file says. Match the canonical doc: `core.bundles`, `core.interpreter`, and the Pipe-touching modules of `core.pipes`.
    - `pipelex/pipelex.py:122-124` claims RuntimeHub must be installed first because the scoping install *"needs a RuntimeHub already in place"*. It does not — `class_registry_scoping.install` lives in a module that imports nothing from `pipelex`, and `_resolve_scoped_class_registry` reads only the contextvar and the library manager, lazily. State the real reason (runtime is the lower layer, so it reads first) or drop the clause.
    - `CHANGELOG.md:8` maps `TextFormat` / `TemplatingStyle` / `TagStyle` to `pipelex.tools.templating`, whose `__init__.py` is **0 bytes**: `from pipelex.tools.templating import TextFormat` raises `ImportError`. Name the exact modules, as every other entry in the same sentence does. This is the artifact external consumers read.
    - `concept_provider_abstract.py:5` and `pipe_provider_abstract.py:8` still say *"stays high"* — the only two survivors of the low/high → runtime/interpreter vocabulary sweep.
    - `TODOS.md:339` and `:500-501` are off by one. Measured at HEAD: **269 modules / 20,305 SLOC** (claimed 268 / 20,304). The base and H-1 rows reproduce to the digit, so this is a stale re-take, not environment drift. The 0-interpreter-modules row is exact.
- [ ] **A7 — regenerate the stale error page.** `JobMetadataError` moved to `pipelex/system/exceptions.py`, but `docs/errors/job-metadata-error.md:16` still reports `pipelex.pipeline.exceptions`. It is the only stale page in the set, i.e. `make generate-error-pages` (alias `gep`) was never run in this PR. That page is the `type_uri` target users land on from a runtime error.
- [ ] **A8 — restate the class-registry leaf-import rule.** `docs/contribute/hub-layering.md:164` says to import `class_registry_access` directly *"only from inside `runtime_hub`'s import closure"* — but two of the three in-tree importers are **not** in that closure (`concept_factory.py` and `structure_generation/generator.py`; only `concept.py` is). The code is right and the rule is wrong: the real criterion is "a module that must stay import-light with respect to `runtime_hub` uses the leaf". As written the rule invites someone to "fix" `concept_factory.py` to import from `runtime_hub`, silently re-coupling `core.concepts` to the whole cogt/plugin stack. Nothing checks this mechanically.

> **CHECKPOINT A** — run `make agent-check`, then the full `make agent-test`, then `make drift-check` and ack the re-opened contract. Re-take the two `Measured after` tables in `TODOS.md` at that point rather than copying A6's numbers, since A1–A5 may move them. Push and let CI confirm before starting Phase B.
>
> ⚠ **A1 sub-step 1 makes the suite red on purpose.** Do not reach Checkpoint A with it reverted "to get green" — finish A1's sub-step 2 so the tree is green because the breach is fixed, not because the test was removed. If the remedy turns out to be bigger than this phase should carry, mark A1.2 as its own follow-up and leave the entry point in with an `xfail` that names this document, so the breach stays visible.

## Phase B — test hardening

Additive; safe to land in one commit after Checkpoint A. B1 and B2 are the two that pin things the current tests only *appear* to pin.

- [ ] **B1 — test the real teardown, not a simulation.** `tests/unit/pipelex/test_hub_lifecycle.py:70` calls `class_registry_scoping.reset()  # what Pipelex.teardown does`. Nothing pins that the production lines in `Pipelex.teardown` / `teardown_if_needed` do anything — delete them and the suite stays green, because a stale `_library_id` resolves to `None` and falls back to the global registry rather than raising. Add a real boot → pin a scoped library → `Pipelex.teardown()` → assert unscoped → fresh `Pipelex.make()` → assert the resolver is re-installed.
- [ ] **B2 — give the closure detector a negative control.** `_CLOSURE_SCRIPT` in `test_runtime_layer_import_closure.py` is a `textwrap.dedent` string, so no linter sees `INTERPRETER_PACKAGES` / `is_interpreter`; a typo makes all entry points pass vacuously, forever. The detector does work today (`pipelex.interpreter_hub` → exit 1, 51 modules; `pipelex.pipe_operators.func.pipe_func` → exit 1, 54), but nothing asserts that. Parametrize `(entry_point, expect_offender)` and include a known-dirty entry point asserting `returncode == 1`. [A1](#phase-a--in-pr-fixes) already added the `pipelex.plugins.discovery` entry point; this item adds the negative control on top, so the detector itself is pinned rather than only the property.
- [ ] **B3 — cover `check_hub_layering_cmd`.** Zero coverage today; both `sys.exit(1)` paths (violations found, scan root missing) and the quiet/panel split are untested. Asymmetric with the sibling guard, which has `test_check_keyword_only_cmd.py` and `test_check_keyword_only_cmd_fix.py`. Mirror those.
- [ ] **B4 — cover the guard's filesystem surface.** `collect_all_violations`, `iter_source_files`, and `module_qname_for`'s `__init__`-stripping branch have no test; every current test hands the guard a synthetic path string. Build a tmp tree in the style of `test_keyword_only_guard_single_file.py` (a violating runtime-layer module, a clean one, an `__init__.py`, a `__pycache__/x.py`).
- [ ] **B5 — test `concept_provider` as an actual injection.** All 75 test call sites pass the identical `get_concept_library()`, so the parameter is only ever proven *accepted*, never *consulted*. A "passed one and ignored it" regression would not fail anything. Pass a distinct stub (`mocker.Mock(spec=ConceptProviderAbstract)`) whose `is_compatible` selects a different arm, and assert it was called.
- [ ] **B6 — tighten the `TYPE_CHECKING` carve-out.** `_is_type_checking_test` matches `ast.Attribute(attr=attr)` without constraining the receiver, so `anything.TYPE_CHECKING:` grants the layer-rule exemption. Require the receiver to be `Name(id="typing")` and add a `not_typing.TYPE_CHECKING` case asserting a violation — or, if the looseness is deliberate, pin it with a test that says so.
- [ ] **B7 — bound the closure subprocess.** `subprocess.run` in `test_runtime_layer_import_closure.py:100` has no `timeout=`. Each case spawns a fresh interpreter importing heavy modules; a deadlock presents as a hung suite, which this repo has a documented history of (`docs/agents/debugging-hanging-pytest-runs.md`). Add `timeout=` and turn `TimeoutExpired` into a failure naming the entry point.

> **CHECKPOINT B** — run `make agent-check` and the full `make agent-test`. Nothing here re-opens a drift contract, so this is a plain commit. If A1 was closed properly, B2's negative control lands on an already-green tree and simply pins the detector; if A1.2 was deferred with an `xfail`, B2 must not remove it.

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
# F1 — a declared runtime-layer module reaching interpreter_hub transitively
for m in pipelex.plugins.direct.direct_plugin pipelex.plugins.discovery; do
  .venv/bin/python -c "
import sys, importlib
importlib.import_module('$m')
INTERP={'libraries','pipe_operators','pipe_controllers','codegen','builder'}
mods=[n for n in sys.modules if n.startswith('pipelex.')]
print('$m', 'interpreter_hub=', 'pipelex.interpreter_hub' in sys.modules,
      'interp=', len([n for n in mods if n.split('.')[1] in INTERP]))"
done
.venv/bin/pipelex-dev check-hub-layering --quiet   # still PASSED

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
