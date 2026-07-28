# Modularity refactors — implementation tracker

**Design doc:** [`wip/refactoring/modularity-refactors.md`](wip/refactoring/modularity-refactors.md) — the *why*, the rulings, the measurement snippets. This file is the *how*: ordered work, checkboxes, hard checkpoints.

**Worktree:** `_hub/` · **Branches:** `refactor/Modularity-3` (M3 + M1 + M2, pushed at `fa6f4fae9`) → `refactor/Modularity-4` (F1, local only) · **Base:** `refactor/Hub-2` (PR #1064, still open — see [Gating](#gating)) · **Status:** **F1 complete and reviewed three times — CHECKPOINT F1 cleared.** All four tracks reviewed and their fixes committed. Only Phase 5 remains.

**Reviewed 2026-07-27** (`/plan-eng-review`, 8 issues, all ruled). The review reversed **D-M1-2**, ruled **D-M1-4**/**D-M1-5**/**D-M1-6**, re-scoped **F1**, and corrected the cross-repo blast radius in both directions. The changes are folded in below; see [Review findings](#review-findings) for what moved and why.

Three tracks, ordered by dependency: **M3 → M1** (M3 is a prerequisite slice of M1), **M2** independent, then one small follow-up. Each track is its own PR.

---

## How to use this file

- Work top to bottom. Tick a box only when the thing is *done and verified*, not when it is written.
- **Checkpoints are hard stops.** At a `🛑 CHECKPOINT` you finish the phase, run the gates, update this file, fan out the reviews, and stop for the user. Do not start the next phase in the same session.
- The [Cold-start brief](#cold-start-brief) at the bottom is what a fresh session reads first. Keep it true.
- Measured numbers are recorded as of the date noted. Re-measure rather than trusting them; the *shape* (which modules, zero vs non-zero) is the criterion, not the absolute count.

---

## Gating

- [ ] **PR #1064 (`refactor/Hub-2`) is merged to `dev`.** All three tracks build on the F1 remedy (`pipelex/interpreter_plugins/`, the transitive guard rule). This branch is already based on it, so work can *start* before the merge — but no track may be opened as a PR against `dev` until #1064 lands, or the diff will carry #1064's changes.
- [ ] **PR topology — ruled 2026-07-27: three PRs, with M1 STACKED on M3.** The plan previously said both "M3 → M1" and "each track is based on #1064 and opened against `dev`", which cannot both be true. The topology is:

  ```
  #1064 (refactor/Hub-2)
    └─ M3 ─────────── PR → dev
        └─ M1 ─────── PR → M3   (retarget to dev once M3 merges)
    └─ M2 ─────────── PR → dev   (independent)
        └─ F1 ─────── PR → M2
  ```

  ⚠ **Superseded in practice by [D-M2-4](#decisions).** M3, M1 and M2 all landed as commits on `refactor/Modularity-3`, in that order. The prescribed *landing order* is what mattered and it is satisfied; splitting the branch into three PRs after the fact would re-create exactly the three-file conflict the topology existed to avoid. Open it as **one PR against `dev`** once #1064 merges (or split M3 off first if a smaller review is wanted — it is the only one of the three that is genuinely self-contained). F1 stays a separate PR on top, since it is the only behavior change in the track.

- [x] **Landing order is prescribed, not optional.** M1 and M2 both modify `hub_layering_guard.py`, `test_runtime_layer_import_closure.py` and `docs/contribute/hub-layering.md`. They are *architecturally* independent but **not operationally** independent — parallel branches conflict on those three files. Land M3 → M1 first, then rebase M2. ⚠ **A drift ack does not survive the rebase**: the digest reads the git index, so re-review and re-ack `hub-layering-convention` after rebasing M2.
  → **Resolved by construction (D-M2-4): M2 was built directly on top of M1 on this branch, not on a parallel branch.** The prescribed landing order is satisfied, the three-file conflict never arises, and the rebase-and-re-ack step disappears — the `hub-layering-convention` ack recorded at CHECKPOINT M2 is already against the final tree. The PR topology below collapses accordingly.
- [ ] **M2 is NOT release-gated.** Measured 2026-07-27 across every sibling repo: **zero** external consumers import `pipelex.plugins.<vendor>`. The "one breaking wave" argument covers M3 and M1 only. M2 may land whenever it is ready — it does not have to wait for the sweep, and its row comes out of the [Phase 5](#phase-5--close-out) table.

---

## Ground rules for every move

These are cross-cutting and each one has already been the cause of a confusing failure somewhere in this repo. Read them before the first `git mv`.

- [ ] **Re-path `subject_grants.toml` in the same commit as the move — and *before* running `make agent-check`.** Grants are keyed `<path>::<qualname>` and staleness is symmetric: a grant whose def moved **hard-fails** `check-keyword-only`. Worse, `make agent-check` runs `fix-keyword-only` *first*, which will silently rewrite the now-"ungranted" subjects to keyword-only — corrupting the diff. Order is always: `git mv` → rewrite grant paths → `make cko` (read-only, must be green) → then `make agent-check`.
  Measured grant hits by moving path (2026-07-27): `core/bundles` 6 · `core/interpreter` 15 · `core/pipes/pipe_abstract` 5 · `core/pipes/rendering` 15 · `core/pipes/pipe_factory` 0 · `core/registry_models` 0 · `plugins/` 160.
- [ ] **Regenerate error pages when an exceptions module moves.** `docs/errors/<slug>.md` carries a `Defined in | <module path>` row, so every moved error class churns its page. Verified: the page **filename and `type_uri` derive from the class name, not the module path** — so a pure move is URL-stable, and only a class *rename* changes a published `type_uri`. Run `make gep` after each move and inspect the diff.
- [ ] **Mirror the test tree in the same commit** — and **derive the list from each test module's actual subject, never from an inventory written in advance.** M1 proved this twice: the tracker's M1a and M1b test inventories were both materially incomplete. Grep each candidate for the source module it imports and route it by that. For M2: `tests/unit/pipelex/plugins/`, `tests/integration/pipelex/plugins/`.
- [ ] **Check every moved test for a path derived from its own depth.** `Path(__file__).parents[N]` silently resolves to a different directory after a move — no import rewrite, type checker or import-graph tool sees a parent count, and it fails only when the test runs. M1b hit exactly this. Re-anchor on a named directory (`next(p for p in Path(__file__).parents if p.name == "tests")`) rather than fixing the index.
- [ ] **`make cleanderived` after every batch of moves**, before running linters or pytest — stale `__pycache__` and collection state make the linters chase ghosts.
- [ ] **Rewrite imports by exact module path, never by prefix substring.** Two live traps:
  - `pipelex.plugins.secrets` (vendor dir) vs `pipelex.plugins.secrets_provider_registry` (mechanism module) — same for `storage`. A prefix `sed` corrupts the mechanism modules.
  - `pipelex.core.interpreter` (the package) vs `pipelex.interpreter_hub` / `interpreter_plugins` (unrelated). Anchor on `pipelex.core.interpreter.` and `pipelex.core.interpreter import`.
- [ ] **Rewrite string-literal module references too — they are not imports and nothing sees them.** `mocker.patch("pipelex.plugins.fal.fal_img_gen_worker.ImgGenArgsFactory.make_args_for_model")` is a module path that no import rewrite, no type checker, and no import-graph tool will touch. They fail loudly at test time, but only *after* the move, and a naive import-only rewrite turns the suite red in bulk. Measured 2026-07-27: **M2 = 189** literals, **M1 = 15** (the closure test's own config strings are among them). The `secrets` / `storage` ambiguity above is worse in string form — the sample includes `"pipelex.plugins.storage.storage_plugin..."`.
- [ ] **Use `git mv`** so history follows the file; do the import rewrite as a separate hunk in the same commit.
- [ ] **Sweep with `git grep` or `/usr/bin/grep`, never a bare `grep -r`.** This shell's `grep` is a **ugrep wrapper that honours `.gitignore`** — from the workspace root it silently skips every sibling repo, and inside `_hub` it skips the stale `site/` tree. It returns a *false clean* on exactly the completeness sweep a rename refactor depends on, and it fails silently by construction. Found during M2's review round; M2's own verdict survived re-verification only because the load-bearing pass happened to use `git grep`.
- [ ] **A brace-glob is a module reference no per-name regex will match.** `plugins/{google,openai}/*_img_gen_factory.py` names two modules and matches neither a `google` nor an `openai` substitution keyed on a single vendor. Same class of miss as a string literal, one level further out — and it survives into *unchecked plan items*, where it is worst, because those are instructions for work not yet done. Grep for the brace form explicitly before declaring a rename complete.
- [ ] **Every measurement/guard set is a matched set.** Whenever a module changes layer or package, four places must agree: `RUNTIME_LAYER_PACKAGES` (the guard), `INTERPRETER_PACKAGES` (the closure test), the `INTERPRETER` set in `docs/contribute/hub-layering.md`'s verification snippet, and the classification snippet's `I` in the design doc. Updating one and not the others makes a check pass vacuously.
  **Two of the four are now mechanically bound** (M1c): a test asserts the closure predicate and the doc snippet name the same packages, and two more assert that every entry in `RUNTIME_LAYER_PACKAGES` / `INTERPRETER_PACKAGES` resolves on disk — so a typo can no longer guard nothing. `INTERPRETER_CORE` / `INTERPRETER_CORE_EXCLUDED` are **gone**; do not re-add them. The design doc's copy stays manual (it lives in `wip/`, which is archived at track end).

---

## Phase 0 — baseline

Cheap, and it is what every exit criterion is measured against.

- [x] Confirm the tree is clean and gates are green *before* touching anything: `make agent-check`, `make agent-test`, `make drift-check`, `make chl`. — all green on `95a1e9bf7`.
- [x] Re-run the [core classification snippet](wip/refactoring/modularity-refactors.md#measurement) and paste the result into [Measurements](#measurements) below with today's date. — reproduced the [Measurements](#measurements) table exactly (97 / 51×3 / 33 / 30×4, same nine modules).
- [x] Note any drift from the design doc's numbers. **Known already:** re-measured on `bc30149c7` the counts are uniformly higher than the doc's (`registry_models` 97 vs 92, the 48s are 51, the 30 is 33, the 28s are 30). The *set of nine* modules and their ordering are unchanged, so the plan holds; only the absolute figures moved. — confirmed on `95a1e9bf7`; no further drift.
- Also baselined here because M3's exit criteria need them: **43** inverted `core → pipe_*` import statements (24 `registry_models` · 12 `pipelex_bundle_blueprint` · 4 `bundle_elaborator` · 2 `output_renderer` · 1 `pipe_abstract`).
- ⚠ **Gotcha, cost ~10 min:** `make cleanderived` deletes `tests/integration/pipelex/fixtures/_generated_model_sets.py`, which is gitignored but *not* regenerated by `agent-check` — only by the test targets. So the ground rules' "`cleanderived` before the linters" order makes pyright fail with 12 unrelated `reportMissingImports` in `model_selection.py`. Regenerate with `.venv/bin/pipelex-dev preprocess-test-models --generate-fixtures --profile ci` before re-running `agent-check`.

---

## M3 — split the boot manifest by layer

Removes core's fattest interpreter edge and seeds `pipe_machinery/`. Small, self-contained, no behavior change.

### Work

- [x] Create `pipelex/pipe_machinery/__init__.py` (empty, per repo convention).
- [x] Create `pipelex/pipe_machinery/registry_models.py` holding `PipeRegistryModels(RegistryModels)` with the six pipe lists: `PIPE_OPERATORS`, `PIPE_OPERATORS_FACTORY`, `PIPE_CONTROLLERS`, `PIPE_CONTROLLERS_FACTORY`, `PIPE_SIGNATURES`, `PIPE_SIGNATURES_FACTORY`, plus the ~24 `pipe_operators` / `pipe_controllers` / `pipe_signature` imports that come with them. — 24 imports, as measured.
- [x] Strip those six lists and their imports out of `pipelex/core/registry_models.py`. `CoreRegistryModels` keeps `STUFF`, `EXPERIMENTAL`, `FIELD_EXTRACTION` and the `core.stuffs` imports only. It should end up importing nothing from `pipe_operators` / `pipe_controllers` / `pipe_signature`, and no longer needing `PipeAbstractType` / `PipeFactoryProtocol` / `Any`. — all three dropped as predicted.
- [x] `pipelex/pipelex.py`: import both and register both — two adjacent `register_classes` lines. (`RegistryModels.get_all_models()` reflects over `dir(cls)` and dedups through a `set`, so the split is mechanical and double-registration is impossible.)
- [x] Add `"pipe_machinery"` to `INTERPRETER_PACKAGES` **and** drop `"pipelex.core.registry_models"` from `INTERPRETER_CORE` in `tests/unit/pipelex/test_runtime_layer_import_closure.py`. Do this in M3, not M1 — the moment an interpreter module lives under a new top-level package the predicate must count it, or the test under-counts silently. (The design doc puts this in M1 move 4; it belongs here for `pipe_machinery`, and in M1 for `mthds_parsing`.)
  Also **proved the new token is live**, rather than trusting `DIRTY_ENTRY_POINT` (which only proves *some* token matches): ran `_CLOSURE_SCRIPT` against `pipelex.pipe_machinery.registry_models` and asserted both that it exits 1 and that the offenders list contains a `pipe_machinery` module of its own. This is M1c's "one leaf probe per new package" step, done early for M3's token.
- [x] Update the guard's `RUNTIME_LAYER_PACKAGES` docstring where it enumerates `registry_models` as part of core's interpreter half (`hub_layering_guard.py` ~line 101). The declaration tuple itself does not change in M3.
- [x] `docs/contribute/hub-layering.md`: update the two places naming `core.registry_models` as Pipe machinery inside `core/` (~lines 111, 242).
  ⚠ **There were four, not two.** The drift review found two more, and they are the load-bearing ones: the *"`runtime_hub` must not name anything from …"* list under "Why the boundary exists" (line 80) and the **`INTERPRETER` set inside the page's own verification snippet** (line 91). Both enumerate the interpreter top-level packages, so both go stale on any new one — and a reader running the stale snippet measures zero interpreter modules and believes it. Expect the same pair in M1a (`mthds_parsing`). The tracker's grep for `registry_models` finds neither; grep for `interpreter_plugins` to find them.
- [x] Write the **registration-surface doc** — new page under `docs/contribute/`, registered in **two** places in `mkdocs.yml`: the `llmstxt-md` plugin's section list (~line 330) and the real `nav:` (~line 569). Missing the first one silently drops the page from `llms.txt`. Content: adding a pipe kind touches the kind's package, the type tag (`PipeType`/`PipeCategory`), the blueprint union in `core/bundles/pipelex_bundle_blueprint.py`, `PipeRegistryModels`, and the spec map (`builder/pipe/pipe_spec_map.py` + `pipe_spec_union.py`). Include the note that the spec-layer parallel in `builder/pipe/` is deliberate (see `pipelex/builder/CLAUDE.md`, spec vs blueprint), not duplication to collapse. — `docs/contribute/registration-surface.md`, both mkdocs registrations done.
- [x] **Not doing:** the `PipeBlueprintUnion` extraction (cut in design doc v2 — it would move twice, since M1 hoists `core/bundles/` wholesale). **Not doing:** moving `PipeType` / `PipeCategory` out of `core/pipes/pipe_blueprint.py` — measured 0, runtime-layer, stays in `core/` permanently (D-M1-2). — respected; note `PipeType`/`PipeCategory` move with `pipe_blueprint.py` in M1b under the *reversed* D-M1-2, so "stays in `core/` permanently" here is superseded by the reversal (see [Decisions](#decisions)).
- [x] **CRITICAL — regression test for the split registration.** Nothing in the suite asserts that pipe classes reach the class registry: `tests/unit/pipelex/test_hub_lifecycle.py:39-51` asserts hub singletons and scoping, and the class-registry tests use a synthetic `ScopedModel`. If either `register_classes` line is dropped or mis-wired, **boot still succeeds** and kajson deserialization of a pipe fails later, in production.
  **Assert the full set, not a sample.** One pipe + one stuff only catches a missing *whole* registration call — it cannot catch dropping one of the six lists, or one model out of a list, while hand-splitting `core/registry_models.py:53-93`. So: freeze the pre-split `CoreRegistryModels.get_all_models()` set, assert `CoreRegistryModels ∪ PipeRegistryModels` equals it exactly, **and** assert the two manifests are disjoint. That pins every model across the split and is the only new failure mode M3 introduces.
  → **`tests/unit/pipelex/test_registry_models_split.py`** (new module — the repo's one-TestClass-per-module rule rules out appending to `test_hub_lifecycle.py`, which T1 named). Three tests, and the third is the one T1's verify step is about: the frozen-set and disjointness assertions are computed *from the manifests* and would stay green if `Pipelex.make` never registered them, so a third test reads the **booted class registry** through `get_class_registry()`. **Both mutation checks run, both red as intended:** deleting the `PipeRegistryModels` `register_classes` line → *"booted class registry is missing 24 registered model(s)"*; deleting one model from `PIPE_OPERATORS` → set-equality failure *and* *"missing 1 registered model(s): ['PipeSearch']"*. The frozen set is 42 class names; names are unique, and the test asserts that too so the set comparison cannot lie.
- [x] **`make drift-ack CONTRACT=hub-layering-convention`.** M3 edits `hub_layering_guard.py` (the docstring above the tuple), which is a trigger file in `drift.toml:65-69` — so the contract opens and M3's checkpoint `make drift-check` fails without an ack. Review `docs/contribute/hub-layering.md` for real first: M3 moves the pipe manifest out of `core/`, which the doc describes in two places. Stage the trigger files before acking (the digest reads the git index).
- [x] Changelog entry under `[Unreleased] → ### Changed`, marked **breaking** (`CoreRegistryModels` no longer carries the pipe lists; `pipelex.pipe_machinery.registry_models.PipeRegistryModels` is new).
- [x] **Not in the plan, done anyway (matched-pair ground rule).** The design doc's classification snippet gained `"pipe_machinery"` in its `I` set — it is the *third* copy of the interpreter-package list, alongside the closure test's `INTERPRETER_PACKAGES` and the hub-layering page's `INTERPRETER`. The plan deferred this to M1 ("after M1, extend `I` with …"); leaving it would have made the design doc's own measurement under-count for the whole M3→M1 window. Snippet preamble now names all three copies explicitly so the next package cannot update one and miss two.
- [x] **Not in the plan, done anyway.** `tests/unit/pipelex/cli/dev/test_hub_layering_guard.py:52` asserted `not is_runtime_layer("pipelex.core.registry_models")` under the comment *"Everything that names a `Pipe` … stays in the interpreter layer"*. Post-M3 that module names no `Pipe`, so the assertion was still passing under a false rationale — it now belongs with `pipelex.core.qualified_ref` (undeclared because `pipelex.core` is not a declared package). Regrouped, and added `assert not is_runtime_layer("pipelex.pipe_machinery.registry_models")` for the new home. ⚠ This is the same test M1c rewrites wholesale (T5) — expect a conflict there and resolve in M1c's favour.

### Exit criteria

| | baseline | target | **actual** |
| --- | --- | --- | --- |
| interpreter modules loaded by `pipelex.core.registry_models` | 97 | **0** | ✅ **0** (and `hub=0`) |
| inverted `core → pipe_*` import statements | 43 | 19 | ✅ **19** |
| pipe-kind manifests filed inside `core/` | 2 | 1 | ✅ **1** (`PipeBlueprintUnion` only; it moves in M1a) |
| tests pinning pipe classes into the class registry | 0 | **1** | ✅ **1** module / 3 tests, all three mutation checks red |

> **On the "97 interpreter modules" framing.** `registry_models.py` is a boot-time composition manifest with exactly one consumer (`pipelex.py:500`) and it appears in no runtime entry-point closure — so the 97 is not a live problem, and M2's exit criteria explicitly bless the same shape (`builtins.py`, "by design"). M3's real justification is the *directory*: a pipe-kind manifest filed in `core/` makes `core` look like it depends on pipes. Do not oversell the metric in the PR description.

### 🛑 CHECKPOINT M3 — HARD STOP

1. **Gates** (in this order): `make cko` → `make cleanderived` → `make agent-check` → `make agent-test` → `make drift-check` → `make chl` → `make tb`.
2. **Verify:** re-run the core classification snippet; `pipelex.core.registry_models` must report `0 0`. Confirm the closure test still passes *and* that its `DIRTY_ENTRY_POINT` control still fails (it is what proves the predicate is live).
3. **Update this file:** tick the boxes, record measured actuals in [Measurements](#measurements), refresh the [Cold-start brief](#cold-start-brief), log any decision taken or question raised.
4. **Commit** the phase, then **fan out the reviews** per [Review fan-out protocol](#review-fan-out-protocol) with the commit SHA. M3 reviews: `correctness-and-boot` + `over-engineering`.
5. **Stop.** Report the review verdicts to the user and wait.

#### Review round — done 2026-07-27, fixes applied on Louis' call

`correctness-and-boot`: **no defects.** It re-derived the move independently (six lists byte-identical, both `register_classes` calls live, no other call-site rebuilds from `CoreRegistryModels` alone, no new cycle, no cross-repo consumer of the old path) and re-ran the gates itself.

`over-engineering`: **production change clean and load-bearing**; three defects, all in the new test module. All three confirmed against the code and fixed:

- **The frozen 42-name `PRE_SPLIT_REGISTERED_MODEL_NAMES` literal was spent scaffolding.** Its job — "nothing dropped while hand-splitting" — expired at commit time, after which it billed a hand-edit on every legitimate addition. Confirmed non-hypothetical: the registered-model set grew in each of the last four substantive commits to that file (#953, #1014, #1028, #1039). Replaced with a **derived structural invariant**: every pipe kind must declare the factory that `pipe_factory.py:121` will look up for it by string (`f"{pipe_type.value}Factory"`). That catches the realistic error (a half-dropped kind/factory pair), stays green on a deliberate removal of both halves, and needs no maintenance ever.
- **The disjointness assertion was redundant** with the name-collision check in the same module (`union` is a list concat, so `len(names) == len(union)` already fails on exactly that input) and guarded a runtime-harmless state. Dropped; the collision check was **kept and is load-bearing** — the registry is keyed by class name and kajson's `register_classes` skips a name it already holds.
- **The name-prefix assertions were tautological or wrong.** `all(startswith("Pipe"))` over the pipe manifest cannot fail; `not any(startswith("Pipe"))` over core encoded a layer heuristic our own [`hub-layering.md`](docs/contribute/hub-layering.md) contradicts — `PipeOutput` is **runtime-layer** ("reads as Pipe machinery but is not"), so registering it in `CoreRegistryModels` would be correct and would have tripped the assertion. Both dropped.

Two further items, one from each reviewer:

- **Module-level docstring** violated `pipelex/kit/agent_rules/pytest_standards.md:80` ("not on top of the file and not on top of the class"). Rewritten as a comment block — same rationale preserved, correct placement. (Both agents cited the rule as `.claude/rules/pytest-standards.md`, which does not exist; the kit file is the real one.)
- **The matched triple disagreed on `pipe_signature`** — present in the design doc's `I`, absent from the closure test's `INTERPRETER_PACKAGES` and `hub-layering.md`'s `INTERPRETER`. Pre-dates M3 (verified at `95a1e9bf7`), but this commit is the first to *write the invariant down*, so leaving it would have been dishonest. Added to both shipped copies after confirming `pipelex/pipe_signature/` is a real top-level package that imports `interpreter_hub` directly (`signature_walk.py:11`) and is loaded by **zero** of the closure test's runtime entry points — so the predicate got stricter with no red. The prose must-not-name list at `hub-layering.md` gained `pipe_signature` **and** `interpreter_plugins`, which it had also been missing. All three copies verified equal by script.

⚠ One reviewer claim was **wrong and rejected**: the `over-engineering` agent asserted the three copies were "correctly in sync". They were not — verified directly. It had also, in an earlier message, attributed conclusions to two sub-agents before hearing from them, and retracted that itself.

Mutation checks on the rewritten module, each red on exactly the intended test: drop a pipe kind → factory-pairing test; delete a `register_classes` line → liveness test (still caught, which is what made the derived rewrite safe); duplicate a class name across manifests → collision test.

**Gap noticed, deliberately not closed here — decide it in M1.** The `hub-layering-convention` drift contract triggers on `hub_layering_guard.py` + the two hub modules and reviews `hub-layering.md`. The closure test's `INTERPRETER_PACKAGES` is **not** a trigger, and `hub-layering.md`'s `INTERPRETER` snippet is the thing that drifted from it — so no contract binds the matched triple, which is exactly why the `pipe_signature` disagreement survived unnoticed. Adding the closure test as a trigger (or a contract binding the three copies) is a drift-registry decision, and M1 touches all three files anyway. Raised now so it is not rediscovered the hard way.

---

## M1 — make core's layer split physical

Hoists the eight interpreter-layer modules (plus four measured-zero leaf modules that move for cohesion) out of `core/` into two new packages, then collapses the guard declaration to a single entry. This is the big one — split into three commits.

### D-M1-4 — RULED 2026-07-27: rename, and treat it as a wire break

**Rename `PipelexInterpreterError` → `MthdsParserError`.** But the premise the original recommendation rested on was wrong. The plan said *"No external consumer imports `PipelexInterpreter`, so the class rename adds nothing to the sweep."* Measured — it is consumed in five repos, and four of them consume it **as a string, not an import**:

```
pipelex-temporal/pipelex_temporal/temporal_bundle_validator.py:26   from ... import PipelexInterpreter
mthds-starter-js/src/lib/errors.ts:176                              case "PipelexInterpreterError":
pipelex-starter-js/src/lib/errors.ts:257                            case "PipelexInterpreterError":
vscode-pipelex/.../cliValidationBackend.test.ts:99                  error_type: 'PipelexInterpreterError'
playroom/src/app/api/graph/route.ts:119                             message.includes("PipelexInterpreterError")
```

Those four TypeScript consumers branch on the class name as the `error_type` **wire value**. Renaming does not break their build — they silently stop matching and fall through to a generic error branch. This is the exact failure the guard's own docstring names: *a missed import is an ImportError, a missed string is not.*

- [x] Rename the class. `BundleElaboratorError` (its subclass) keeps its name.
- [x] Add the `mkdocs.yml` `redirect_maps` entry (`errors/pipelex-interpreter-error.md` → the new page) so the retired `type_uri` still resolves. Verified: the page filename and `type_uri` derive from the **class name**, not the module path (`docs/errors/pipelex-interpreter-error.md:18` carries `| Defined in | pipelex.core.interpreter.exceptions |` as a body row) — so the pure module moves are URL-stable and only this rename churns a URL.
- [x] Changelog: **wire-visible** break, not merely an import break. Name the `error_type` value change explicitly.
- [x] Carry all five repos into the [Phase 5](#phase-5--close-out) sweep table. The redirect fixes the human-facing docs link and does **nothing** for the four machine consumers — they need a coordinated string change.

### M1a — `pipelex/mthds_parsing/`

- [x] `git mv` into a new `pipelex/mthds_parsing/`: `core/interpreter/interpreter.py` → `parser.py`, `bundle_elaborator.py`, `helpers.py`, `validation_error_categorizer.py`, `core/bundles/pipe_sorter.py`, `pipelex_bundle_blueprint.py`.
- [x] **Create `pipelex/mthds_parsing/__init__.py` (empty).** Not optional: ruff runs `select = ["ALL"]` (`pyproject.toml:346`) and `INP001` is per-file-ignored **only** for `tests/**` (`:469`), so a source package without an `__init__.py` fails lint. M1a deletes two package initializers, so this is easy to miss.
- [x] **Add `"mthds_parsing"` to `INTERPRETER_PACKAGES` in THIS commit, not M1c**, and run the closure gate here. Between M1a and M1c the package would otherwise exist as an interpreter home that the predicate does not count — the merged exceptions module could enter a runtime closure with the test staying green. (The tracker previously deferred this to M1c.)
- [x] Merge `core/bundles/exceptions.py` + `core/interpreter/exceptions.py` into one `mthds_parsing/exceptions.py` (topical split only if a circular import forces it, per the error-class location convention).
- [x] Delete `core/bundles/` and `core/interpreter/` (including their empty `__init__.py`).
- [x] Rename the class `PipelexInterpreter` → `MthdsParser` across the tree (33 Python files, ~76 references incl. docs). Apply the D-M1-4 ruling to `PipelexInterpreterError`.
- [x] Rewrite importers. ⚠ **Do not work from a hand-written list** — the previous one was materially incomplete (26 importer files exist; it named ~11 and missed `builder/conventions.py`, `builder/operations/runner_code_ops.py`, `cli/bundle_target_resolution.py`, `language/mthds_schema_generator.py`, agent-CLI commands, …). Rewrite mechanically, then **assert zero surviving references to the old paths** — imports *and* string literals — as the completion check.
- [x] Move tests: `tests/unit/pipelex/core/{bundles,interpreter}/` → `tests/unit/pipelex/mthds_parsing/`.
- [x] **Re-path subject grants AND fix the embedded qualname.** `core/bundles` 6 + `core/interpreter` 15 hits — but `subject_grants.toml:2615` is `["pipelex/core/interpreter/interpreter.py::PipelexInterpreter.make_pipelex_bundle_blueprint"]`, which embeds the **renamed class**. Re-pathing alone leaves a stale grant that hard-fails `check-keyword-only`; the qualname must become `MthdsParser.make_pipelex_bundle_blueprint`. Then `make cko`.
- [x] `make gep` and inspect the `docs/errors/` diff (expect `Defined in` row churn; a filename/`type_uri` change only if D-M1-4 says rename).

### M1b — `pipelex/pipe_machinery/`

**D-M1-2 was REVERSED 2026-07-27** — see [Review findings](#review-findings). The original ruling classified modules by the measurement snippet, which counts **outbound** edges ("how many interpreter modules does X load?"). That answers "is X a leaf?", not "which layer owns X?". The layer question is **inbound: who needs this?** Under the inbound test, four more `core/pipes/` modules are interpreter-only and move with the rest:

| `core/pipes/` module | runtime-layer importers | verdict |
| --- | --- | --- |
| `pipe_output` | 4 | runtime — **stays** |
| `variable_multiplicity` | 5 | runtime — **stays** |
| `exceptions` | 1 | runtime — **stays** |
| `pipe_blueprint` | **0** | interpreter — **moves** |
| `validation` | **0** | interpreter — **moves** |
| `template_guard_lint` | **0** | interpreter — **moves** |
| `handle_pipe_errors` | **0** | interpreter — **moves** |

Every importer of `pipe_blueprint` is `pipe_operators/` (7), `pipe_controllers/` (4), `pipe_signature/` (2), `builder/` (4), `libraries/` (1), `pipeline/` (1), plus the four modules M1 already hoists. **Runtime genuinely does not know about pipes** — which is what the original rule of thumb said all along.

- [x] `git mv` into the package M3 created: `core/pipes/pipe_abstract.py`, `core/pipes/pipe_factory.py`, `core/pipes/rendering/` (both renderers + `__init__.py`), **plus `pipe_blueprint.py`** (D-M1-2 reversed).
- [x] Home the other three flagged modules. `validation.py` is imported by `pipe_blueprint` and `pipe_abstract` → `pipe_machinery/`. `template_guard_lint.py` is imported only by `pipe_operators/` + `pipe_controllers/` → `pipe_machinery/`. `handle_pipe_errors.py` is imported by `validation_error_categorizer` (going to `mthds_parsing/`) and `pipeline/validate_bundle.py` → **`mthds_parsing/`**. Verify each against the closure test after the move; the inbound test used *declared* runtime packages, and `pipeline/` / `pipe_run/` are undeclared straddlers.
- [x] Rewrite importers tree-wide (`pipe_abstract` is imported very widely — expect the largest single hunk of the track). Include the 15 string literals (ground rules).
- [x] Move tests. The previous inventory was incomplete; the actual set under `tests/unit/pipelex/core/pipes/` is `rendering/`, `test_pipe_abstract_namespace_strip.py`, `test_pipe_abstract_signature_surface.py`, `test_pipe_blueprint.py`, `test_pipe_blueprint_presence_markers.py`, `test_pipe_blueprint_signature_enums.py`, `test_validation.py` → **`pipe_machinery/`**; `test_handle_pipe_errors_suffix.py` → **`mthds_parsing/`** (it follows its module, not the package). Plus `tests/integration/pipelex/core/pipes/test_input_renderer_light_golden.py` → the integration mirror. Re-derive the list at move time rather than trusting this one.
- [x] Re-path subject grants (`core/pipes/pipe_abstract` 5 + `core/pipes/rendering` 15 hits, plus whatever the four newly-moved modules carry — re-measure), then `make cko`.
- [x] Confirm `core/pipes/` now holds exactly its runtime half: `inputs/`, `stuff_spec/`, `pipe_output.py`, `variable_multiplicity.py`, `exceptions.py`. **Do not** name the new package `pipelex/pipes/` — two `pipes` packages in adjacent layers would be actively confusing.

### M1c — collapse the declaration and the docs

- [x] Collapse `RUNTIME_LAYER_PACKAGES` in `pipelex/cli/dev_cli/commands/hub_layering_guard.py`: the six `pipelex.core.*` entries become the single `"pipelex.core"`. Rewrite the long `#:` note above the tuple (~lines 97-105) — it currently justifies the package-by-package listing, which no longer exists.
- [x] **Rewrite `test_core_is_split_between_the_layers` wholesale** in `tests/unit/pipelex/cli/dev/test_hub_layering_guard.py`. (The tracker previously pointed at line 52; that line asserts `pipelex.toolsmith.thing` and is unrelated.) The real block carries **six** core assertions, all of which invert or go stale — including `assert not is_runtime_layer(module_qname="pipelex.core.qualified_ref")`, commented *"the split is deliberate, not an omission"*, which is precisely what M1c reverses. The test's name and docstring become false too. Replace with a `test_core_is_wholly_runtime_layer` asserting the positive, and draw negatives from `mthds_parsing/` and `pipe_machinery/` so they assert the new boundary rather than the absence of the old one.
  ⚠ **Vacuous-green window.** `is_runtime_layer` is a pure string predicate over qnames — it never checks that a module exists. Between M1b and M1c, four of those assertions reference module paths that no longer exist **and keep passing**. Do the rewrite in the same commit as the collapse. (Standalone hardening deferred — see [Follow-ups](#follow-ups-from-the-review).)
- [x] Closure test (`test_runtime_layer_import_closure.py`): add `"mthds_parsing"` to `INTERPRETER_PACKAGES`; then **delete `INTERPRETER_CORE`, `INTERPRETER_CORE_EXCLUDED` and the `is_interpreter` branches that read them.** With D-M1-2 reversed and `pipe_blueprint` moving too, this is now correct **as stated** — nothing is left for them to name. (Under the *original* D-M1-2 it would have silently relaxed a live constraint: `hub-layering.md:220` says `pipe_blueprint` is the one entry not caught transitively, so it was the only name in the tuple doing real work. Reversing D-M1-2 is what makes the deletion honest.) Also update the module docstring's "two documented interpreter homes are deliberately absent" paragraph.
- [x] **Prove each new `INTERPRETER_PACKAGES` token is spelled right.** `DIRTY_ENTRY_POINT` only proves that *at least one* configured token matches — it imports `interpreter_hub`, whose closure contains several old interpreter packages, so a typo in `mthds_parsing`, `pipe_machinery` or `pipe_signature` leaves the suite green while that token guards nothing. The predicate lives inside a `textwrap.dedent` string, so nothing type-checks it. Add one leaf probe per new package (a case that must be flagged), or lift the predicate out of the embedded string and unit-test it directly.
- [x] **D-M1-6 — RULED: add `"pipe_signature"` to `INTERPRETER_PACKAGES`.** Verified 2026-07-27 against all five runtime entry points: **zero** `pipe_signature` modules loaded by any of them, so this is safe and surfaces no pre-existing leak. It is independent of the moves — pull it forward to Phase 0 or M3 if you want it out of M1c's diff.
- [x] **Verify the straddler did not become a failure.** `PipelexBundleBlueprintValidationErrorData` (moving into `mthds_parsing/exceptions.py`) is imported by `pipeline/` and `libraries/`. Measured 2026-07-27: **no runtime-layer entry point currently loads it** — `runtime_hub`, `plugins.builtins` and `content_generator` pull in only `pipelex.pipeline` + `pipeline.pipeline_models` — so the deleted exclusion should cost nothing. If the closure test *does* fail on it, do **not** re-add an exclusion: move the data class to a runtime-layer home instead, and record the decision here.
- [x] **Spec + conformance, in this same change.** `conformance/tests/pipelex_transport/test_data.py:45` pins `("pipelex.core.pipes.pipe_abstract", "PipeAbstract", "class")` in `ALLOWED_SURFACE` — an active, unskipped test — and `docs/specs/pipelex-transport-boundary.md:133` names the same path. Workspace CLAUDE.md requires both sides to change with the code, and `make check-spec-links` gates it. ⚠ `_hub`'s `make agent-test` **structurally cannot catch this** — different repo. Also check `docs/specs/pipelex-transport-boundary.md:164` (`pipelex.plugins.orchestrator_registry` — survives M2, it is a mechanism module) and `docs/specs/pipelex-mthds-protocol.md:47` (`PipelexBundleBlueprint` — class name unchanged, path only).
- [x] `docs/contribute/hub-layering.md`: (a) **keep the rule of thumb as written** — *"if it names a `Pipe`, it belongs to the interpreter layer"* (line 115) is correct, and was only slated for rewrite to accommodate the `pipe_blueprint` misclassification that D-M1-2's reversal removes; (b) delete the `core.pipes.pipe_output` carve-out paragraph (line 110) — the collapsed declaration now covers it; (c) **rewrite line 220's predicate paragraph** — it justifies naming core's Pipe-machinery modules one by one and singles out `pipe_blueprint`; both disappear (this target was missing from the tracker); (d) update the Known-inversions (line 242) and "Where core splits" (line 111) sections for the new package names; (e) update line 80's `runtime_hub` must-not-name list.
- [x] Update the classification snippet in `wip/refactoring/modularity-refactors.md` → Measurement (`I` gains `mthds_parsing`, `pipe_machinery`) so the design doc does not go stale.
- [x] `make drift-plan` → the `hub-layering-convention` contract triggers on `hub_layering_guard.py`; review the doc for real, `git add` the trigger files, then `make drift-ack CONTRACT=hub-layering-convention RATIONALE="…"`.
- [x] Changelog entry, **breaking**: the two new packages, the class rename, and the `type_uri` change if D-M1-4 says rename.

### Exit criteria

| | baseline | target | **actual** |
| --- | --- | --- | --- |
| `RUNTIME_LAYER_PACKAGES` entries naming `pipelex.core.*` | 6 | **1** (`pipelex.core`) | ✅ **1** |
| `core` modules loading > 0 interpreter modules | 9 (8 after M3) | **0** | ✅ **0** (4 after M1a, 0 after M1b) |
| `core/pipes/` modules with 0 runtime-layer importers (inbound test) | 4 | **0** | ✅ **0** — what remains scores 4 / 5 / 1 |
| doc carve-outs for `core.pipes.pipe_output` | 1 | 0 | ✅ **0** |
| inverted `core → pipe_*` import statements | 19 (after M3) | **0** | ✅ **0** (3 after M1a) |
| `INTERPRETER_CORE` / `INTERPRETER_CORE_EXCLUDED` entries | 7 / 2 | **deleted** | ✅ **deleted** — `EXCLUDED` in M1a, `CORE` in M1b |

### 🛑 CHECKPOINT M1 — HARD STOP

1. **Gates:** `make cko` → `make cleanderived` → `make agent-check` → `make agent-test` → `make drift-check` → `make chl` → `make gep` (diff must be reviewed, not just generated).
2. **Verify:** re-run the classification snippet with the extended set — every remaining `pipelex.core.*` module reports `0 0`. **Re-run the inbound test too** (see [Measurements](#measurements)) — every module left in `core/pipes/` must have ≥1 runtime-layer importer. `make chl` passes with the collapsed declaration *and* the transitive rule reports zero breaching runtime-layer modules. Closure test green including the dirty control.
3. **Cross-repo gate (cannot be run from `_hub`):** in the `conformance/` repo, update `ALLOWED_SURFACE` and `docs/specs/pipelex-transport-boundary.md`, then run `make check-spec-links`. This is a hard checkpoint item, not sweep work.
4. **Update this file** + [Cold-start brief](#cold-start-brief) + [Measurements](#measurements).
5. **Commit**, then **fan out reviews** with the commit range. M1 reviews: `correctness-and-imports` + `boundary-and-naming` + `over-engineering` + `test-and-docs-sync`.
6. **Stop.** Report verdicts and wait.

#### Checkpoint record — reached 2026-07-27, commits `0f0309b8f` · `c9c45c475` · `10080cf26`

**All gates green** at `10080cf26`: `cko`, `cleanderived` + fixture regen, `agent-check` (ruff / pyright 0 / mypy 0 / cko / chl), full `agent-test`, `drift-check`, `chl`, `gep` (no churn — no error class moved in M1b/M1c), `tb`. Every exit-criterion actual is in the table above.

**Decisions taken during implementation** (each one the plan authorized in advance):

- **D-M1-8 — `PipelexBundleBlueprintValidationErrorData` moved to `pipelex.core.exceptions`, not into `mthds_parsing/`.** M1c's plan said to verify the straddler "did not become a failure" and, if it did, to move the data class to a runtime-layer home rather than re-add an exclusion. It did: the claim "no runtime-layer entry point currently loads it" was wrong — `pipelex.core.memory.working_memory_factory` reaches it, and the closure test's own docstring said so all along (`core.bundles.exceptions` was in `INTERPRETER_CORE_EXCLUDED` precisely because it lands in every runtime closure). Moved to `core/exceptions.py`, which already holds the two sibling structured error-data models it shares `PipeValidationErrorType` with. That is what let `INTERPRETER_CORE_EXCLUDED` be deleted outright in M1a instead of being carried forward.
- **`INTERPRETER_CORE` deleted in M1b, not M1c.** M1b is the commit that empties it; leaving a four-entry tuple whose comment says "not under a top-level package of its own" for one commit would have been the exact "passing under a false rationale" shape M3's review flagged.
- **Test moves were re-derived, and the tracker's inventory was again incomplete** — it missed `test_execution_data_coverage.py`, `test_pipe_validate_before_run.py`, `test_run_pipe_tracer_metadata.py` and `test_inputs_template_toml.py`. Derived instead from each module's actual subject (grep each test for the `core.pipes.*` module it imports).
- **`tests/unit/pipelex/core/test_data/` stays put.** It is a shared MTHDS corpus consumed from `tests/integration/pipelex/language/` as well as by the parser tests, so it is not a mirror of a source module. Noted rather than silently left.

**The one real bug the move introduced, and nothing static could have caught it.** `tests/integration/.../test_input_renderer_light_golden.py` derived its fixture paths from `Path(__file__).parents[4]`. Moving it one level shallower silently repointed that at the repo root, and it failed only in the full suite — no import rewrite, type checker or import-graph tool sees a parent count. Re-anchored on `tests/` **by name**; every other moved test was then swept for the same shape (none had it). Worth carrying into M2: a depth index is a module-location dependency that looks like a constant.

**Cross-repo gate (item 3) — done, and it reports more than M1 caused.** `conformance/tests/pipelex_transport/test_data.py` and `docs/specs/pipelex-transport-boundary.md` now pin `pipelex.pipe_machinery.pipe_abstract`; `make check-spec-links` passes. Running the transport arm against this branch (`CONFORMANCE_PIPELEX_PYTHON=_hub/.venv/bin/python`) then reports two failures, and the split matters:

- **7 provider-side symbols missing — all pre-existing**, none touched by M1: `pipelex.hub.*` (5, retired by the hub split) plus `pipelex.pipeline.job_metadata.JobMetadata` and `pipelex.graph.trace_context.TraceContext` (moved by the Phase 3 type moves). `ALLOWED_SURFACE` is stale w.r.t. two *earlier* tracks. This is release-gated sweep debt that predates M1 and should be folded into the same wave.
- **1 consumer-side hit — M1-caused and working as designed**: `pipelex-transport/pipelex_transport/primitives/pipe_classification.py` still imports `pipelex.core.pipes.pipe_abstract`. The deny-by-default AST scan is pointing at the Phase 5 sweep item. **Deliberately not fixed here** — `pipelex-transport` pins a *released* `pipelex`, so changing it now breaks it immediately; it lands with the wave.

⚠ **Both cross-repo edits are left UNCOMMITTED in their own repos** (`conformance/` on `dev`, workspace-root `docs/specs/`), one line each. Committing them to `dev` would break those repos against the released `pipelex` before the wave lands. Whoever runs the sweep must pick them up.

**Two follow-ups closed early, both mutation-checked.** T10 (guard against vacuously-green string-predicate tests) is **done**, in the form the plan preferred: `RUNTIME_LAYER_PACKAGES` entries and `INTERPRETER_PACKAGES` tokens must each resolve on disk. And the gap M3's checkpoint flagged as "no contract binds the matched triple" is now bound by a test rather than a drift contract — the closure predicate and `hub-layering.md`'s snippet must name the same set. ⚠ **The design doc's third copy is deliberately not asserted**, since `wip/` is archived at track end; it stays a manual concern for M2, which adds no interpreter package and so should not disturb it.

#### Review round — done 2026-07-28, fixes applied

Four reviews over `6d5b9418a..a23c1b70b`. **All four cleared the moves themselves**, each by measurement rather than reading: every module under the three packages imports cleanly, the only module-level cycle in `pipelex/` (`core.stuffs.stuff` ↔ `stuff_artefact`) is unchanged and untouched, `pipelex/core/**` holds zero imports of any interpreter package, and the collapse to one `pipelex.core` entry *widens* enforcement — `core.exceptions`, `core.registry_models`, `core.qualified_ref` and bare `core.pipes` were previously undeclared and unchecked. The D-M1-8 placement was tested skeptically and stands: 6 of 9 runtime entry points transitively load `pipeline.exceptions`, so filing the straddler with the parser would have broken the property for real.

**Every defect was documentation, fixture or test-quality drift — none in the moves.** All confirmed against the code before fixing.

- **The user-facing regression, and the one no gate could catch.** `_SUBSYSTEM_SECTIONS` in `pipelex/errors/error_pages_generator.py` never got an `mthds_parsing` row. `_subsystem_key` reads the module's *second segment*, so the rename silently reclassified both parser errors through `_FALLBACK_MACRO_SLUG` — the two errors a method author hits most moved from **Authoring & language** to **Platform & tooling**. Fixed with the missing row. ⚠ **The lesson is about the check, not the row:** `make gep` reporting "no diff" was read as evidence the rename propagated, and it is not — it proves committed matches generated, and the pages matched *because* they baked in the wrong fallback. The generator is deliberately built so a missing curation entry still renders rather than failing. **Read the generated diff, never just the exit code.**
- **A wire-visible brand defect the rename introduced.** `title()` auto-derives from the class name, so `MthdsParserError` published the RFC 7807 title `"Mthds parser"` — the standard's brand, mis-cased, on every error report. Fixed with `_declared_title = "MTHDS parser"`. The five error-report fixtures that paired the new `error_type` with the retired `title`/`type_uri` are corrected, and the identity triple is now **pinned by a test** (`test_mthds_parser_error_identity_is_pinned`) — nothing asserted it before, which is exactly how the fixtures came to carry a shape the class cannot produce.
- **An overclaim I wrote into the M1c rewrite.** "Every `pipelex.core.*` module loads zero interpreter modules" is false as stated: `core.pipes.pipe_output` loads `pipeline.pipeline_models`, and `runtime_hub` also loads `pipe_run.pipe_run_mode`. It holds only under the closure predicate's deliberate `pipeline`/`pipe_run` carve-out — which line 228 of the same page states plainly. The base commit had said the honest opposite at that spot. Qualified in all four places the property is stated. See [deferred follow-ups](wip/refactoring/deferred-placement-follow-ups.md) §3: the caveat now repeats in four places, which is itself the argument for moving those two leaves.
- **Eighteen assertions carrying three bits.** The two guard tests M1c rewrote were an *inventory*, not an invariant: with `pipelex.core` a single prefix entry, any string under it is True and any string under `pipe_machinery.`/`mthds_parsing.` is False, invented names included. This repeats the defect M3's own review round found and recorded as a lesson. Replaced with derived invariants: `pipelex.core` is declared with **no** `pipelex.core.*` sub-entry (re-splitting core fails), and `RUNTIME_LAYER_PACKAGES` ∩ `INTERPRETER_PACKAGES` = ∅ — which also binds two declarations maintained in separate modules and never previously compared.
- **The regex scraper was self-inflicted.** `INTERPRETER_PACKAGES` lived inside the `textwrap.dedent` string, which is what forced a regex to read it back and was the stated justification for the new tests. Hoisted to a real module-level constant handed to the subprocess **as argv** — no interpolation, no scraper, names now lint-visible. Mutation-checked that the argv path is load-bearing: emptying the set makes the negative control fail.
- **`parents[5]`, and why it was worse than a style point.** `test_hub_layering_guard.py` validated the declaration against `Path(__file__).resolve().parents[5] / "pipelex"` while the sibling test added in the *same commit* carries a comment condemning depth indices. Not merely fragile: `parents[6]` is the workspace root, which holds a sibling `pipelex/` checkout — so a module moved one level shallower would validate a **different repo** and pass. Re-anchored on `tests/` by name.
- **Stale prose, all fixed:** `runtime_hub.py`'s "one rule" docstring (still forbade two deleted packages, omitted the four current ones — and it is a declared trigger of the drift contract whose ack reviewed only the doc copy); `hub-layering.md` placing the renderers in `core/pipes/rendering/` in the present tense, plus the paragraph arguing for that regrouping; two adjacent paragraphs on the same premise reaching opposite conclusions; the closure test's own entry-point and `pipe_machinery` comments; `handle_pipe_errors.py` citing a now-sibling module; the blueprint-location enumeration in the kit rules source and `builder/CLAUDE.md`; `tests/CLAUDE.md` missing rows; the CHANGELOG naming a package deleted later in the same unreleased cycle.

**Deferred, not fixed** — placement and naming accuracy, no silent bug, recorded in [`wip/refactoring/deferred-placement-follow-ups.md`](wip/refactoring/deferred-placement-follow-ups.md): three modules in `mthds_parsing/` that are not parsing (`pipe_sorter`, the generic half of `helpers`, `handle_pipe_errors`); the parser fixture corpus still filed under `tests/unit/pipelex/core/`; and the `pipeline`/`pipe_run` leaf leak. `pipe_machinery/` was checked module by module and is accurately named throughout.

**Fixed in passing** (pre-existing, same class): `tests/CLAUDE.md` had no row for `pipelex/codegen/` or `pipelex/pipe_signature/` either.

---

## M2 — separate the plugin mechanism from the vendor adapters

`pipelex/plugins/` is two things under one name: the mechanism (17 top-level modules) and the built-in vendor adapters (17 directories). Splitting them makes the one-way dependency visible: adapters → mechanism, engine → mechanism, mechanism → nothing.

### Work

- [x] **Create `pipelex/providers/__init__.py` (empty)** — same `INP001` reason as `mthds_parsing/` (ruff `select = ["ALL"]`, tests-only exemption). The commit fails lint without it.
- [x] `git mv` the 17 vendor directories to a new `pipelex/providers/`: `anthropic`, `azure_rest`, `bedrock`, `blackboxai`, `docling`, `fal`, `gateway`, `google`, `huggingface`, `linkup`, `mistral`, `openai`, `openrouter`, `portkey`, `pypdfium2`, `secrets`, `storage`. (D-M2-1: `providers/` over `backends/` — `backends/` would collide with `pipelex/cogt/model_backends/`, and the code's own vocabulary for the non-inference adapters is already "provider": `secrets_provider_registry`, `storage_provider_registry`.)
- [x] `pipelex/plugins/` keeps the mechanism only: `contract.py`, `registrar.py`, `discovery.py`, `exceptions.py`, the seven `*_registry.py`, `model_handle.py`, `sdk_client_registry.py`, `sdk_client_manager.py`, `backend_extras_factory.py`.
- [x] `builtins.py` follows the vendors → `pipelex/providers/builtins.py`, still exporting `RUNTIME_BUILTIN_PLUGINS` / `RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES`. Re-point the downward import in `pipelex/interpreter_plugins/builtins.py`. Both stay parameters of `build_registrar` — unchanged.
- [x] Rewrite imports. **Watch the `secrets` / `storage` trap** (ground rules): `pipelex.plugins.secrets` is a vendor dir, `pipelex.plugins.secrets_provider_registry` is a mechanism module that must not move. Same for `storage`.
- [x] **Rewrite the 189 string-literal module references** (ground rules) — `mocker.patch("pipelex.plugins.<vendor>...")` targets, invisible to import rewrites and to pyright. They fail loudly at test time, so `make agent-test` is the gate, but budget them as real work: an import-only rewrite turns the suite red in bulk and reads as a catastrophic move rather than expected residue.
- [x] **Add `"pipelex.providers"` to `RUNTIME_LAYER_PACKAGES`, and add a guard test that proves it.** This is the one step where a mistake is invisible — dropping the vendors from the guard silently un-declares the largest runtime package.
  ⚠ **The plan previously claimed "the transitive rule is what catches it." That is backwards.** Verified at `pipelex/cli/dev_cli/commands/hub_layering_guard.py:677`: the rule iterates `sorted(module for module in reaching if is_runtime_layer(module_qname=module))`. An **undeclared** package is excluded from the rule's domain, so omitting it makes the guard go *quieter*, not louder. **No existing gate catches this.** Add an explicit assertion to `tests/unit/pipelex/cli/dev/test_hub_layering_guard.py` that a representative `pipelex.providers.*` module `is_runtime_layer`.
- [x] Add `pipelex/providers/builtins.py` to the closure test's `RUNTIME_LAYER_ENTRY_POINTS` (replacing `pipelex.plugins.builtins`, which after the move no longer aggregates anything). Its presence there is load-bearing history: that module and three neighbours breached the boundary transitively while both gates stayed green.
- [x] Move tests: `tests/unit/pipelex/plugins/` and `tests/integration/pipelex/plugins/` — split so vendor tests land under a `providers/` mirror and mechanism tests stay under `plugins/`.
- [x] Re-path subject grants (160 hits under `plugins/` — the bulk are vendor workers), then `make cko`.
- [x] `make gep` — several vendor directories carry exceptions modules (`gateway`, `portkey`, `bedrock`, `google`, `mistral`, `openai`, …), so expect a wide `Defined in` diff. Filenames and `type_uri`s must be **unchanged** (no class renames in M2); if one changes, something got renamed by accident.
- [x] Docs sweep for `pipelex/plugins/<vendor>/` paths: `docs/under-the-hood/reasoning-controls.md` (a table of ~10 paths), `error-model.md` (3 refs to `pipelex/plugins/*/`), `inference-backend-plugins.md`, `secrets-provider-plugins.md`, `orchestrator-plugins.md`. **Do not touch the entry-point group name** `"pipelex.plugins"` — it is a group identifier, not a module path, and it is the third-party contract.
- [x] **Sweep architectural prose in *source*, not just `docs/`.** Two module docstrings describe the pre-M2 layout and go stale silently: `pipelex/plugins/contract.py:33-35` ("``pipelex.plugins`` for the runtime half, ``pipelex.interpreter_plugins`` for the interpreter half" — after M2 the runtime *adapters* are in `pipelex.providers`), and `pipelex/interpreter_plugins/builtins.py:3-8` (describes `pipelex.plugins` as the neighbouring runtime adapter package). Both are the kind of comment the repo's own diagram-maintenance rule says must move with the code.
- [x] `docs/contribute/hub-layering.md` → **Known inversions**: record the four `cogt → provider config` imports (`anthropic`, `google`, `mistral`, `openai` config classes reached from `cogt/config_cogt.py`) as a deliberate, documented exception. Rationale (D-M2-2): the main config model is statically typed end-to-end (`configs.py` ⇄ `pipelex.toml` structural sync); making vendor config sections plugin-contributed would trade that static typing for a dynamic registry.
- [x] **`make drift-ack CONTRACT=hub-layering-convention`.** M2 adds `pipelex.providers` to `RUNTIME_LAYER_PACKAGES`, a trigger file in `drift.toml:65-69`, so the contract opens and M2's checkpoint `make drift-check` fails without an ack. Review the doc for real — M2 adds a whole runtime-layer package, which the "Where core splits" and Known-inversions sections both describe.
- [x] Changelog entry, **breaking**: `pipelex.plugins.<vendor>` → `pipelex.providers.<vendor>`. Two things to state explicitly: (a) the *plugin entry-point contract is unaffected* — an external plugin imports `pipelex.plugins.contract` / `pipelex.plugins.registrar`, both of which stay put; (b) **no known external consumer imports the vendor paths** (measured 2026-07-27: zero hits across every sibling repo), so the break is in-tree only. Do not imply a consumer migration that nobody needs.

### Exit criteria

| | baseline | target | **actual** |
| --- | --- | --- | --- |
| mechanism modules importing a vendor | 1 (`builtins.py`, by design) | **0 in `plugins/`**, 1 in `providers/` | ✅ **0 / 1** — `providers/builtins.py` names all 17, nothing under `pipelex/plugins/` names any |
| vendor modules importing outside `providers/` + `plugins/` | 0 | 0 (unchanged) | ✅ **0** |
| guard test asserting `pipelex.providers.*` is runtime-layer | 0 | **1** | ✅ **1**, derived from disk and mutation-checked red |
| `cogt → <specific vendor>` statements | 7 | 7 (4 documented, 2 in F1, 1 self-resolving) | ✅ **7**, and they are the *only* three source files outside `providers/` naming a vendor |
| `RUNTIME_LAYER_PACKAGES` covers every vendor module | yes | yes | ✅ **17 / 17** |

⚠ **Measurement trap, cost ~10 min and it under-counted silently.** `pypdfium2` contains a digit, so a `[a-z_]*` character class in a grep pattern skips it — the first pass reported 16 of 17 vendor imports in `builtins.py` and would have reported a clean `cogt` count even if a `pypdfium2` import existed. Use `[a-z0-9_]+` for anything matching a vendor segment. The *rewrite* script was never at risk (it uses literal vendor names), only the measurements taken afterwards — which is the worse of the two, because a measurement is what tells you the rewrite was complete.

> **The "vendor imports nothing but the mechanism" metric was false by construction** and is restated above. The design doc deliberately preserves cross-vendor edges (`blackboxai` / `openrouter` / `portkey` → `openai`; `gateway` → `fal` / `google` / `openai` / `portkey`) because they stay inside the new package — e.g. `blackboxai/blackboxai_completions_factory.py:9` and `openrouter/openrouter_completions_factory.py:8` import `OpenAICompletionsFactory` at module level. A metric targeting zero could never be met. Measure "imports outside `providers/` **and** `plugins/`" instead.

### 🛑 CHECKPOINT M2 — HARD STOP

1. **Gates:** `make cko` → `make cleanderived` → `make agent-check` → `make agent-test` → `make drift-check` → `make chl` → `make gep` (review the diff).
2. **Verify:** transitive layering rule reports zero breaching runtime-layer modules; closure test reports zero interpreter modules for every runtime entry point *including the new `providers.builtins`*; the dirty control still fails.
3. **Update this file** + [Cold-start brief](#cold-start-brief) + [Measurements](#measurements).
4. **Commit**, then **fan out reviews**. M2 reviews: `correctness-and-imports` + `boundary-and-naming` + `over-engineering`.
5. **Stop.** Report verdicts and wait.

#### Checkpoint record — reached 2026-07-28

**All gates green**: `cko`, `cleanderived` + fixture regen, `agent-check` (ruff / pyright 0 / mypy 0 / cko / chl), full `agent-test`, `drift-check` (two contracts acked), `chl`, `gep` (diff reviewed, see below), `tb`. Every exit-criterion actual is in the table above.

**Scale of the move:** 17 vendor packages + `builtins.py` out of `pipelex/plugins/`; **1364 substitutions across 136 files**, of which **191 were string literals** (the plan predicted 189 — the drift is two, both in test mock targets). The completion check was the one that makes "did I get them all?" answerable: grep the whole tree for the old paths and assert the only survivors are in the deliberately excluded files (`CHANGELOG.md`, `TODOS.md`, `wip/`, `docs/errors/` — history and generated pages, which must not be textually rewritten; the error pages are regenerated by `make gep` instead).

**The `secrets` / `storage` trap was real and was avoided by construction.** Every substitution anchors the vendor name on a `(?![A-Za-z0-9_])` lookahead, so `plugins.secrets` (vendor dir) rewrites while `plugins.secrets_provider_registry` (mechanism module) does not. Verified after the fact by asserting that no mechanism module is reachable at a `pipelex.providers.*` path, and that the `pipelex.plugins` **entry-point group name** — a group identifier, not a module path, and the third-party contract — is untouched.

**Decisions taken during implementation:**

- **D-M2-4 — M2 was built on top of M1 on this branch, not on a parallel branch off #1064.** The plan's topology had M2 independent and rebased after M1, with a mandatory drift re-ack because a rebase invalidates the digest. Building it stacked satisfies the prescribed landing order, eliminates the three-file conflict the plan warned about, and makes the ack recorded here final. See [Gating](#gating).
- **Test split derived per module, not from the plan's two-line instruction.** The vendor subdirectories were unambiguous, but the flat modules needed reading. `test_linkup_plugin_guard.py`, `test_secrets_plugin.py` and `test_storage_plugin.py` are *vendor* tests despite sitting at the `plugins/` root (they moved into the matching `providers/<vendor>/` mirrors); `test_transport_retry_wiring.py` and `test_plugin_pipelex_storage_images.py` are cross-vendor and moved to the `providers/` root; `test_inference_backend_coverage.py` reads as a vendor test by name but is a *mechanism* round-trip over `BUILTIN_PLUGINS` and stayed. On the integration side `conftest.py` moved with the four vendor tests, because all four of its consumers moved and the three modules that stayed use none of it.
- **`tests/CLAUDE.md` gained a `pipelex/providers/` row.** The source-to-test mapping is 1:1 by convention; a new source package with no row silently drops out of every targeted test run.

**The one user-facing defect, and it is the same shape M1 hit three weeks ago.** `_SUBSYSTEM_SECTIONS` in `pipelex/errors/error_pages_generator.py` had a `plugins` row and no `providers` row. `_subsystem_key` reads a module's **second dotted segment**, so every vendor error class would have silently reclassified out of *Inference & providers* into the `_FALLBACK_MACRO_SLUG` (*Platform & tooling*) — with `make gep` exiting 0 and producing an entirely plausible diff. This is M1's `mthds_parsing` regression repeating on the next module move, and it was caught **only** because M1's recorded lesson was to read the generated diff rather than trust the exit code. Fixed by splitting the row in two, which the content wanted anyway: **Provider adapters** (a vendor SDK rejected the call) and **Plugin system** (a plugin failed to load or claimed a taken slot). Verified by the negative: `docs/errors/platform-and-tooling.md` is byte-identical, so nothing fell through. No page was added or removed, so no `type_uri` changed.

**Two drift contracts opened, not one.** `hub-layering-convention` was predicted. `config-docs` was not — re-pathing the four vendor config imports touches `cogt/config_cogt.py`, a trigger. Reviewed for real and logged as **friction**: `docs/configuration/` cites no Python import path anywhere, so an import-only diff cannot affect it *by construction*. That is the second such opening on that contract from a pure refactor sweep, and the dogfood log now carries a concrete narrowing proposal (ignore diffs confined to import statements) backed by two data points.

#### Review round — done 2026-07-28, fixes applied

Three reviews over `7beda698f..dee323e28`. **All three cleared the move itself, by measurement rather than reading.** The `correctness-and-imports` pass found **no import defect at all**: it AST-walked every `.py` under `pipelex/` and `tests/`, resolved all 944 `pipelex.`-prefixed string constants against the live interpreter (which covers every `mocker.patch` target), imported all 111 modules under `pipelex.providers` in one process, and confirmed that importing the entire `pipelex.plugins` mechanism pulls in **zero** `providers` modules — so the one-way dependency is empirically true, not merely asserted. `boundary-and-naming` independently verified the same and confirmed the "omitting the entry makes the guard quieter, not louder" premise by monkeypatching the tuple and watching the guard report zero violations either way.

**Every defect was in the documentation of the boundary, or in the test that guards it. None in the move.**

- **The new guard test repeated a defect this track has now made three times.** `is_runtime_layer` matches by dotted prefix, so reading the vendor list off disk and looping over it carried exactly one bit — `is_runtime_layer("pipelex.providers.totally_invented.x")` is `True`, the assert fires on the first entry, and the remaining iterations can never execute. Two reviewers flagged it, and both correctly noted the test must **not** be deleted: it is the only thing in the suite that catches a dropped declaration, because the guard CLI itself stays green. The clincher is that `test_core_is_declared_as_one_whole_package`, which M1c added *to this same file*, has a docstring condemning precisely this shape. Replaced with a membership assertion over **both** halves of the split — which is strictly stronger than what it replaced (dropping `pipelex.plugins` now fails too, where the disk-scan version only caught `pipelex.providers`), carries two bits instead of one, and drops a real second failure mode the reviewers spotted: an adapter added without an `__init__.py` is importable as a namespace package but was silently skipped by the filter. Both mutations checked red.
- **A boundary claim my own commit contradicted two sections later.** "Where the built-in plugins split" asserted the one-way dependency as three clauses, and the third — *"the engine depends only on the mechanism"* — is false: importing `cogt.config_cogt` alone loads **8** `pipelex.providers.*` modules, which the Known-inversions bullet added in the *same commit* documents and justifies. One document, two opposite claims about the same word. This is the identical shape M1's review found ("two adjacent paragraphs on the same premise reaching opposite conclusions"), and it is the worst defect of the round: a layering page that states the boundary wrongly is more harmful than one that omits it. Clause dropped and scoped explicitly to the two packages, with a pointer to the inversions.
- **"One directory per vendor" is wrong twice over.** `providers/secrets/` registers the built-in `env` backend — no vendor exists — and `providers/storage/` registers local, in-memory, S3 and GCP behind a single directory; in both cases only the registration shim moved, the implementations are under `pipelex/tools/`. The package *name* survives this (all three reviewers agree `providers` is right, and it is exactly why `vendors/` would have been wrong), but the prose overreached. Corrected, and the exception is now stated rather than glossed.
- **Hardcoded counts, flagged independently by all three reviewers**, against an explicit workspace rule ("Never hardcode counts… they create diff churn, go stale silently, and add no value"). Four live locations pinned "seventeen" / "the seven capability registries". The irony was pointed out and is fair: the neighbouring test went out of its way to avoid becoming an inventory while the prose beside it hardcoded the number. Fixed. Left alone deliberately: the same words inside the recorded drift-ack rationales and the dogfood log, which are append-only records of a decision at a point in time — rewriting them would falsify the record.
- **Two unchecked F1 items named paths M2 had moved** (`plugins/{google,openai}/*_img_gen_factory.py`). Completed items' historical references are correct as written; it is specifically the open ones that must name the current tree, because F1 is the next work on this branch and this file is its handoff. Fixed.

**One reviewer claim was wrong and is rejected:** `correctness-and-imports` reported a fifth hardcoded count at `hub_layering_guard.py:114`. There is no numeral in that file — verified by grep. The other four locations it named were correct.

**Two method findings worth more than the defects.**

- **This shell's `grep` is a ugrep wrapper that honours `.gitignore`.** Run from the workspace root it silently skips every sibling repo; inside `_hub` it skips the stale `site/` tree. A naive `grep -r` therefore returns a **false clean** on exactly the sweep a rename refactor depends on. The whole-tree completion check was re-run with `/usr/bin/grep` and the verdict held — but it held by luck of using `git grep` for the load-bearing pass, not by design. **Use `/usr/bin/grep` or `git grep` for any completeness sweep.**
- **A brace-glob evades a per-vendor regex.** `plugins/{google,openai}/` is a real module reference that no substitution keyed on a single vendor name will match — it is the same class of miss as a string literal, one level further out. Worth adding to the ground rules before the release-wave sweep; the same shape exists in a `pipelex-api/wip/` note.

**Reported and not reproduced:** one reviewer saw the new guard test fail once in five full-suite runs, with `is_runtime_layer` returning `False` for a module the committed tuple covers — impossible against this tree, and the run carried the `bringing up nodes...`-twice signature that `docs/agents/debugging-hanging-pytest-runs.md` names as xdist worker crash-and-replace. Re-run 25 times under xdist after the rewrite: **zero failures**. The rewritten test no longer touches the filesystem, which removes one of the two moving parts. Recorded as an unreproduced observation rather than closed — if it recurs it needs root-causing, not tolerating.

**Not done here, deliberately:** the `wip/` docs that still describe the pre-M2 layout (`wip/plugins/*.md`, the design doc's own prose) were excluded from the rewrite along with `CHANGELOG.md` and `TODOS.md`, per M1's method. The design doc's classification snippet needs **no** change — M2 adds a runtime-layer package, not an interpreter one, so the matched triple is undisturbed.

---

## Follow-up F1 — the two `cogt → vendor` img-gen factory imports behind a registry

Deliberately **not** inside the 127-file M2 move: this is a behavior change and would be invisible in that diff (D-M2-2).

**Re-scoped 2026-07-27 from three imports to two.** Two corrections:

1. **`backend_factory.py:53` (VertexAI) is dropped.** VertexAI support is being removed, so the edge self-resolves. Do not build auth-dispatch machinery for a vendor on its way out — it would outlive its reason. The import is already deferred (`# noqa: PLC0415`), so it costs nothing while it remains.
2. **No registry. There is no dispatch key.** The first review proposed an arg-builder slot on `inference_backend_registry`; the outside voice showed that cannot work, and it is verified:
   - `ImgGenArgsFactory.make_args_for_model(cls, model_rules, *, img_gen_job, nb_images, model_id, model_name)` — **receives no `sdk`** (`img_gen_args_factory.py:54-62`).
   - Dispatch is a `match` over **`AspectRatioTaxonomy`**, not over a provider (`img_gen_args_factory.py:367-396`): `GPT_IMAGE_LEGACY` / `GPT_IMAGE_2` → `OpenAIImgGenFactory.size_for_*`, `GEMINI_*` → `GoogleImgGenFactory.resolve_image_config`, `QWEN_IMAGE` → …
   - The gateway worker is **one SDK that executes both** OpenAI and Google taxonomies (`gateway_img_gen_worker.py:78-84`), so an `(family, sdk)` key cannot select the right helper at all.

**Ruled: move the helpers, do not dispatch them.** Extract the OpenAI/Google taxonomy and geometry helpers into a **neutral mapping module under `cogt/img_gen/`**, then have both `ImgGenArgsFactory` and the provider workers import *inward*. These are taxonomy utilities keyed by a `cogt`-owned enum — they were never independently dispatched workers.

- [x] Extract the taxonomy/geometry helpers from `providers/google/google_img_gen_factory.py` and `providers/openai/openai_img_gen_factory.py` into a neutral `cogt/img_gen/` mapping module. (Both re-pathed by M2 — F1 is unstarted work, so its paths must name the current tree.) — **two** modules, not one (D-F1-1): `cogt/img_gen/img_gen_gemini_mapping.py` + `cogt/img_gen/img_gen_gpt_mapping.py`.
- [x] Re-point `img_gen_args_factory.py:37-38` (currently **module-level**, not deferred) and the provider workers to import inward from it. Net import-cost improvement: removes two eager vendor imports from a `cogt` module. — done; the inward importers are `providers/google/google_img_gen_worker.py` and `providers/gateway/gateway_factory.py`.
- [x] Tests covering each taxonomy branch, including the unmapped-taxonomy path. — the branch coverage already existed and moved with the module (`test_img_gen_gemini_mapping.py`, incl. the non-Gemini-taxonomy rejection; the GPT-Image branches are covered from the args-factory side). What was **missing** is the invariant F1 actually buys, added as `test_img_gen_mapping_neutrality.py` (D-F1-4).
- [x] Changelog entry.
- [x] Leave `backend_factory.py:53` alone; re-check after VertexAI removal lands. — untouched; it is now the *only* remaining `cogt → specific vendor` edge of this kind.

**Why this beats the registry**, recorded so it is not re-litigated: no hub wiring, no registrar menu entry, and therefore **no plugin-API version bump**. `plugins/contract.py:5-19` uses strict coarse API equality and explicitly versions registrar changes, so adding a menu capability would force a coordinated plugin wave — for two import sites. It also fixes the dependency *direction* rather than routing it through machinery, and it leaves `pipelex.plugins.contract` untouched, which is what M2's changelog promises.

### Exit criteria

| | baseline | target | **actual** |
| --- | --- | --- | --- |
| `cogt → specific vendor` import statements | 7 | **5** (4 config + 1 deferred VertexAI) | ✅ **5** |
| source files outside `providers/` naming a vendor module | 3 | **2** | ✅ **2** (`config_cogt.py`, `backend_factory.py`) |
| eager vendor imports in `cogt/img_gen/` | 2 | **0** | ✅ **0** |
| third-party imports in the mapping modules | 1 (`openai`) | **0** | ✅ **0**, and pinned by a test |
| tests pinning the neutrality of the new home | 0 | **1** | ✅ **1** module / 2 tests, both mutation-checked red |

### 🛑 CHECKPOINT F1 — HARD STOP

Gates as above (this one *does* change behavior, so `make agent-test` is the real gate, not a formality). Reviews: `correctness-and-boot` + `over-engineering`. Then stop.

#### Checkpoint record — reached 2026-07-28

**All gates green**: `cko`, `cleanderived` + fixture regen, `agent-check` (ruff / pyright 0 / mypy 0 / cko / chl), full `agent-test`, `drift-check`, `chl`, `gep` (diff reviewed — empty, and *verified* empty rather than assumed: no error class moved, and `cogt` already had its `_SUBSYSTEM_SECTIONS` row, so the M1/M2 regression shape could not repeat here), `tb`.

**Scale:** 2 source modules + 1 test module moved, 127 substitutions across 11 files plus the durations file. Same rewrite method as M1/M2 (ordered longest-first substitutions over `git ls-files`, `CHANGELOG.md` / `TODOS.md` / `wip/` / `docs/errors/` excluded, then a whole-tree `git grep` completion check asserting the only survivors are in those excluded files). ⚠ `.test_durations` is **not** an exclusion — M1 and M2 both rewrote it, and it carries test node ids that a test move invalidates.

**One near-miss the completion sweep caught by construction:** `OpenAIImageURL` is a live local alias for the OpenAI SDK's `ImageURL` in four completions factories. A substitution keyed on `OpenAIImage` would have corrupted all four; the list keys on the full type names (`OpenAIImageLegacySizeType`, `OpenAIImageModerationType`, `OpenAIImageInputFidelityType`), so none matched. Verified after the fact — the four sites are untouched.

**Decisions taken during implementation** — see [Decisions](#decisions) for D-F1-1 … D-F1-4.

#### Review round — done 2026-07-28, fixes applied

`correctness-and-boot`: **no defects.** It reconstructed both pre-move files, applied only the documented renames, and diffed against the new ones — the **entire** functional delta is `moderation_literal`'s `omit` → `None`, everything else being docstrings. It then traced every consumer of that value and confirmed the branch is identical (`Omit` is not a `str`, so the old `isinstance` test and the new `is None` test agree on every input), verified all three `mocker.patch` targets followed the class, confirmed no orphan `.test_durations` entries, and recomputed the neutrality property independently — 43 modules in the mapping closure, zero `pipelex.providers`, zero `pipelex.config`, no deferred or dynamic import anywhere in it. It also confirmed boot is untouched: the moved modules are lookup tables, present in no manifest and no entry point.

⚠ **Its one unreproduced observation has a mundane explanation, and it is reassuring rather than worrying.** It saw the closure subprocess fail exactly once, reporting **10** `pipelex.providers` modules, and could not reproduce it in 8 further full-suite runs or 15 standalone ones. Ten is the exact count [Measurements](#post-f1-measured-2026-07-28) records for the deliberate mutation used to prove the guard discriminates — so the reviewer observed that mutation in flight, in a shared worktree, and what it actually witnessed is the guard firing correctly on a genuinely coupled tree. Its suggested hardening (`-I` plus explicit `cwd=`/`env=`) is **not applied**: cwd on `sys.path[0]` is what makes the subprocess measure the *working tree* rather than an installed copy, and the sibling `test_runtime_layer_import_closure.py` is built the same way. Recorded rather than silently dismissed — if it ever appears with no concurrent editing, that reasoning is what to re-examine.

`over-engineering`: **the move itself is clean and not over-engineered** — verified as a pure placement fix with no registry, no plugin slot, no dispatch layer and no shim, and the `omit` → `None` change *removes* machinery rather than adding it. The equivalence was confirmed independently rather than taken on trust (the old caller never put the sentinel in the dict either, and the worker reads the key's absence). Grants correctly re-pathed; `bc22ba934` verified a pure re-sort by identical line multiset.

**Every defect was in the new guard test, and the headline one is this track's own recurring shape — a check that cannot fail.**

- **`assert MAPPING_MODULE_PATHS` sat at the top of a test parametrized over that same list, so it was unreachable.** pytest never calls a body for an empty parameter set: it reports `SKIPPED [1] got empty parameter set` and exits 0. Verified directly with a throwaway repro against this venv rather than taken on the reviewer's word. The line therefore could not catch the one failure it named — a stale glob turning the check into a silent green skip — and **D-F1-4's written justification for the glob was false as a result**. The sibling assertion in the *non*-parametrized test is reachable and does the job for real, so the fix is a deletion, not an addition: the dead assert goes, the third copy of the same check inside `_CLOSURE_SCRIPT` goes with it (its only caller is already gated by the reachable one), and the surviving guard now carries a comment explaining why it cannot live in the parametrized sibling. Mutation-checked: with the glob pointed at a non-matching pattern the module reports **1 failed, 1 skipped** — loud, which is the whole point.
- **Kept the glob, against the reviewer's preferred fix.** Replacing it with a two-item literal would retire all three vacuity checks at once, which is true and tempting. But the glob is the only thing that covers a third taxonomy family on the day it lands, and this invariant is invisible to every other gate in the repo (D-F1-4) — a new mapping module silently outside the check is a worse failure than one reachable assertion is a cost. One reachable guard, one line of cost.
- **Duplicated closure machinery with `test_runtime_layer_import_closure.py`: judged, not drifted.** The reviewer is right that this branch's M1/M2 rounds were about killing near-duplicate guard mechanics, so it deserved a ruling rather than silence. Ruling: **keep them separate.** After the deletions above the shared surface is a ten-line script, a timeout constant and one `subprocess.run` — and the two guards must be able to diverge (the closure test's detector is parameterized by interpreter packages passed as argv and carries a dirty-control entry point; this one has a fixed prefix and no entry-point list). Extracting a helper would couple them to save less than it costs.
- **Stale grant rationale fixed** — `input_fidelity_literal` still read *"Derives the OpenAI fidelity literal"* after the de-vendoring rename D-F1-2 motivated. Re-recorded through `make sgr` so the registry stays machine-written and sorted.
- **Stale tense in this file fixed** — the re-sort was still described as pending future work inside the very range that landed it.

**An overclaim I caught while verifying one of the reviewer's "cleared" items, and it is the M2 shape again.** My own docstring, changelog entry and `hub-layering.md` bullet all said the GPT Image family is "served by three different SDKs (OpenAI, Azure REST, the Pipelex gateway)". The shipped decks prove **two** — `openai.toml` and `azure_openai.toml` are the only ones declaring a `gpt_image_*` taxonomy. The gateway *worker* is genuinely written for these models (it routes through the same args factory and carries the OpenAI `/images/generations` → `/images/edits` split), but its catalog is fetched remotely, so no shipped config settles it. The two proven adapters already defeat "file it in the OpenAI adapter", so the argument never needed the third. Reworded in all three places to what the config proves. ⚠ The reviewer had marked this claim *checked and accurate*; a reviewer confirming a claim is not the same as the claim being verifiable from the tree.

**One finding confirmed against the code and rejected:** the `"not supported by OpenAI image model '<name>'"` error strings. They name the *model the user chose*, which is an OpenAI model whichever SDK routes to it — Azure and the gateway serve OpenAI's models, they do not make them theirs. The module docstring's neutrality claim is about the *mapping*, not the model, so the two do not contradict. Rewriting them would churn several test `match=` patterns to make the messages less accurate.

**Fixed alongside, in its own commit** — `subject_grants.toml` had stopped being sorted by key, which its own documentation calls an invariant (`docs/contribute/keyword-only-arguments.md:37`: *"machine-written and sorted by key, so diffs stay stable and merge conflicts resolve trivially"*). Measured 11 out-of-order pairs; F1 contributed 2 of them and **M1 and M2 the rest** — a bulk path rewrite re-paths a grant key without moving its block, and `check-keyword-only` does not gate order, so the invariant broke silently and stayed broken across three commits. Kept out of F1's diff as branch debt rather than F1 debt: it is `bc22ba934`, a pure reordering (304 insertions against 304 deletions, with the key set, every `param` and every `rationale` asserted unchanged before writing).

#### Third review round — `/review`, done 2026-07-28

Run against `origin/refactor/Modularity-3` (the F1-only diff), after the two agent rounds above. **No correctness defect.** The move is complete and the consumer set closes: enumerating every pre-move reference to the two classes and their six type aliases at the base yields exactly the sites F1 touched, with no survivor anywhere in the tree outside `CHANGELOG.md` / `TODOS.md` / `wip/`. The `omit` → `None` equivalence re-verified independently (`Omit`/`omit` now appear nowhere in `pipelex/`; the only reader of the `moderation` key is `openai_img_gen_worker.py:78`, which pops it). The neutrality property re-measured in a fresh interpreter: **0** `pipelex.providers` modules and **0** vendor-SDK roots in the mapping closure. Gates re-run green: `cko`, `agent-check` (ruff / pyright 0 / mypy 0 / cko / chl), `drift-check`, `tb`, full `agent-test`. Codex, given the same scoped diff adversarially, returned **no findings** and reproduced the closure measurement itself.

Five items, none critical. Three fixed mechanically, two ruled by Louis:

- **The corrected three-SDK claim survived in a fourth copy, and it was inside the very test that pins the property.** `test_img_gen_mapping_neutrality.py`'s header said *"GPT Image by the OpenAI, Azure REST and gateway workers"* — the exact wording `fd141d4ed` set out to retire from the docstring, the changelog and `hub-layering.md`. Same matched-set failure as `pipe_signature` in M3 and the four-not-two occurrences in M3's doc sweep: the sweep found the three copies someone had listed, not the copies that exist. Reworded to what the decks prove (re-verified: `openai.toml` and `azure_openai.toml` are still the only two declaring a `gpt_image*` taxonomy).
- **Two subject-grant rationales describe an operand that is not the granted param.** `ImgGenGeminiMapping.img_gen_taxonomy` and `.optional_img_gen_taxonomy` grant `param = "inference_model"` but read *"Operates on the aspect-ratio taxonomy"* — copied from the seven siblings that really do take `taxonomy`. Pre-existing (identical at the base), but this round's own fix list already re-recorded `input_fidelity_literal` for exactly this defect and stopped at one. Re-recorded both through `make sgr`; sort invariant re-asserted over all keys.
- **A comprehension variable shadowed the parameter interpolated two lines below it.** `img_gen_gpt_mapping.py:89` built its "supported aspect ratios" list with `for aspect_ratio in …` while `aspect_ratio` is the function's own parameter, used at line 91 in the error message. Correct only because comprehensions carry their own scope — and the sibling builder at line 120 already names it `supported_ratio`. Renamed to match. Pre-existing, moved unchanged.
- **`.test_durations` carried 112 orphan entries and `test_parser.py`'s 54 tests had none — M1 debt, fixed here in its own commit.** The ground rules call `.test_durations` a non-exclusion precisely because a test move invalidates its node ids, but M1's rewrite re-pathed *directories* and missed *basename renames*: `test_interpreter.py` → `test_parser.py` (52 entries), `test_interpreter_preliminary_text.py` → `test_parser_preliminary_text.py`, plus the renderer moves into `pipe_machinery/rendering/`, `test_job_metadata_request_id.py` into `system/`, and `test_hub_class_registry.py` → `test_class_registry_scoping.py`. Nothing gated it: the file is generated, pytest-split silently treats an unknown node id as average duration, so the only symptom was CI shard imbalance. Reconciled against a full unfiltered `--collect-only` (`-m ""` — the marker filter in `addopts` hides ~312 items and would have "orphaned" every `e2e` entry), matching each dead id to a live one by its `Class::test` tail: **125 remapped, 0 ambiguous, 0 dropped.** The two surviving dead ids are `pipe_img_gen` parametrizations keyed on the generated model-set fixture, so they are profile-dependent rather than orphaned, and were left alone. ⚠ **This is a third instance of the same shape** (`subject_grants.toml` order, the matched triple, now durations): a *generated or bookkeeping* file that no gate validates, broken by a bulk rewrite, invisible until someone measures it.
- **The test module that still named the vendor is renamed.** `test_img_gen_args_openai_sizes.py` / `TestImgGenArgsOpenAISizes` → `test_img_gen_args_gpt_sizes.py` / `TestImgGenArgsGptSizes`. It exercises `AspectRatioTaxonomy.GPT_IMAGE_2` / `GPT_IMAGE_LEGACY` and patches `pipelex.cogt.img_gen.img_gen_gpt_mapping.log`, so it was the last "OpenAI" that D-F1-2 should have taken. (`test_safety_openai_moderation_mapping` keeps its name — `SafetyCheckerTaxonomy.OPENAI_MODERATION` is a real enum member.) Its 13 durations entries were re-pathed in the same reconciliation.

**One gap recorded, deliberately not closed** — see [Follow-ups from the review](#follow-ups-from-the-review): the neutrality guard is weaker than its comment claims in two ways. The AST check reads only the mapping modules' *own* import statements and the closure check counts only `pipelex.providers`, so a vendor SDK reached **transitively** through another `pipelex.cogt` module passes both. Unexercised today — measured **zero** vendor-SDK imports anywhere in `pipelex/` outside `providers/`, which is the stronger invariant and is itself unguarded. And `_MAPPING_DIR.glob("img_gen_*_mapping.py")` is non-recursive and name-keyed, so *"a third taxonomy family is covered the day it lands"* holds only for a family landing in that exact directory under that exact suffix. Both are cheap to close and neither is worth the machinery F1 exists to avoid; recorded so the claim is not mistaken for a proof.

---

## Phase 5 — close out

- [ ] Verify the three (or one) PRs are open against `dev` with #1064 merged first.
- [ ] Write the **cross-repo sweep handoff** into `wip/refactoring/` — the sweep is release-gated and shared with the hub split, the Phase 3 type moves, and the `interpreter_plugins` relocation. It must land as **one breaking wave**, not four. Known external hits:

  **Re-measured 2026-07-27 across every repo in the workspace.** The previous table was materially incomplete — it named one repo; there are eight. It also called `pipelex-temporal` "private and unchecked" when it is checked out at the workspace root and carries the most hits of any consumer.

  | repo | hits | what |
  | --- | --- | --- |
  | `pipelex-temporal` | **13** | `PipelexInterpreter` (class, 3 files) · `PipeAbstract` · `PipeFactory` · `PipelexInterpreterError` in a comment |
  | `pipelex-api` | 5 | `PipelexBundleBlueprint` · `PipeAbstract` · `PipelexBundleBlueprintValidationErrorData` |
  | `pipelex-transport` | 3 | `PipeAbstract` (`primitives/pipe_classification.py` + 2 tests) — **was missing from the table entirely** |
  | `mthds-starter-js` | 2 | `"PipelexInterpreterError"` — **wire string**, `src/lib/errors.ts:176` + test |
  | `pipelex-starter-js` | 2 | `"PipelexInterpreterError"` — **wire string**, `src/lib/errors.ts:257` + test |
  | `conformance` | 1 | `ALLOWED_SURFACE` pin — **handled at CHECKPOINT M1, not here** |
  | `vscode-pipelex` | 1 | `error_type: 'PipelexInterpreterError'` — **wire string** |
  | `playroom` | 1 | `message.includes("PipelexInterpreterError")` — **wire string** |

  **The four wire-string consumers are the dangerous ones**: they branch on the error class name as an `error_type` value, so the rename does not break their build — they silently fall through to a generic error branch. No Python grep or type checker finds them.

  Verified clean for the M1 module set: `pipelex-cookbook`, `cocode`, `pipelex-mistralai-workflows`, `pipelex-worker`, `pipelex-starter-python`, `pipelex-relay`, `sandbox`, `pipelex-daytona-sandbox` (it imports `pipelex.plugins.contract` / `registrar`, which do not move). **M2 and F1 contribute nothing to this sweep** — zero external consumers import `pipelex.plugins.<vendor>`, and zero import either img-gen mapping under any name (re-measured across every repo at F1 time; the only hit anywhere is the released `pipelex/` checkout itself). No kajson-registered class moves, so serialized payloads are untouched.

- [ ] **Fix the workspace repo table first.** `pipelex-transport` and `pipelex-daytona-sandbox` are real consumer repos missing from the workspace-root `CLAUDE.md` table — which is the table every cross-repo sweep is built from, and the reason `pipelex-transport` was missed here. Add both (and audit for others) before the sweep runs.
- [ ] Archive this tracker to `wip/refactoring/` when the track completes (repo convention — see how `wip/hub/hub-split-tracker.md` was handled).
- [ ] Update the memory entry `project_modularity_refactors.md`.

---

## Review fan-out protocol

At every checkpoint, spawn the reviews **in parallel, in one message**, each as a **fresh sub-agent with no inherited context**. Hand each one *only* a pointer to the changes — never this plan, never the design doc, never the rationale, never your own conclusions. A reviewer that has read the justification cannot independently find the flaw in it.

Prompt template (fill the bracketed parts, change nothing else):

> Run the `/code-review` skill on the following changes in the repo at `/Users/lchoquel/repos/Pipelex/_hub`:
> `[git diff <base>..<sha>` — or the list of unstaged files]
>
> Focus dimension: **[dimension]**.
>
> We want clean, solid software — not over-engineering. Report concrete defects with file:line, and say plainly if you find none. Do not propose speculative features or abstractions.

Dimensions to draw from:

| dimension | what the reviewer is asked to hunt |
| --- | --- |
| `correctness-and-imports` | broken/circular imports, a moved symbol whose importers were missed, a rewrite that hit the wrong module (`plugins.secrets` vs `secrets_provider_registry`), test files left behind their source |
| `correctness-and-boot` | behavior change hiding in a mechanical move; boot-sequence registration correct and complete |
| `boundary-and-naming` | does the new package boundary actually hold, or did the move just relabel the problem? are the names right for what is inside them? |
| `over-engineering` | anything introduced that is not load-bearing: speculative abstraction, indirection with one caller, a guard entry that guards nothing, machinery kept alive after its reason expired |
| `test-and-docs-sync` | guard config / closure-test predicate / design-doc snippet in agreement; docs describing the old tree; a check that now passes vacuously |

**Reading the verdicts:** treat a finding as a real defect only after you confirm it against the code. Reviewers with no context will sometimes flag an intentional ruling from the [Decisions](#decisions) table as a bug — that is expected and is not a reason to reverse the ruling; note it and move on. Design tradeoffs that are not silent bugs get captured as deferred follow-ups in `wip/refactoring/`, not reflexively fixed.

---

## Decisions

Inherited from the design doc (already ruled — do not re-litigate):

| id | ruling |
| --- | --- |
| **D-M1-1** | Pipe manifest → `pipelex/pipe_machinery/registry_models.py` as `PipeRegistryModels`; M3 creates the package, M1 fills it |
| **D-M1-3** | `core/interpreter/` + `core/bundles/` → `pipelex/mthds_parsing/`; `PipelexInterpreter` → `MthdsParser` |
| **D-M2-1** | Vendors → `pipelex/providers/`, flat, no capability nesting |

Ruled during the **2026-07-27 review**:

| id | ruling | why |
| --- | --- | --- |
| **D-M1-2** | ~~`pipe_blueprint.py` is runtime and stays in `core/`~~ → **REVERSED. It is interpreter-layer and moves**, along with `validation.py`, `template_guard_lint.py` and `handle_pipe_errors.py` | The measurement snippet counts **outbound** edges, which answers "is X a leaf?" not "which layer owns X?". The layer question is **inbound**: zero declared runtime-layer modules import any of these four. Runtime does not know about pipes |
| **D-M1-4** | **Rename** `PipelexInterpreterError` → `MthdsParserError`, add the `redirect_maps` entry, and carry **five** repos into the sweep | The premise "no external consumer imports `PipelexInterpreter`" was false; four TS repos consume it as an `error_type` **wire string**, which the redirect does not help |
| **D-M1-5** | **Delete** `INTERPRETER_CORE` / `INTERPRETER_CORE_EXCLUDED` and their `is_interpreter` branches | Correct *because* D-M1-2 was reversed. Under the original ruling this would have silently relaxed the one entry `hub-layering.md:220` calls load-bearing |
| **D-M1-6** | **Add** `"pipe_signature"` to `INTERPRETER_PACKAGES` | Verified against all five runtime entry points: zero `pipe_signature` modules loaded. Safe, no pre-existing leak, and independent of the moves |
| **D-M2-2** | The four `cogt` config imports: accepted + documented (unchanged). The factory imports: **two**, not three, fixed by a **neutral `cogt/img_gen/` mapping module** — **no registry** | VertexAI is being removed so its edge self-resolves. The registry cannot dispatch these: `make_args_for_model` takes no sdk, dispatch is by `AspectRatioTaxonomy`, and gateway is one SDK spanning both taxonomies. A registry slot would also force a plugin-API bump for two import sites |
| **D-M1-7** | **M1 stacks on M3** (PR → M3, retargeted to `dev` on merge). M2 lands after M1 and re-acks drift post-rebase | The plan asserted both "M3 → M1" and "each track branches from #1064 against `dev`"; M1 cannot be both. M1/M2 share three files, so they are not operationally parallel |
| **D-M2-3** | **M2 is not release-gated** and comes out of the sweep table | Measured: zero external consumers import `pipelex.plugins.<vendor>` |
| **D-M1-8** | **`PipelexBundleBlueprintValidationErrorData` moved to `pipelex.core.exceptions`**, not into `mthds_parsing/` with the parser that raises it | Ruled during M1a under the authority M1c's plan granted ("if the closure test *does* fail on it, move the data class to a runtime-layer home instead"). It does fail: `core.memory.working_memory_factory` reaches it, and the closure test's `INTERPRETER_CORE_EXCLUDED` existed for exactly that. `core/exceptions.py` already holds the two sibling structured error-data models keyed on the same `PipeValidationErrorType`. Moving the leaf is what let the exclusion be deleted outright rather than carried forward |
| **D-M2-4** | **M2 is stacked on M1 on one branch**, not a parallel branch off #1064 rebased afterwards | The plan's own [Gating](#gating) already prescribed the landing order M3 → M1 → M2 and warned that the three shared files make them non-parallel. Stacking satisfies the order, removes the conflict, and removes the mandatory post-rebase drift re-ack — the ack recorded at CHECKPOINT M2 is against the final tree rather than a tree that will move |
| **D-R-1** | **No third layer** between runtime and interpreter | A layer encodes a forbidden arrow; there is only one (`runtime_hub ↛ interpreter_hub`). The shared kernel a third layer would hold already exists as `core/`'s value model, which both layers use. The pipe vocabulary fails the entry test — only the interpreter needs it |
| **D-F1-1** | **Two mapping modules, not one.** `cogt/img_gen/img_gen_gemini_mapping.py` + `cogt/img_gen/img_gen_gpt_mapping.py` | The plan said "a neutral `cogt/img_gen/` mapping module", singular. The two taxonomy families share **zero** code, come to ~500 lines together, and cover disjoint `AspectRatioTaxonomy` members; the repo files one topic per module, and the existing tests were already split per family. Named on the package's own `img_gen_*` prefix convention, with classes `ImgGen<Family>Mapping` to match `ImgGenArgsFactory` / `ImgGenParamSupport` |
| **D-F1-2** | **Rename the classes and the vendor-suffixed methods**, rather than carrying `GoogleImgGenFactory` / `OpenAIImgGenFactory` into `cogt/` | Two things were wrong in the new home, and both are the defect this track keeps finding — a name that describes where the code used to live. (a) The **vendor** is not what the mapping is keyed by: dispatch is by model *family*, and the gateway resolves Gemini geometry through a Portkey SDK, so "Google" names a party that is not always involved. (b) "Factory" contradicts the repo's own convention (`make_from_*`); these are lookup tables and validators. Renames measured in-tree only: **zero** consumers in any sibling repo |
| **D-F1-3** | **`moderation_literal` returns `None` instead of the OpenAI `omit` sentinel** | Load-bearing for the move, not a drive-by simplification: `Omit`/`omit` come from `from openai import …`, so keeping the sentinel would have put a hard vendor-SDK import in the neutral layer — exactly what F1 exists to remove. Verified equivalent rather than assumed: the sole caller already collapsed the non-`str` case to "emit no key" (`img_gen_args_factory.make_args_from_safety_checker`), and `openai_img_gen_worker.py:78` only ever pops a `str`. The emitted API arguments are identical on every path |
| **D-F1-4** | **Add a neutrality test** (`tests/unit/pipelex/cogt/img_gen/test_img_gen_mapping_neutrality.py`) | Nothing in the repo can catch a regression here. `pipelex.cogt` and `pipelex.providers` are **both** runtime-layer, so the hub-layering guard and the import-closure test are blind to an edge between them *by construction* — the property F1 buys would otherwise be unguarded from the moment it landed, which is the shape of the M2 finding Codex #5 caught. Two complementary checks because the coupling has two routes back: an AST read of the modules' own imports (catches a fresh `from openai import omit`) and a subprocess closure measurement (catches a `pipelex.cogt.*` import that drags an adapter in behind it). The module list is globbed from disk so a third family is covered the day it lands. ⚠ **The first version guarded that glob in the wrong place** — see the [review round](#review-round--done-2026-07-28-fixes-applied-1) |

---

## Measurements

Baseline, measured **2026-07-27** on `bc30149c7` (venv-synced, subprocess per module — see the design doc's snippet).

Core modules loading > 0 interpreter modules (`interp_mods`, `pulls interpreter_hub`):

| module | interp_mods | hub | moved by |
| --- | --- | --- | --- |
| `core.registry_models` | 97 | yes | M3 |
| `core.pipes.pipe_factory` | 51 | yes | M1b |
| `core.pipes.rendering.input_renderer` | 51 | yes | M1b |
| `core.pipes.rendering.output_renderer` | 51 | yes | M1b |
| `core.pipes.pipe_abstract` | 33 | no | M1b |
| `core.bundles.pipe_sorter` | 30 | no | M1a |
| `core.bundles.pipelex_bundle_blueprint` | 30 | no | M1a |
| `core.interpreter.bundle_elaborator` | 30 | no | M1a |
| `core.interpreter.interpreter` | 30 | no | M1a |

Measured **0** outbound and therefore worth restating: `core.pipes.pipe_blueprint` (**moves anyway — D-M1-2 reversed**, see the inbound test below), and the four leaf modules that move for cohesion — `core.bundles.exceptions`, `core.interpreter.exceptions`, `core.interpreter.helpers`, `core.interpreter.validation_error_categorizer`.

### The inbound test — added 2026-07-27, and it is the one that decides layer

The classification snippet above counts **outbound** edges. That tells you whether a module is a *leaf*, not which layer owns it. A module can import nothing and still be exclusively interpreter business. The layer question is **who needs this** — measured against the *declared* runtime-layer packages:

```bash
RUNTIME='pipelex/(cogt|plugins|reporting|system|tools|runtime_hub|core/(concepts|domains|memory|stuffs)|core/pipes/(inputs|stuff_spec))'
for m in pipe_blueprint pipe_output validation variable_multiplicity template_guard_lint handle_pipe_errors exceptions; do
  n=$(grep -rln "core\.pipes\.$m\b" pipelex/ --include="*.py" | grep -cE "$RUNTIME")
  printf "core.pipes.%-24s %s\n" "$m" "$n"
done
```

Result on `89ae4950b`: `pipe_output` 4 · `variable_multiplicity` 5 · `exceptions` 1 → **runtime, stay**. `pipe_blueprint` 0 · `validation` 0 · `template_guard_lint` 0 · `handle_pipe_errors` 0 → **interpreter, move**.

The control matters: `pipe_output` and `variable_multiplicity` score non-zero, so the test discriminates rather than flagging everything. ⚠ It measures against *declared* runtime packages; `pipeline/` and `pipe_run/` are undeclared straddlers, so re-verify any move against the closure test.

Other baselines: `cogt → specific vendor` = 7 statements (4 config, 2 img-gen factory, 1 inline `vertexai_factory`). Runtime entry-point closures (`runtime_hub`, `plugins.builtins`, `content_generator`) currently pull in only `pipelex.pipeline` + `pipeline.pipeline_models` from the straddler zone.

### Post-M3, measured 2026-07-27

Baseline above re-taken on `95a1e9bf7` before any edit: **identical** to the table — same nine modules, same counts. No drift since `bc30149c7`.

After M3, with `"pipe_machinery"` added to the snippet's `I` set:

| module | interp_mods | hub | moved by |
| --- | --- | --- | --- |
| ~~`core.registry_models`~~ | ~~97~~ → **0** | **0** | ✅ M3, done |
| `core.pipes.pipe_factory` | 51 | yes | M1b |
| `core.pipes.rendering.input_renderer` | 51 | yes | M1b |
| `core.pipes.rendering.output_renderer` | 51 | yes | M1b |
| `core.pipes.pipe_abstract` | 33 | no | M1b |
| `core.bundles.pipe_sorter` | 30 | no | M1a |
| `core.bundles.pipelex_bundle_blueprint` | 30 | no | M1a |
| `core.interpreter.bundle_elaborator` | 30 | no | M1a |
| `core.interpreter.interpreter` | 30 | no | M1a |

Nine → eight. Every other module's count is **unchanged**, which is the expected shape: `registry_models` had exactly one consumer and was on no other module's import path.

Inverted `core → pipe_*` import statements: **43 → 19** — `pipelex_bundle_blueprint` 12 · `bundle_elaborator` 4 · `output_renderer` 2 · `pipe_abstract` 1. All 19 belong to modules M1 hoists, so M1's target of **0** needs no further work in `core/` beyond the moves already planned.

### Post-M1, measured 2026-07-27 on `10080cf26`

Classification snippet with `I` = the nine interpreter packages: **zero** `pipelex.core.*` modules report a non-zero `interp_mods` or `hub`. The table is empty — M1's headline criterion, reached in two steps (M1a took it 8 → 4 by hoisting the parser, M1b took it 4 → 0 by hoisting the Pipe machinery).

Inverted `core → pipe_*` import statements: **43 → 19 (M3) → 3 (M1a) → 0**. The 3 that survived M1a were `pipe_abstract`'s one `pipe_signature.exceptions` import and `output_renderer`'s two deferred `pipe_controllers` imports under `TYPE_CHECKING` — both modules M1b moved, so no further work in `core/` was needed.

Inbound test, re-derived at move time rather than trusted: everything that moved scored **0** declared runtime-layer importers (`pipe_blueprint`, `validation`, `template_guard_lint`, `handle_pipe_errors`, `pipe_abstract`, `pipe_factory`, `rendering`); everything that stayed scored non-zero (`pipe_output` 4, `variable_multiplicity` 5, `exceptions` 1). The control still discriminates, which is what makes the verdict meaningful.

`core/pipes/` final contents: `inputs/`, `stuff_spec/`, `exceptions.py`, `pipe_output.py`, `variable_multiplicity.py` — exactly the runtime half the plan predicted.

### Post-M2, measured 2026-07-28

The move: **17** vendor packages + `builtins.py` from `pipelex/plugins/` to `pipelex/providers/`. **136** files rewritten, **1364** substitutions, of which **191** string literals (predicted 189) and **145** `subject_grants.toml` path keys (12 grants stay, all on mechanism modules).

| | before | after |
| --- | --- | --- |
| directories under `pipelex/plugins/` | 17 vendors + mechanism | **0 vendors** — mechanism modules only |
| `RUNTIME_LAYER_PACKAGES` entries | 7 | **8** (`pipelex.providers` added) |
| source files outside `providers/` naming a specific vendor | 3 | **3** (unchanged — the documented `cogt` edges) |
| `pipelex/plugins/` modules naming a vendor | 1 (`builtins.py`) | **0** |

`INTERPRETER_PACKAGES` is **unchanged** — M2 adds a runtime-layer package, so the matched triple (guard tuple / closure predicate / hub-layering snippet / design-doc snippet) is undisturbed, and the design doc needed no edit. Verified by script rather than assumed: the closure predicate and the doc snippet still name the same set.

### Post-F1, measured 2026-07-28

| | before | after |
| --- | --- | --- |
| `cogt → specific vendor` import statements | 7 | **5** — the four `config_cogt.py` config classes (documented, D-M2-2) + the deferred `VertexAIFactory` |
| source files outside `providers/` naming a vendor module | 3 | **2** (`cogt/config_cogt.py`, `cogt/model_backends/backend_factory.py`) |
| third-party packages imported by the img-gen mapping modules | 1 (`openai`) | **0** |
| `pipelex.providers.*` modules in the mapping modules' import closure | — | **0**, measured in a fresh interpreter |

⚠ The vendor-segment character class matters here too (the M2 trap): `[a-z0-9_]+`, not `[a-z_]*`. The measurement above is the whole verdict for F1 — the rewrite itself was keyed on literal module paths and was never at risk.

The mutation that proves the closure check discriminates: adding one `pipelex.providers.google.google_factory` import to a mapping module makes it report **10** provider modules, not one — `google_factory` reaches `pipelex.config`, which reaches `config_cogt`, which names the four vendor configs. The documented `cogt → config` inversion is therefore also the shortest path back to full vendor coupling, which is worth knowing before anyone calls it harmless.

*(Append post-phase re-measurements here as each checkpoint clears.)*

---

## Review findings

`/plan-eng-review`, 2026-07-27, against `89ae4950b`. Eight issues, all ruled. Recorded so the reasoning survives the checkpoint.

| # | finding | ruling |
| --- | --- | --- |
| 1 | "No external consumer imports `PipelexInterpreter`" was false — 5 repos, and 4 consume it as an `error_type` **wire string** that renaming breaks silently | Rename; carry all 5 into the sweep (D-M1-4) |
| 2 | `conformance/` `ALLOWED_SURFACE` + `docs/specs/` pin `core.pipes.pipe_abstract`; unmentioned by the plan, and `_hub`'s suite cannot catch it | Hard item at CHECKPOINT M1, not sweep work |
| 3 | D-M1-2 classified by **outbound** imports; the inbound test says `pipe_blueprint` + 3 more are interpreter-only | D-M1-2 reversed; all four move; this makes D-M1-5's deletion honest and saves a doc rewrite |
| 4 | M2 has **zero** external blast radius; the "one wave" argument does not cover it | M2 de-gated from the sweep (D-M2-3) |
| 5 | The `hub-layering-convention` drift contract fires in all 3 tracks; only M1c had an ack | Ack steps added to M3 and M2 |
| 6 | The guard test needs a full rewrite, not a one-line fix — and 4 assertions go **vacuously green** between M1b and M1c | Rewrite wholesale in the collapse commit |
| 7 | 189 (M2) + 15 (M1) **string-literal** module references that no import rewrite or type checker sees | Added to ground rule 5, budgeted per track |
| 8 | F1's "dispatch through `inference_backend_registry`" does not typecheck — it is `MakeWorkerFn`-only | F1 re-scoped to 2 imports + a new registry slot (D-M2-2) |

Also settled: **no third layer** is needed (D-R-1).

### Outside voice — Codex, same day, 15 further findings

Run in-repo at `reasoning_effort=high`, told what the review above had already found. Verdict: *"not implementation-ready."* Eight claims were verified against the tree; all held. All 15 are folded in.

| # | finding | where it landed |
| --- | --- | --- |
| **5** | **The M2 guard claim was backwards.** The plan said omitting `"pipelex.providers"` is caught by the transitive rule. It cannot be — `hub_layering_guard.py:677` filters through `is_runtime_layer`, so an **undeclared** package is excluded from the rule's domain. The plan named its riskiest step and pointed at a safety net that does not exist | M2 — explicit guard test |
| **14/15** | F1 had no workable dispatch key (`make_args_for_model` takes no sdk; dispatch is by taxonomy; gateway is one SDK spanning both) and implied an unplanned plugin-API bump | **F1 rewritten** — neutral mapping module, no registry |
| **3** | PR topology was self-contradictory (M3→M1 *and* each track based on #1064) | Gating — M1 stacks on M3 |
| **1** | `mthds_parsing` unguarded between M1a and M1c | Predicate updated in **M1a** |
| **2** | `mthds_parsing/` and `providers/` had no `__init__.py` step; ruff `INP001` fails the commit | Both tracks |
| **4** | M1 and M2 are architecturally but **not operationally** independent; a rebase invalidates the drift ack | Gating — landing order + re-ack |
| **6** | `DIRTY_ENTRY_POINT` proves *a* token matches, not that each new one is spelled right | M1c — leaf probe per package |
| **7** | The M3 regression test was too weak — one pipe + one stuff misses a dropped list or model | M3 — full-set + disjointness |
| **8** | `subject_grants.toml:2615` embeds `PipelexInterpreter.make_pipelex_bundle_blueprint`; re-pathing alone leaves it stale | M1a |
| **9/10** | Hand-written importer and test-move inventories were materially incomplete (26 importer files, not ~11) | M1a / M1b — assert-zero-old-paths |
| **11** | The design doc still contradicted this tracker | Superseded banner added to the design doc |
| **12** | M2's "vendor imports nothing but mechanism = 0" is false by construction — cross-vendor edges are deliberately kept | Metric restated |
| **13** | Stale architectural prose in *source* (`contract.py:33-35`, `interpreter_plugins/builtins.py:3-8`) | M2 sweep |

Clean on two axes it checked independently: pydantic/kajson (the discriminated union keys on the stable `type` field and no registered concrete pipe class moves) and entry-point metadata / relative imports.

## Follow-ups from the review

Not in this wave. Captured with their evidence so they are not re-derived.

- [ ] **Decouple `error_type` from the Python class name.** Give each `PipelexError` an explicit stable wire identifier instead of deriving `error_type` and the docs `type_uri` from the class name. Every error-class rename is currently a silent break for any consumer switching on the string, and nothing in the repo flags it. Evidence: `mthds-starter-js/src/lib/errors.ts:176`, `pipelex-starter-js/src/lib/errors.ts:257`, `vscode-pipelex/.../cliValidationBackend.test.ts:99`, `playroom/src/app/api/graph/route.ts:119`. Would also remove the need for the `redirect_maps` workaround. Independent of all three tracks; touches the error model and the agent-CLI JSON envelope, so it needs a matching spec/conformance change.
- [ ] **Close the two holes in the img-gen neutrality guard, or downgrade its comment to what it proves.** Raised by the [third F1 review round](#third-review-round--review-done-2026-07-28); recorded rather than fixed because both are cheap and neither is worth machinery on a track whose whole argument was "placement, not indirection". (a) **Transitive vendor SDKs are unguarded.** `_import_roots` reads only the mapping modules' own import statements and `_CLOSURE_SCRIPT` counts only `pipelex.providers`, so an `openai` import reached through some other `pipelex.cogt` module passes both checks. Measured clean today — **zero** vendor-SDK imports anywhere in `pipelex/` outside `providers/` — and *that* is the stronger invariant, unguarded and worth a repo-wide test of its own rather than a denylist bolted onto this one. (b) **The glob under-claims its own coverage.** `_MAPPING_DIR.glob("img_gen_*_mapping.py")` is non-recursive and suffix-keyed, so "a third taxonomy family is covered the day it lands" holds only for a family landing in that exact directory under that exact name. Either bind the convention with a test or soften the comment.
- [ ] **Gate the bookkeeping files a bulk rewrite silently breaks.** Three instances on this branch now, each found by hand well after the fact: `subject_grants.toml` losing its sort (fixed in `bc22ba934`), the matched triple disagreeing on `pipe_signature` (fixed in M3), and `.test_durations` carrying 112 orphan node ids across three commits (fixed in the third F1 round). All three share a shape — a generated or bookkeeping artifact that no gate validates, invalidated by a bulk path rewrite, invisible until someone measures it. A cheap `make check` addition covers two of them: assert `subject_grants.toml` keys are sorted, and assert every `.test_durations` node id resolves against a full unfiltered collection. ⚠ The collection must run with `-m ""` — the marker filter in `addopts` hides ~312 items, so a naive check would report every `e2e` entry as an orphan.
- [x] **Guard against vacuously-green string-predicate tests.** ✅ **Done in M1c** — see T10. Assert that every module qname referenced as a string literal in the guard and closure tests resolves to a real module. `is_runtime_layer` never checks existence, so a moved module silently converts assertions into tests of nonexistent paths — the M1b→M1c window is the worked example. Best done **after M1**, when the guard config is in its final shape.

## Cold-start brief

**Read this first in a new session.** Keep it true at every checkpoint.

- **Where:** worktree `_hub/`, based on `refactor/Hub-2` (PR #1064). **Two branches now**: `refactor/Modularity-3` carries M3 + M1 + M2 and is pushed at `fa6f4fae9`; `refactor/Modularity-4` branches off it and carries F1 alone, local only. That split was made outside this plan's own steps but it *is* the topology [Gating](#gating) prescribes — F1 is the track's only behavior change and was always meant to be a separate PR on top. Related memory: `project_modularity_refactors.md`, `project_hub_split_refactor.md`.
- **What:** three refactors continuing the hub split — M3 (split the boot manifest, seed `pipe_machinery/`), M1 (hoist core's interpreter half into `mthds_parsing/` + `pipe_machinery/`, collapse the guard declaration), M2 (split `plugins/` into mechanism + `providers/`), then follow-up F1 (the two img-gen factory imports, fixed by moving the mappings inward — **no registry**, see D-M2-2).
- **Why now:** **M3 and M1** break external imports, and the repo already owes a release-gated cross-repo sweep for the hub split — landing them first means consumers absorb one breaking wave instead of several. **M2 and F1 do not** (measured zero external consumers for both) and can land on their own schedule.
- **State:** **M3, M1, M2 and F1 all done and committed on one branch — sitting at CHECKPOINT F1.** M1 is three commits: `0f0309b8f` (M1a, parser → `mthds_parsing/`), `c9c45c475` (M1b, Pipe machinery → `pipe_machinery/`), `10080cf26` (M1c, declaration collapse + guards + docs), plus `7beda698f` for the review fixes. M2 is one commit on top (D-M2-4 — stacked, not parallel) plus `fa6f4fae9` for its review fixes, then F1. All gates green at every checkpoint, all exit criteria met. **Every track's review round is done and its fixes committed** — the moves cleared every time, every defect was docs/fixture/test-quality drift, and three placement items are deferred to `wip/refactoring/deferred-placement-follow-ups.md`. **F1 has had three rounds** (`correctness-and-boot`, `over-engineering`, then `/review` against the F1-only diff): no correctness defect in any of them, and the third round's fixes are the last of it. Only Phase 5 remains.
- **Blocking:** PR #1064 must merge before this branch opens a PR against `dev`. **No open decisions.**
- **⚠ Two cross-repo edits are uncommitted in sibling repos** — `conformance/tests/pipelex_transport/test_data.py` and workspace-root `docs/specs/pipelex-transport-boundary.md`, one line each, repointing `PipeAbstract` to `pipelex.pipe_machinery`. They are release-gated with the rest of the sweep and must not be lost.
- **What M3 actually changed:** no module moved paths and no class was renamed — only the six pipe lists moved from `CoreRegistryModels` to `pipelex.pipe_machinery.registry_models.PipeRegistryModels`. M3 contributes **nothing** to the cross-repo sweep. **M1 is where the sweep debt is incurred**, and it is bigger than the module moves: `PipelexInterpreterError` → `MthdsParserError` is the `error_type` **wire string** four TypeScript consumers branch on, and the docs redirect does nothing for them.
- **What M2 confirmed, and the one thing it adds:** every M1 lesson below fired again. The test inventory in the plan was incomplete a third time (six flat modules needed per-module classification, and one — `test_inference_backend_coverage.py` — reads as a vendor test by name while being a mechanism test by subject). The generated-output lesson paid off directly: `_SUBSYSTEM_SECTIONS` was missing a `providers` row, the identical defect M1 hit with `mthds_parsing`, and `make gep` exits 0 either way. **The new one: a grep character class is a measurement bug.** `pypdfium2` has a digit, so `[a-z_]*` silently skips it — the rewrite was safe (literal vendor names) but the *verification* under-counted, which is worse, because the verification is what licenses "done". Use `[a-z0-9_]+`.
- **What M1 learned that M2 will hit again:**
    1. **Test inventories written in advance are wrong.** Both of M1's were materially incomplete. Derive the move list from each test's actual subject, at move time.
    2. **A `Path(__file__).parents[N]` in a moved test is a silent bug** — nothing static sees a parent count, and it fails only under the full suite. Sweep for it after every test move.
    3. **Doc enumerations are where `hub-layering.md` rots** — and the ones that go stale are rarely in the paragraph your diff touches. M1c found two (`The layer rule`, the must-not-name list) well away from the change. Grep for a *sibling* package name, not for the thing you moved.
    4. **Moving the leaf beats excluding it.** M1a's straddler decision is the general lesson: an exclusion records a placement problem, a move removes it. `pipeline` / `pipe_run` are the two left.
    5. `make cleanderived` deletes a gitignored generated test fixture that only the test targets rebuild, so pyright fails on unrelated errors until you regenerate it (command in [Phase 0](#phase-0--baseline)).
- **The four things that will bite you:** (1) re-path `subject_grants.toml` *before* `make agent-check`, or `fix-keyword-only` silently rewrites your subjects — note that a whole-tree textual rewrite re-paths them for free, including qualnames embedded in the key, which is how M1a's `PipelexInterpreter.make_pipelex_bundle_blueprint` fixed itself; (2) `pipelex.plugins.secrets` is a vendor dir but `pipelex.plugins.secrets_provider_registry` is a mechanism module — no prefix `sed`; (3) the guard tuple, the closure-test predicate, the hub-layering snippet and the design-doc snippet are a matched set — **the first three are now mechanically bound by tests** (M1c), the design doc's is not; (4) **string literals are module references too** — 189 in M2, invisible to every import tool.
- **What the rewrite method looked like, since M2 is the same shape at larger scale:** one Python script over `git ls-files`, an ordered longest-first substitution list (dotted paths, then filesystem paths, then test paths, then the class rename), excluding `CHANGELOG.md` / `TODOS.md` / `wip/` / `docs/errors/` — history and generated pages must not be rewritten. Then `grep` the whole tree for the old paths and assert the only survivors are in those excluded files. That completion check is what makes "did I get them all?" answerable.
- **The measurement trap that already caught this plan once:** the classification snippet counts *outbound* imports. It tells you whether a module is a leaf, **not** which layer owns it. Use the [inbound test](#the-inbound-test--added-2026-07-27-and-it-is-the-one-that-decides-layer) for layer decisions.
- **What F1 adds, and it generalizes past this track:** a placement fix *inside one layer* has no gate. Both `pipelex.cogt` and `pipelex.providers` are runtime-layer, so the hub guard and the closure test cannot see an edge between them by construction — every `cogt → vendor` inversion on this page is invisible to both. Whenever you fix one, the invariant you just bought is unguarded from that moment on unless you write the test yourself (D-F1-4). The same is true of the four `config_cogt` edges that stay, which is why they are documented rather than merely tolerated.

---

## Implementation Tasks

Synthesized from the review's findings. Each derives from a specific finding above.

- [x] **T1 (P1, human: ~3h / CC: ~20min)** — M3 — Add the regression test pinning pipe + stuff classes into the class registry after boot
  - Surfaced by: Test review — M3 splits `register_classes`; nothing asserts registry contents; failure is silent at boot
  - Files: ~~`tests/unit/pipelex/test_hub_lifecycle.py`~~ → **new `tests/unit/pipelex/test_registry_models_split.py`** (one TestClass per module is a repo rule), `pipelex/pipelex.py`
  - Verify: `make tb`, then drop one `register_classes` line and confirm the test goes red — ✅ done, and the stronger mutation too (drop one model from one list)
- [x] **T2 (P1, human: ~1d / CC: ~40min)** — M1b — Hoist `pipe_blueprint`, `validation`, `template_guard_lint`, `handle_pipe_errors` out of `core/`
  - Surfaced by: Issue 3 — D-M1-2 classified by outbound imports; inbound test shows 0 runtime-layer importers
  - Files: `pipelex/core/pipes/`, `pipelex/pipe_machinery/`, `pipelex/mthds_parsing/`
  - Verify: inbound test reports ≥1 runtime importer for every module left in `core/pipes/`; `make chl`; closure test
- [x] **T3 (P1, human: ~2h / CC: ~15min)** — M1c — Update `conformance` ALLOWED_SURFACE + `docs/specs/pipelex-transport-boundary.md`
  - Surfaced by: Issue 2 — active unskipped test pins `pipelex.core.pipes.pipe_abstract`; `_hub`'s suite cannot catch it
  - Files: `conformance/tests/pipelex_transport/test_data.py`, `docs/specs/pipelex-transport-boundary.md`
  - Verify: `make check-spec-links` in `conformance/`
- [ ] **T4 (P1, human: ~4h / CC: ~30min)** — Phase 5 — Expand the sweep table to 8 repos incl. the 4 `error_type` wire-string consumers
  - Surfaced by: Issue 1 — the table named one repo; there are eight, and four consume a wire string
  - Files: `TODOS.md`, workspace-root `CLAUDE.md` (✅ done)
  - Verify: re-run the cross-repo grep; every hit appears in the table
- [x] **T5 (P2, human: ~2h / CC: ~15min)** — M1c — Rewrite `test_core_is_split_between_the_layers` wholesale
  - Surfaced by: Issue 6 — six assertions invert or go stale; four go vacuously green between M1b and M1c
  - Files: `tests/unit/pipelex/cli/dev/test_hub_layering_guard.py`
  - Verify: `.venv/bin/pytest tests/unit/pipelex/cli/dev/test_hub_layering_guard.py`
- [x] **T6 (P2, human: ~1h / CC: ~10min)** — M3 + M2 — Add `drift-ack` steps for `hub-layering-convention`
  - Surfaced by: Issue 5 — `drift.toml:65-69` triggers on the guard; all three tracks touch it, only M1c acked
  - Files: `TODOS.md`, `drift.toml`
  - Verify: `make drift-check` green at each checkpoint — ✅ M3 half done: the contract opened exactly as predicted (only after `git add`; the digest reads the index), was reviewed for real, acked, and logged in `wip/drift-contracts/dogfood-log.md` (mandatory per ack). M2's ack landed at CHECKPOINT M2 — and M2 opened a *second* contract the plan did not predict, `config-docs`, because re-pathing the four vendor config imports touches `config_cogt.py`. Both reviewed for real, both acked, both logged.
- [x] **T7 (P2, human: ~1d / CC: ~30min)** — M2 — Rewrite the 189 string-literal module references
  - Surfaced by: Issue 7 — invisible to import rewrites and pyright; 189 in M2, 15 in M1
  - Files: `tests/unit/pipelex/plugins/`, `pipelex/plugins/`
  - Verify: `make agent-test`; zero surviving `pipelex.plugins.<vendor>` literals
- [x] **T8 (P2, human: ~1d / CC: ~30min)** — F1 — Extract the taxonomy/geometry helpers into a neutral `cogt/img_gen/` mapping module; both sides import inward
  - Surfaced by: Issue 8 + Codex #14/#15 — `make_args_for_model` takes no sdk, dispatch is by `AspectRatioTaxonomy`, gateway is one SDK spanning both; a registry slot would force a plugin-API bump
  - Files: `pipelex/cogt/img_gen/img_gen_args_factory.py`, `pipelex/providers/{google,openai}/*_img_gen_factory.py`
  - Verify: a test per taxonomy branch incl. the unmapped-taxonomy path; `pipelex.plugins.contract` untouched
- [x] **T11 (P1, human: ~2h / CC: ~15min)** — M2 — Add a guard test asserting `pipelex.providers.*` is runtime-layer
  - Surfaced by: Codex #5 — the transitive rule filters through `is_runtime_layer`, so an omitted declaration is excluded from the check, not caught by it. No existing gate covers this
  - Files: `tests/unit/pipelex/cli/dev/test_hub_layering_guard.py`
  - Verify: drop `"pipelex.providers"` from the tuple and confirm the test goes red
- [x] **T12 (P2, human: ~2h / CC: ~15min)** — M1a — Fix the embedded qualname in `subject_grants.toml:2615` alongside the re-path
  - Surfaced by: Codex #8 — the key carries `PipelexInterpreter.make_pipelex_bundle_blueprint`; re-pathing alone leaves it stale and hard-fails `check-keyword-only`
  - Files: `subject_grants.toml`
  - Verify: `make cko`
- [x] **T13 (P2, human: ~1h / CC: ~10min)** — ~~M1a~~ + ~~M2~~ — Create the two missing `__init__.py` files — ✅ both done (`pipelex/mthds_parsing/__init__.py`, `pipelex/providers/__init__.py`)
  - Surfaced by: Codex #2 — ruff `select = ["ALL"]`, `INP001` exempt only for `tests/**`; both commits fail lint as written
  - Files: `pipelex/mthds_parsing/__init__.py`, `pipelex/providers/__init__.py`
  - Verify: `make agent-check`
- [ ] **T9 (P3, human: ~3d / CC: ~1 session)** — follow-up — Decouple `error_type` from the Python class name
- [x] **T10 (P3, human: ~4h / CC: ~25min)** — follow-up — Guard against vacuously-green string-predicate tests — ✅ **done in M1c**, both halves: `RUNTIME_LAYER_PACKAGES` entries and `INTERPRETER_PACKAGES` tokens must each resolve on disk, mutation-checked red

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | ISSUES FOUND → absorbed | 15 findings, all folded |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 8 issues, 1 critical gap (closed) |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **CODEX:** ran in-repo at high reasoning effort; verdict *"not implementation-ready"*, 15 findings. Eight verified against the tree, all held. All folded in. Two reversed prior rulings: **F1 drops the registry** for a neutral `cogt/img_gen/` mapping module (no dispatch key exists), and **M1 stacks on M3** (the topology was self-contradictory). The sharpest catch: the plan claimed the transitive rule catches an omitted `RUNTIME_LAYER_PACKAGES` entry — it is the opposite, an undeclared package is excluded from the rule's domain (`hub_layering_guard.py:677`).
- **CROSS-MODEL:** 23 findings total, no overlap — the two passes were complementary rather than confirming. The eng review found *classification and blast-radius* errors (outbound-vs-inbound layer test, wire strings, missing consumer repos); Codex found *build-order and gate-efficacy* errors (lint failures, unguarded windows, a safety net that does not exist). Both agreed independently that F1's registry framing was wrong; only Codex found why.
- **VERDICT:** ENG CLEARED — ready to implement. Scope accepted as-is (three tracks + F1, three stacked PRs); 23 findings folded; 1 critical test gap closed by the regression rule.

NO UNRESOLVED DECISIONS
