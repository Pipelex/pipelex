# Modularity refactors — implementation tracker

**Design doc:** [`wip/refactoring/modularity-refactors.md`](wip/refactoring/modularity-refactors.md) — the *why*, the rulings, the measurement snippets. This file is the *how*: ordered work, checkboxes, hard checkpoints.

**Worktree:** `_hub/` · **Branch:** `refactor/Modularity-3` · **Base:** `refactor/Hub-2` (PR #1064, still open — see [Gating](#gating)) · **Status:** not started.

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
- [ ] Decide with the user whether each track opens its own PR against `dev`, or whether all three land as one `refactor/Modularity-3` PR. The design doc says three PRs; three is the recommendation (each has its own checkpoint and its own blast radius).

---

## Ground rules for every move

These are cross-cutting and each one has already been the cause of a confusing failure somewhere in this repo. Read them before the first `git mv`.

- [ ] **Re-path `subject_grants.toml` in the same commit as the move — and *before* running `make agent-check`.** Grants are keyed `<path>::<qualname>` and staleness is symmetric: a grant whose def moved **hard-fails** `check-keyword-only`. Worse, `make agent-check` runs `fix-keyword-only` *first*, which will silently rewrite the now-"ungranted" subjects to keyword-only — corrupting the diff. Order is always: `git mv` → rewrite grant paths → `make cko` (read-only, must be green) → then `make agent-check`.
  Measured grant hits by moving path (2026-07-27): `core/bundles` 6 · `core/interpreter` 15 · `core/pipes/pipe_abstract` 5 · `core/pipes/rendering` 15 · `core/pipes/pipe_factory` 0 · `core/registry_models` 0 · `plugins/` 160.
- [ ] **Regenerate error pages when an exceptions module moves.** `docs/errors/<slug>.md` carries a `Defined in | <module path>` row, so every moved error class churns its page. Verified: the page **filename and `type_uri` derive from the class name, not the module path** — so a pure move is URL-stable, and only a class *rename* changes a published `type_uri`. Run `make gep` after each move and inspect the diff.
- [ ] **Mirror the test tree in the same commit.** `tests/unit/` mirrors source paths: `tests/unit/pipelex/core/{bundles,interpreter}/`, `tests/unit/pipelex/core/pipes/rendering/`, `tests/unit/pipelex/plugins/`, `tests/integration/pipelex/plugins/`.
- [ ] **`make cleanderived` after every batch of moves**, before running linters or pytest — stale `__pycache__` and collection state make the linters chase ghosts.
- [ ] **Rewrite imports by exact module path, never by prefix substring.** Two live traps:
  - `pipelex.plugins.secrets` (vendor dir) vs `pipelex.plugins.secrets_provider_registry` (mechanism module) — same for `storage`. A prefix `sed` corrupts the mechanism modules.
  - `pipelex.core.interpreter` (the package) vs `pipelex.interpreter_hub` / `interpreter_plugins` (unrelated). Anchor on `pipelex.core.interpreter.` and `pipelex.core.interpreter import`.
- [ ] **Use `git mv`** so history follows the file; do the import rewrite as a separate hunk in the same commit.
- [ ] **Every measurement/guard set is a matched pair.** Whenever a module changes layer or package, three places must agree: `RUNTIME_LAYER_PACKAGES` (the guard), `INTERPRETER_PACKAGES` / `INTERPRETER_CORE` (the closure test), and the classification snippet in the design doc. Updating one and not the others makes a check pass vacuously — the exact failure mode the closure test's `DIRTY_ENTRY_POINT` control exists to catch.

---

## Phase 0 — baseline

Cheap, and it is what every exit criterion is measured against.

- [ ] Confirm the tree is clean and gates are green *before* touching anything: `make agent-check`, `make agent-test`, `make drift-check`, `make chl`.
- [ ] Re-run the [core classification snippet](wip/refactoring/modularity-refactors.md#measurement) and paste the result into [Measurements](#measurements) below with today's date.
- [ ] Note any drift from the design doc's numbers. **Known already:** re-measured on `bc30149c7` the counts are uniformly higher than the doc's (`registry_models` 97 vs 92, the 48s are 51, the 30 is 33, the 28s are 30). The *set of nine* modules and their ordering are unchanged, so the plan holds; only the absolute figures moved.

---

## M3 — split the boot manifest by layer

Removes core's fattest interpreter edge and seeds `pipe_machinery/`. Small, self-contained, no behavior change.

### Work

- [ ] Create `pipelex/pipe_machinery/__init__.py` (empty, per repo convention).
- [ ] Create `pipelex/pipe_machinery/registry_models.py` holding `PipeRegistryModels(RegistryModels)` with the six pipe lists: `PIPE_OPERATORS`, `PIPE_OPERATORS_FACTORY`, `PIPE_CONTROLLERS`, `PIPE_CONTROLLERS_FACTORY`, `PIPE_SIGNATURES`, `PIPE_SIGNATURES_FACTORY`, plus the ~24 `pipe_operators` / `pipe_controllers` / `pipe_signature` imports that come with them.
- [ ] Strip those six lists and their imports out of `pipelex/core/registry_models.py`. `CoreRegistryModels` keeps `STUFF`, `EXPERIMENTAL`, `FIELD_EXTRACTION` and the `core.stuffs` imports only. It should end up importing nothing from `pipe_operators` / `pipe_controllers` / `pipe_signature`, and no longer needing `PipeAbstractType` / `PipeFactoryProtocol` / `Any`.
- [ ] `pipelex/pipelex.py`: import both and register both — two adjacent `register_classes` lines. (`RegistryModels.get_all_models()` reflects over `dir(cls)` and dedups through a `set`, so the split is mechanical and double-registration is impossible.)
- [ ] Add `"pipe_machinery"` to `INTERPRETER_PACKAGES` **and** drop `"pipelex.core.registry_models"` from `INTERPRETER_CORE` in `tests/unit/pipelex/test_runtime_layer_import_closure.py`. Do this in M3, not M1 — the moment an interpreter module lives under a new top-level package the predicate must count it, or the test under-counts silently. (The design doc puts this in M1 move 4; it belongs here for `pipe_machinery`, and in M1 for `mthds_parsing`.)
- [ ] Update the guard's `RUNTIME_LAYER_PACKAGES` docstring where it enumerates `registry_models` as part of core's interpreter half (`hub_layering_guard.py` ~line 101). The declaration tuple itself does not change in M3.
- [ ] `docs/contribute/hub-layering.md`: update the two places naming `core.registry_models` as Pipe machinery inside `core/` (~lines 111, 242).
- [ ] Write the **registration-surface doc** — new page under `docs/contribute/`, registered in **two** places in `mkdocs.yml`: the `llmstxt-md` plugin's section list (~line 330) and the real `nav:` (~line 569). Missing the first one silently drops the page from `llms.txt`. Content: adding a pipe kind touches the kind's package, the type tag (`PipeType`/`PipeCategory`), the blueprint union in `core/bundles/pipelex_bundle_blueprint.py`, `PipeRegistryModels`, and the spec map (`builder/pipe/pipe_spec_map.py` + `pipe_spec_union.py`). Include the note that the spec-layer parallel in `builder/pipe/` is deliberate (see `pipelex/builder/CLAUDE.md`, spec vs blueprint), not duplication to collapse.
- [ ] **Not doing:** the `PipeBlueprintUnion` extraction (cut in design doc v2 — it would move twice, since M1 hoists `core/bundles/` wholesale). **Not doing:** moving `PipeType` / `PipeCategory` out of `core/pipes/pipe_blueprint.py` — measured 0, runtime-layer, stays in `core/` permanently (D-M1-2).
- [ ] Changelog entry under `[Unreleased] → ### Changed`, marked **breaking** (`CoreRegistryModels` no longer carries the pipe lists; `pipelex.pipe_machinery.registry_models.PipeRegistryModels` is new).

### Exit criteria

| | baseline | target |
| --- | --- | --- |
| interpreter modules loaded by `pipelex.core.registry_models` | 97 | **0** |
| inverted `core → pipe_*` import statements | 43 | 19 |
| pipe-kind manifests filed inside `core/` | 2 | 1 |

### 🛑 CHECKPOINT M3 — HARD STOP

1. **Gates** (in this order): `make cko` → `make cleanderived` → `make agent-check` → `make agent-test` → `make drift-check` → `make chl` → `make tb`.
2. **Verify:** re-run the core classification snippet; `pipelex.core.registry_models` must report `0 0`. Confirm the closure test still passes *and* that its `DIRTY_ENTRY_POINT` control still fails (it is what proves the predicate is live).
3. **Update this file:** tick the boxes, record measured actuals in [Measurements](#measurements), refresh the [Cold-start brief](#cold-start-brief), log any decision taken or question raised.
4. **Commit** the phase, then **fan out the reviews** per [Review fan-out protocol](#review-fan-out-protocol) with the commit SHA. M3 reviews: `correctness-and-boot` + `over-engineering`.
5. **Stop.** Report the review verdicts to the user and wait.

---

## M1 — make core's layer split physical

Hoists the eight interpreter-layer modules (plus four measured-zero leaf modules that move for cohesion) out of `core/` into two new packages, then collapses the guard declaration to a single entry. This is the big one — split into three commits.

### D-M1-4 — settle before starting (see [Decisions](#decisions))

- [ ] **Get the user's ruling on renaming `PipelexInterpreterError` → `MthdsParserError`.** The class rename `PipelexInterpreter → MthdsParser` is already ruled (D-M1-3), but the exception is a separate call: `type_uri` derives from the **class name**, so renaming it changes a *published, wire-visible* error identifier (`https://docs.pipelex.com/latest/errors/pipelex-interpreter-error/` → `.../mthds-parser-error/`) and retires a docs URL. A pure module move does not. Recommendation: rename it, for consistency with the package and class, and because this repo runs no deprecation period — but say so in the changelog as a wire-visible break, not just an import break. `BundleElaboratorError` (its subclass) keeps its name either way.

### M1a — `pipelex/mthds_parsing/`

- [ ] `git mv` into a new `pipelex/mthds_parsing/`: `core/interpreter/interpreter.py` → `parser.py`, `bundle_elaborator.py`, `helpers.py`, `validation_error_categorizer.py`, `core/bundles/pipe_sorter.py`, `pipelex_bundle_blueprint.py`.
- [ ] Merge `core/bundles/exceptions.py` + `core/interpreter/exceptions.py` into one `mthds_parsing/exceptions.py` (topical split only if a circular import forces it, per the error-class location convention).
- [ ] Delete `core/bundles/` and `core/interpreter/` (including their empty `__init__.py`).
- [ ] Rename the class `PipelexInterpreter` → `MthdsParser` across the tree (33 Python files, ~76 references incl. docs). Apply the D-M1-4 ruling to `PipelexInterpreterError`.
- [ ] Rewrite importers. Known in-tree importers of `core.interpreter.*`: `pipeline/{validate_bundle,resolve_bundle,execution_seams,dry_run_pipeline}.py`, `libraries/{library_utils,library_manager}.py`, `cli/commands/{validate/pipe_cmd,run/pipe_cmd,run/bundle_cmd,run/_run_core,build/runner/bundle_cmd}.py`. Importers of `core.bundles.exceptions`: `pipeline/{validation_errors,exceptions,fixes/planner}.py`, `libraries/{concept_reference_validation,exceptions}.py`.
- [ ] Move tests: `tests/unit/pipelex/core/{bundles,interpreter}/` → `tests/unit/pipelex/mthds_parsing/`.
- [ ] Re-path subject grants (`core/bundles` 6 + `core/interpreter` 15 hits), then `make cko`.
- [ ] `make gep` and inspect the `docs/errors/` diff (expect `Defined in` row churn; a filename/`type_uri` change only if D-M1-4 says rename).

### M1b — `pipelex/pipe_machinery/`

- [ ] `git mv` into the package M3 created: `core/pipes/pipe_abstract.py`, `core/pipes/pipe_factory.py`, `core/pipes/rendering/` (both renderers + `__init__.py`).
- [ ] Rewrite importers tree-wide (`pipe_abstract` is imported very widely — expect the largest single hunk of the track).
- [ ] Move tests: `tests/unit/pipelex/core/pipes/rendering/` → `tests/unit/pipelex/pipe_machinery/rendering/`; the `pipe_abstract` / `pipe_factory` tests likewise.
- [ ] Re-path subject grants (`core/pipes/pipe_abstract` 5 + `core/pipes/rendering` 15 hits), then `make cko`.
- [ ] Confirm `core/pipes/` still holds exactly its runtime half: `inputs/`, `stuff_spec/`, `pipe_output.py`, `pipe_blueprint.py`, `validation.py`, `variable_multiplicity.py`, `template_guard_lint.py`, `handle_pipe_errors.py`, `exceptions.py`. **Do not** name the new package `pipelex/pipes/` — two `pipes` packages in adjacent layers would be actively confusing.

### M1c — collapse the declaration and the docs

- [ ] Collapse `RUNTIME_LAYER_PACKAGES` in `hub_layering_guard.py`: the six `pipelex.core.*` entries become the single `"pipelex.core"`. Rewrite the long `#:` note above the tuple — it currently justifies the package-by-package listing, which no longer exists.
- [ ] Update `tests/unit/pipelex/cli/dev/test_hub_layering_guard.py:52` — it asserts `not is_runtime_layer("pipelex.core.registry_models")`, which inverts once `pipelex.core` is declared wholesale. Find a still-valid negative case (or assert the new positive).
- [ ] Closure test (`test_runtime_layer_import_closure.py`): add `"mthds_parsing"` to `INTERPRETER_PACKAGES`; then **delete `INTERPRETER_CORE`, `INTERPRETER_CORE_EXCLUDED` and the `is_interpreter` branches that read them** — with the pipe machinery out of `core/` and `pipe_blueprint` ruled runtime (D-M1-2), nothing is left for them to name. This is a genuine simplification the track buys; do not leave the machinery in place carrying an empty tuple. Also update the module docstring's "two documented interpreter homes are deliberately absent" paragraph.
- [ ] **D-M1-6 — while here, add `"pipe_signature"` to `INTERPRETER_PACKAGES`.** It is a top-level interpreter package that the closure test does not currently count, though the design doc's own measurement snippet does. Verify the entry points still pass with it added; if one fails, that is a real pre-existing leak — report it rather than dropping the entry.
- [ ] **Verify the straddler did not become a failure.** `PipelexBundleBlueprintValidationErrorData` (moving into `mthds_parsing/exceptions.py`) is imported by `pipeline/` and `libraries/`. Measured 2026-07-27: **no runtime-layer entry point currently loads it** — `runtime_hub`, `plugins.builtins` and `content_generator` pull in only `pipelex.pipeline` + `pipeline.pipeline_models` — so the deleted exclusion should cost nothing. If the closure test *does* fail on it, do **not** re-add an exclusion: move the data class to a runtime-layer home instead, and record the decision here.
- [ ] `docs/contribute/hub-layering.md`: (a) rewrite the rule of thumb to **"if it imports a pipe kind or constructs pipes, it is interpreter-layer; declaring the vocabulary — type tags, blueprint base shapes, signature normalization — is runtime"** (the old "names a `Pipe`" phrasing misclassifies `pipe_blueprint`); (b) delete the `core.pipes.pipe_output` carve-out paragraph; (c) update the Known-inversions and "Where core splits" sections for the new package names; (d) update line 80's `runtime_hub` must-not-name list.
- [ ] Update the classification snippet in `wip/refactoring/modularity-refactors.md` → Measurement (`I` gains `mthds_parsing`, `pipe_machinery`) so the design doc does not go stale.
- [ ] `make drift-plan` → the `hub-layering-convention` contract triggers on `hub_layering_guard.py`; review the doc for real, `git add` the trigger files, then `make drift-ack CONTRACT=hub-layering-convention RATIONALE="…"`.
- [ ] Changelog entry, **breaking**: the two new packages, the class rename, and the `type_uri` change if D-M1-4 says rename.

### Exit criteria

| | baseline | target |
| --- | --- | --- |
| `RUNTIME_LAYER_PACKAGES` entries naming `pipelex.core.*` | 6 | **1** (`pipelex.core`) |
| `core` modules loading > 0 interpreter modules | 9 (8 after M3) | **0** |
| doc carve-outs for `core.pipes.pipe_output` | 1 | 0 |
| inverted `core → pipe_*` import statements | 19 (after M3) | **0** |

### 🛑 CHECKPOINT M1 — HARD STOP

1. **Gates:** `make cko` → `make cleanderived` → `make agent-check` → `make agent-test` → `make drift-check` → `make chl` → `make gep` (diff must be reviewed, not just generated).
2. **Verify:** re-run the classification snippet with the extended set — every remaining `pipelex.core.*` module reports `0 0`. `make chl` passes with the collapsed declaration *and* the transitive rule reports zero breaching runtime-layer modules. Closure test green including the dirty control.
3. **Update this file** + [Cold-start brief](#cold-start-brief) + [Measurements](#measurements).
4. **Commit**, then **fan out reviews** with the commit range. M1 reviews: `correctness-and-imports` + `boundary-and-naming` + `over-engineering` + `test-and-docs-sync`.
5. **Stop.** Report verdicts and wait.

---

## M2 — separate the plugin mechanism from the vendor adapters

`pipelex/plugins/` is two things under one name: the mechanism (17 top-level modules) and the built-in vendor adapters (17 directories). Splitting them makes the one-way dependency visible: adapters → mechanism, engine → mechanism, mechanism → nothing.

### Work

- [ ] `git mv` the 17 vendor directories to a new `pipelex/providers/`: `anthropic`, `azure_rest`, `bedrock`, `blackboxai`, `docling`, `fal`, `gateway`, `google`, `huggingface`, `linkup`, `mistral`, `openai`, `openrouter`, `portkey`, `pypdfium2`, `secrets`, `storage`. (D-M2-1: `providers/` over `backends/` — `backends/` would collide with `pipelex/cogt/model_backends/`, and the code's own vocabulary for the non-inference adapters is already "provider": `secrets_provider_registry`, `storage_provider_registry`.)
- [ ] `pipelex/plugins/` keeps the mechanism only: `contract.py`, `registrar.py`, `discovery.py`, `exceptions.py`, the seven `*_registry.py`, `model_handle.py`, `sdk_client_registry.py`, `sdk_client_manager.py`, `backend_extras_factory.py`.
- [ ] `builtins.py` follows the vendors → `pipelex/providers/builtins.py`, still exporting `RUNTIME_BUILTIN_PLUGINS` / `RUNTIME_CORE_UNCONDITIONAL_PLUGIN_NAMES`. Re-point the downward import in `pipelex/interpreter_plugins/builtins.py`. Both stay parameters of `build_registrar` — unchanged.
- [ ] Rewrite imports. **Watch the `secrets` / `storage` trap** (ground rules): `pipelex.plugins.secrets` is a vendor dir, `pipelex.plugins.secrets_provider_registry` is a mechanism module that must not move. Same for `storage`.
- [ ] **Add `"pipelex.providers"` to `RUNTIME_LAYER_PACKAGES`.** This is the one step where a mistake is invisible — the vendors are runtime-layer today by declaration *and* by measurement; dropping them from the guard silently un-declares the largest runtime package. The transitive rule is what catches it.
- [ ] Add `pipelex/providers/builtins.py` to the closure test's `RUNTIME_LAYER_ENTRY_POINTS` (replacing `pipelex.plugins.builtins`, which after the move no longer aggregates anything). Its presence there is load-bearing history: that module and three neighbours breached the boundary transitively while both gates stayed green.
- [ ] Move tests: `tests/unit/pipelex/plugins/` and `tests/integration/pipelex/plugins/` — split so vendor tests land under a `providers/` mirror and mechanism tests stay under `plugins/`.
- [ ] Re-path subject grants (160 hits under `plugins/` — the bulk are vendor workers), then `make cko`.
- [ ] `make gep` — several vendor directories carry exceptions modules (`gateway`, `portkey`, `bedrock`, `google`, `mistral`, `openai`, …), so expect a wide `Defined in` diff. Filenames and `type_uri`s must be **unchanged** (no class renames in M2); if one changes, something got renamed by accident.
- [ ] Docs sweep for `pipelex/plugins/<vendor>/` paths: `docs/under-the-hood/reasoning-controls.md` (a table of ~10 paths), `error-model.md` (3 refs to `pipelex/plugins/*/`), `inference-backend-plugins.md`, `secrets-provider-plugins.md`, `orchestrator-plugins.md`. **Do not touch the entry-point group name** `"pipelex.plugins"` — it is a group identifier, not a module path, and it is the third-party contract.
- [ ] `docs/contribute/hub-layering.md` → **Known inversions**: record the four `cogt → provider config` imports (`anthropic`, `google`, `mistral`, `openai` config classes reached from `cogt/config_cogt.py`) as a deliberate, documented exception. Rationale (D-M2-2): the main config model is statically typed end-to-end (`configs.py` ⇄ `pipelex.toml` structural sync); making vendor config sections plugin-contributed would trade that static typing for a dynamic registry.
- [ ] Changelog entry, **breaking**: `pipelex.plugins.<vendor>` → `pipelex.providers.<vendor>`. State explicitly that the *plugin entry-point contract is unaffected* — an external plugin imports `pipelex.plugins.contract` / `pipelex.plugins.registrar`, both of which stay put.

### Exit criteria

| | baseline | target |
| --- | --- | --- |
| mechanism modules importing a vendor | 1 (`builtins.py`, by design) | **0 in `plugins/`**, 1 in `providers/` |
| vendor modules importing anything but the mechanism | 0 | 0 (unchanged) |
| `cogt → <specific vendor>` statements | 7 | 7 (4 documented, 3 queued as the follow-up) |
| `RUNTIME_LAYER_PACKAGES` covers every vendor module | yes | yes |

### 🛑 CHECKPOINT M2 — HARD STOP

1. **Gates:** `make cko` → `make cleanderived` → `make agent-check` → `make agent-test` → `make drift-check` → `make chl` → `make gep` (review the diff).
2. **Verify:** transitive layering rule reports zero breaching runtime-layer modules; closure test reports zero interpreter modules for every runtime entry point *including the new `providers.builtins`*; the dirty control still fails.
3. **Update this file** + [Cold-start brief](#cold-start-brief) + [Measurements](#measurements).
4. **Commit**, then **fan out reviews**. M2 reviews: `correctness-and-imports` + `boundary-and-naming` + `over-engineering`.
5. **Stop.** Report verdicts and wait.

---

## Follow-up F1 — the three `cogt → vendor` factory imports behind the registry

Deliberately **not** inside the 127-file M2 move: this is a behavior change and would be invisible in that diff (D-M2-2).

- [ ] `pipelex/cogt/img_gen/img_gen_args_factory.py:37-38` — `GoogleImgGenFactory` / `OpenAIImgGenFactory` imported by name. Dispatch through `inference_backend_registry` instead.
- [ ] `pipelex/cogt/model_backends/backend_factory.py:53` — the inline (`# noqa: PLC0415`) `VertexAIFactory` import. Same treatment.
- [ ] Tests covering the dispatch for each affected backend.
- [ ] Changelog entry.

### 🛑 CHECKPOINT F1 — HARD STOP

Gates as above (this one *does* change behavior, so `make agent-test` is the real gate, not a formality). Reviews: `correctness-and-boot` + `over-engineering`. Then stop.

---

## Phase 5 — close out

- [ ] Verify the three (or one) PRs are open against `dev` with #1064 merged first.
- [ ] Write the **cross-repo sweep handoff** into `wip/refactoring/` — the sweep is release-gated and shared with the hub split, the Phase 3 type moves, and the `interpreter_plugins` relocation. It must land as **one breaking wave**, not four. Known external hits:

  | repo | file | symbol |
  | --- | --- | --- |
  | `pipelex-api` | `api/routes/pipelex/build/runner.py` | `PipelexBundleBlueprint` |
  | `pipelex-api` | `api/routes/pipelex/crate_ops.py` | `PipeAbstract` |
  | `pipelex-api` | `tests/unit/test_validate_errors.py` | `PipelexBundleBlueprintValidationErrorData` |
  | `pipelex-api`, `pipelex-cookbook`, `cocode`, `pipelex-mistralai-workflows` | various | `pipelex.plugins.*` — size the vendor-specific subset during the sweep |

  Verified clean: `pipelex-cookbook`, `cocode`, `pipelex-mistralai-workflows`, `pipelex-worker`, `pipelex-starter-python`, `pipelex-relay`, `sandbox` (for the M1 module set). **`pipelex-temporal` is private and unchecked — verify during the sweep.** No external consumer imports `PipelexInterpreter`, so the class rename adds nothing. No kajson-registered class moves, so serialized payloads are untouched.
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
| **D-M1-2** | Measurement beats the "names a `Pipe`" heuristic: `pipe_blueprint.py` is runtime and stays in `core/`; the four measured-zero leaf modules move with their packages |
| **D-M1-3** | `core/interpreter/` + `core/bundles/` → `pipelex/mthds_parsing/`; `PipelexInterpreter` → `MthdsParser` |
| **D-M2-1** | Vendors → `pipelex/providers/`, flat, no capability nesting |
| **D-M2-2** | The four `cogt` config imports: accepted + documented. The three factory imports: defect, fixed as follow-up F1 after M2 |

Raised while writing this plan — **need a ruling before the phase that depends on them**:

| id | question | needed by | recommendation |
| --- | --- | --- | --- |
| **D-M1-4** | Rename `PipelexInterpreterError` → `MthdsParserError` alongside the class? It changes a published, wire-visible `type_uri` and retires a docs URL, which a pure module move does not. | M1a | **Rename**, and add a `redirect_maps` entry in `mkdocs.yml` (`errors/pipelex-interpreter-error.md` → the new page) so the retired `type_uri` still resolves — the redirects plugin is already configured and used for exactly this. Consistency with the package and class; no deprecation period in this repo. Call it out in the changelog as wire-visible, not merely an import break. |
| **D-M1-5** | After M1, `INTERPRETER_CORE` / `INTERPRETER_CORE_EXCLUDED` in the closure test name nothing. Delete them, or keep them as empty scaffolding? | M1c | **Delete both**, plus the `is_interpreter` branches reading them. If the straddler resurfaces as a failure, move the data class to a runtime-layer home rather than re-adding an exclusion. |
| **D-M1-6** | `pipe_signature` is a top-level interpreter package the closure test does not count (the design doc's snippet does). Add it? | M1c | **Add it.** If an entry point then fails, that is a real pre-existing leak worth surfacing, not a reason to omit the entry. |

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

Measured **0** and therefore worth restating: `core.pipes.pipe_blueprint` (stays in `core/`, D-M1-2), and the four leaf modules that move for cohesion — `core.bundles.exceptions`, `core.interpreter.exceptions`, `core.interpreter.helpers`, `core.interpreter.validation_error_categorizer`.

Other baselines: `cogt → specific vendor` = 7 statements (4 config, 2 img-gen factory, 1 inline `vertexai_factory`). Runtime entry-point closures (`runtime_hub`, `plugins.builtins`, `content_generator`) currently pull in only `pipelex.pipeline` + `pipeline.pipeline_models` from the straddler zone.

*(Append post-phase re-measurements here as each checkpoint clears.)*

---

## Cold-start brief

**Read this first in a new session.** Keep it true at every checkpoint.

- **Where:** worktree `_hub/`, branch `refactor/Modularity-3`, based on `refactor/Hub-2` (PR #1064). Related memory: `project_modularity_refactors.md`, `project_hub_split_refactor.md`.
- **What:** three refactors continuing the hub split — M3 (split the boot manifest, seed `pipe_machinery/`), M1 (hoist core's interpreter half into `mthds_parsing/` + `pipe_machinery/`, collapse the guard declaration), M2 (split `plugins/` into mechanism + `providers/`), then follow-up F1 (three `cogt` factory imports behind the registry).
- **Why now:** all three break external imports, and the repo already owes a release-gated cross-repo sweep for the hub split. Landing these first means consumers absorb **one** breaking wave instead of four.
- **State:** *not started.* Phase 0 baseline not yet captured beyond the figures in [Measurements](#measurements).
- **Blocking:** PR #1064 must merge before any track opens a PR against `dev`. D-M1-4 needs a user ruling before M1a.
- **The three things that will bite you:** (1) re-path `subject_grants.toml` *before* `make agent-check`, or `fix-keyword-only` silently rewrites your subjects; (2) `pipelex.plugins.secrets` is a vendor dir but `pipelex.plugins.secrets_provider_registry` is a mechanism module — no prefix `sed`; (3) the guard tuple, the closure-test predicate, and the design-doc snippet are a matched set — update one without the others and a check goes vacuously green.
