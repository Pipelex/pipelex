# Autofix — step 2: wave-1 rule breadth (implementation plan)

This is the detailed plan for **step 2 of the autofix master plan** ([wip/autofix/master-plan.md](wip/autofix/master-plan.md)): add the remaining wave-1 fix rules, each a deliberately different fix *shape*, to stress the `SuggestedFix`/`FixOp` abstraction before any human-facing surface exists. Companion docs: [suggested-fixes-design.md](wip/autofix/suggested-fixes-design.md) (architecture, decisions D1–D4, checkpoint-0 findings), [deferred-checkpoint-0-review-items.md](wip/autofix/deferred-checkpoint-0-review-items.md), [spike-reviewers-guide.md](wip/autofix/spike-reviewers-guide.md) (what step 1 built, invariants, test map).

## Cold-start orientation

Worktree `_autofix` on branch `feature/Autofix` (treat this directory as the repo root). Step 1 (spike) is PR #1027 vs `dev`, merge-ready: the chain enriched-typed-error → planner → tomlkit applier → convergence loop is proven on one rule, `match-sequence-output`. The moving parts:

- **Fixes package**: `pipelex/pipeline/fixes/` — `planner.py` (pure translation, keyed on `error_type` + structured fields, never message strings), `applier.py` (in-place tomlkit mutation, guarded skips), `fix_loop.py` (`fix_bundle_file`: validate → collect SAFE fixes → apply → re-validate, fingerprint bail).
- **Wire models**: `pipelex/suggested_fix.py` (`FixOpKind`, `FixOp`, `FixSafety`, `SuggestedFix`); `ValidationErrorItem.suggested_fix` in `pipelex/base_exceptions.py`, `exclude_none`.
- **The one shared builder** every consumer (CLI/API/MCP) flows through: `build_validation_error_items` in `pipelex/pipeline/validation_errors.py`.
- **Gates**: `make agent-check` after every change; full `make agent-test` at checkpoints. Fresh worktrees may need `.venv/bin/pipelex-dev generate-mthds-schema` before `plxt lint` passes. Golden `.mthds` fixtures are processed by `plxt format` during `make agent-check`, so fixtures must be format-stable: write the fixture, run the formatter on it, then derive the golden.

## Working conventions for this step

- **TDD**: red tests first at each layer (enrichment → planner → applier → loop), then implement.
- **Structural suppression, not sniffing**: fixability comes from presence of enrichment fields set only at the raise sites that know the correct value — the planner requires the field and never re-derives or message-matches.
- **In-place mutation, never rebuild** in the applier; golden byte-compare tests are the regression net for format preservation.
- **No changelog entry in this step** — the ship wave (master-plan step 6) owns it, including the additive `suggested_fix` API wire-field note (deferred item 1c).
- **Review-finding triage**: real defects get fixed in the phase; design tradeoffs get recorded as deferred items in `wip/autofix/`, not reflexively applied.

## Review fan-out convention (applies at every checkpoint)

At each checkpoint, after committing the phase, spawn a **Sonnet-5 sub-agent** that runs the **`/code-review` skill** on that phase's changes. Spawn it with **no inherited context**: hand it only a pointer to the changes under review — the phase's commit range (`git diff <phase-base-sha>..HEAD`) or the working-tree diff — never this plan, the design doc, the rationale, or your own conclusions. The point is an unanchored review that judges the code on its own terms (we want clean solid software, not over-engineering). Triage its findings per the convention above, then commit the resulting fixes before moving on.

## Ground truth from code recon (2026-07-07 — verify anchors still hold if resuming cold)

### Input-validation channel (for `sync-controller-inputs`)

- All the relevant raise sites live in `PipeAbstract.generic_validate_inputs_with_library` (`pipelex/core/pipes/pipe_abstract.py:263-349`, `@final`): `MISSING_INPUT_VARIABLE` at :273-279 (unsatisfied `required_variables()`) and :290-296 (needed var not declared); `INPUT_STUFF_SPEC_MISMATCH` at :329-335, **already gated on `self.is_controller`** (:299), comparing declared vs needed on `.concept` and `.multiplicity` only — presence markers deliberately not compared; `EXTRANEOUS_INPUT_VARIABLE` at :341-347.
- These errors carry only `variable_names` (single offending var), `pipe_code`, `domain_code` — **no needed-inputs mapping, no concept/multiplicity as structured fields**. That's the enrichment gap this phase closes.
- Operator raise sites that must stay unfixable: `PipeLLM.validate_inputs_static` (`pipelex/pipe_operators/llm/pipe_llm.py:76-94`) raises MISSING/EXTRANEOUS for prompt variables; `PipeStructure.validate_inputs_with_library` (`pipelex/pipe_operators/structure/pipe_structure.py:75-80`) raises `INPUT_STUFF_SPEC_MISMATCH`. None will set the new field → structurally suppressed. For operators the generic missing/extraneous loops are near-vacuous anyway (their `needed_inputs()` re-emits `self.inputs`), but the `required_variables()` site at :273 can fire for operators — hence the enrichment must be gated on `self.is_controller`, not on the function.
- `needed_inputs()` returns `InputStuffSpecs` (`pipelex/core/pipes/inputs/input_stuff_specs.py`, a `RootModel[dict[str, StuffSpec]]`); `StuffSpec` (`pipelex/core/pipes/stuff_spec/stuff_spec.py`) holds `concept: Concept`, `multiplicity`, `presence: PresenceMarker`, and has `to_bundle_representation()`. Ref grammar/rendering: `MULTIPLICITY_PATTERN`, `PresenceMarker`, `format_concept_with_multiplicity` in `pipelex/core/pipes/variable_multiplicity.py`.
- Flow to error data: `categorize_pipe_validation_with_libraries_error` (`pipelex/core/pipes/handle_pipe_errors.py:180-207`) maps `PipeValidationError` → `PipesAndConceptValidationErrorData` (`pipelex/core/exceptions.py:29-68`); the spike's `expected_output_ref` threading at :206 is the pattern to mirror. A second unwrap path exists at handle_pipe_errors.py:99 (pydantic-wrapped) — thread the new field there too.
- TOML shapes the applier must handle: inline `inputs = { doc = "Document", note = "Text?" }` and block `[pipe.<code>.inputs]`; markers `?`/`!` live inside the value strings.
- Blueprint-stage lookalikes: `validation_error_categorizer.py:58-79` reconstructs MISSING/EXTRANEOUS from pydantic message text into *blueprint-channel* items — those carry no enrichment and must get no fix; don't wire input fixes into that channel.

### Blueprint channel (for `strip-native-concept-redecl`)

- Detection: `PipelexBundleBlueprint.validate_concept_keys` (`pipelex/core/bundles/pipelex_bundle_blueprint.py:97-114`), a `mode="before"` field validator that raises a **bare `ValueError`** ("…because it is natively available in Pipelex…") on the first offending code. Consequences today: pydantic `loc` is `("concept",)`, so `_categorize_concept_validation_error` (`pipelex/core/interpreter/validation_error_categorizer.py:180-222`) produces `PipelexBundleBlueprintValidationErrorData` (`pipelex/core/bundles/exceptions.py:6-19`) with `error_type=None` and `concept_code=None` — the concept code survives only in the message text. **A typed raise + structural unwrap is prerequisite work for this rule.**
- Native concept list: `NativeConceptCode` (`pipelex/core/concepts/native/concept_native.py:20-32`), reject-set built from `values_list()` at the raise site.
- The blueprint loop of `build_validation_error_items` (`pipelex/pipeline/validation_errors.py:82-94`) does **not** call any planner today — the spike's planner only hooks the pipe-validation loop (:123). Adding a blueprint-channel planner call is new wiring.
- Blueprint error data **does** carry `source` (from `blueprint_dict["source"]`) — so this will be the first fix with a populated `SuggestedFix.source`, exercising the loop's source/file check for real.
- TOML authoring forms that all normalize to `concept.<Code>`: `[concept.Text]` table (± `[concept.Text.structure]`), `Text = "..."`/inline-table under `[concept]`, and dotted `concept.Text = "..."`. Applier reality: `DELETE_KEY` with `table_path=["concept"], key="Text"` handles **every** form (tomlkit tables and inline tables are both dicts); `DELETE_TABLE ["concept","Text"]` skips the string-shorthand form (scalar-leaf guard at `applier.py:105`). So the planner should emit `DELETE_KEY` on `["concept"]`.
- The `mode="before"` validator raises on the first offending code, so multiple redeclarations converge error-by-error across loop iterations — same cascade behavior as the spike.

### `strip-namespace` facts (stretch)

- `INVALID_PIPE_CODE_SYNTAX` originates as bare `ValueError`s (`pipelex_bundle_blueprint.py:146-148` for pipe keys, :121-123 for `main_pipe`) and is assigned by **message matching** in `_categorize_syntax_validation_error` (`validation_error_categorizer.py:127-163`), carrying no structured `pipe_code`. Enrichment (typed raise carrying the offending code) is prerequisite work.
- `RENAME_TABLE_KEY` exists on the wire enum but the applier raises for it (`applier.py:109-113`); position-preserving rename mechanics in tomlkit is the gate for the whole rule (the old branch's `del`+re-add reordering bug is what to avoid).
- Reference-rewrite inventory is ready-made: `PipelexBundleBlueprint.collect_pipe_references()` (`pipelex_bundle_blueprint.py:165-189`) enumerates `main_pipe`, `steps[].pipe`, `branches[].pipe`, `branch_pipe_code`, `outcomes` values, `default_outcome`.
- **Known abstraction stress**: rewriting `steps[].pipe` / `branches[].pipe` means addressing *items inside arrays of tables* — `FixOp.table_path: list[str]` cannot express an index today. Resolving this (index segments? a new op kind?) is part of the abstraction verdict this step exists to produce.

## Phase 0 — pre-flight

- [ ] **Branch logistics.** PR #1027 is open and merge-ready *from `feature/Autofix`* — pushing new commits there would append to the reviewed PR. Create a stacked branch for step 2 (e.g. `feature/Autofix-step2` off `feature/Autofix`), or rebase onto `dev` if #1027 has merged by the time work starts. The docs-archival commit (this plan + the `TODOS.md` → `wip/autofix/spike-reviewers-guide.md` move) belongs on the step-2 branch.
- [ ] Commit this plan + the archival move as the first step-2 commit; record the phase-base SHA here for the checkpoint diffs: `________`.
- [ ] Sanity: `make agent-check` and `make agent-test` green at base (should be — CI was green on the spike tip).

## Phase A — `sync-controller-inputs` (first multi-op, in-place table-sync shape)

Trigger: `MISSING_INPUT_VARIABLE` / `EXTRANEOUS_INPUT_VARIABLE` / `INPUT_STUFF_SPEC_MISMATCH` on a **controller** pipe. Fix: in-place sync of the `inputs` table with `needed_inputs()` — add/update/delete keys inside the existing table without rebuilding it. Because the enrichment carries the *full* expected mapping, one fix repairs all input drift for that pipe even though validation aborts at the first error.

### A.1 — Enrichment: `expected_inputs` on the typed error

- [ ] RED: integration tests (new `tests/integration/pipelex/pipeline/test_controller_inputs_enrichment.py`, mirroring `test_sequence_output_enrichment.py`) — controller pipe with a missing input / an extraneous input / a concept-or-multiplicity mismatch each produce a full `expected_inputs` mapping on the error data; operator-raised variants (PipeLLM prompt-var, PipeStructure mismatch, `required_variables()` on an operator) produce `None`.
- [ ] Add `expected_inputs: dict[str, str] | None` to `PipeValidationError` (`pipelex/core/pipes/exceptions.py`) — variable name → bundle-representation ref, the exact strings the fix would write. Internal, error-data only (the wire gets only `suggested_fix`), like `expected_output_ref`.
- [ ] Populate at the `generic_validate_inputs_with_library` raise sites, **gated on `self.is_controller`**. Ref rendering must follow the spike's rules (bare code when same-domain or native, qualified otherwise) — factor/reuse the rendering the spike built for `expected_output_ref` rather than duplicating it.
- [ ] **Optionals-marker guard**: for a variable whose declared spec already matches the needed spec on concept + multiplicity, emit the *author's* declared representation (preserving their `?`/`!`); derive markers only for variables being added or whose concept/multiplicity changes.
- [ ] Thread `expected_inputs` through `categorize_pipe_validation_with_libraries_error` (both call paths — direct and pydantic-unwrapped) into `PipesAndConceptValidationErrorData`.
- [ ] **Prerequisite-clean guard — investigate, then implement at the right layer.** The design says: suppress the fix when co-errors (`UNRESOLVED_PIPE_DEPENDENCY`, `UNRESOLVED_CONCEPT`) make `needed_inputs()` untrustworthy. Open question: since validation aborts at the first `PipeValidationError`, can such co-errors even co-occur in one report, or does `needed_inputs()` recursion (`get_required_pipe`) fail earlier? Decide whether the guard lives at the enrichment site (don't set `expected_inputs` unless the derivation is trustworthy) or in the planner (scan sibling items) — prefer the enrichment site if it suffices (consistent with structural suppression). Record the verdict below and pin it with a test either way.

### A.2 — Planner: multi-op fix

- [ ] RED: planner unit tests (`tests/unit/pipelex/pipeline/fixes/test_fix_planner.py`) — each of the three error types with `expected_inputs` + `pipe_code` present → one SAFE `sync-controller-inputs` fix; suppression cases: no `expected_inputs` → `None`; operator variants → `None`; prerequisite cases per A.1's verdict.
- [ ] Extend `plan_fix_for_pipe_validation_error`: emit `set_key` ops at `table_path=["pipe", <code>, "inputs"]` for added/changed variables and `delete_key` ops for extraneous ones — a *diff* against the declared inputs, not a table rewrite. Multiple ops per fix is the new shape; keep op order deterministic for stable fingerprints.
- [ ] Decide + test the **no-`inputs`-table case** (pipe declares no inputs but needs some): nothing to preserve, so a single `set_key` on `["pipe", <code>]` with an inline-table value is acceptable — requires confirming `FixOp.value` (TomlValue) accepts a dict and the applier writes it as an inline table. Record the decision.
- [ ] `description` wording: name the variables added/updated/removed (agents read this; keep it one line).

### A.3 — Applier + loop

- [ ] RED: golden byte-compare fixtures (`tests/data/fixes/`) covering: inline `inputs = {...}` form, block `[pipe.x.inputs]` form, comments on and around the table, add+update+delete in a single fix, idempotence (apply twice = same bytes). Remember the plxt format-stability workflow for fixtures.
- [ ] Applier: confirm `set_key`/`delete_key` on both inline and block `inputs` tables behave in-place (they should — the spike's `_resolve_table` treats both as dicts); add any missing guard semantics surfaced by the goldens.
- [ ] RED→GREEN: convergence-loop integration test (`tests/integration/pipelex/pipeline/test_fix_convergence_loop.py`) — a controller with drifted inputs fixed in one iteration; if a natural cross-rule cascade fixture exists (sequence-output fix surfacing an input sync), add it — don't force one.
- [ ] Wire test: `suggested_fix` for this rule rides `ValidationErrorItem` through the shared builder (`tests/unit/pipelex/pipeline/test_validation_errors.py`).

### 🛑 CHECKPOINT A — hard stop before Phase B

- [ ] **Verify**: `make agent-check` green; **full** `make agent-test` green (not just targeted tests).
- [ ] **Record for cold start**: update this file — check off A tasks, fill in the A.1 prerequisite-guard verdict and the A.2 no-table decision, note anything that bent the `SuggestedFix`/`FixOp` shape; fold shape findings into the design doc (checkpoint-findings style). Commit.
- [ ] **Review fan-out**: spawn a Sonnet-5 sub-agent running `/code-review` on the Phase A diff only (`git diff <phase-0-sha>..HEAD`), per the fan-out convention above (no inherited context — diff pointer only). Triage, fix real defects, defer tradeoffs to `wip/autofix/`, commit.

## Phase B — `strip-native-concept-redecl` (first blueprint-channel + first delete-shaped fix in production)

Trigger: blueprint-level error for a redeclared native concept. Fix: `delete_key` of `concept.<Code>` (covers every authoring form). This phase opens the blueprint channel end-to-end: typed raise → structured categorization → blueprint planner → fix with a real `source`.

### B.1 — Typed error for the redeclaration

- [ ] RED: tests pinning that a native-concept redeclaration yields blueprint error data with a dedicated `error_type` and the offending `concept_code` as structured fields (all authoring forms).
- [ ] Replace the bare `ValueError` at `pipelex_bundle_blueprint.py:107-113` with a typed exception carrying `concept_code`, and teach the blueprint categorizer to unwrap it structurally (pydantic `ctx["error"]` unwrap, the pattern already used for wrapped `PipeValidationError`s at `validation_error_categorizer.py:268`) — no message matching.
- [ ] Pick the enum home for the new error-type value: check the declared type of `PipelexBundleBlueprintValidationErrorData.error_type` (`pipelex/core/bundles/exceptions.py`) and decide widen-vs-new-enum. Don't resurrect the deleted `PipelexBundleBlueprintFixableErrorType` stub as-is; smallest correct surface wins. Record the decision.

### B.2 — Blueprint-channel planner + wiring

- [ ] RED: planner unit tests — redeclaration error data → SAFE `strip-native-concept-redecl` fix with one `delete_key` op (`table_path=["concept"], key=<Code>`); suppression: missing `concept_code` → `None`; non-redeclaration blueprint errors → `None`.
- [ ] New `plan_fix_for_blueprint_validation_error(...)` in `planner.py`; wire it into the blueprint loop of `build_validation_error_items` (`validation_errors.py:82-94`).
- [ ] Populate `SuggestedFix.source` from the blueprint error's `source` — then verify the loop's source/file check accepts it single-file and (under `library_dirs`) targets only the declaring file. First live exercise of that guard; pin with a test.

### B.3 — Applier + loop

- [ ] RED: golden fixtures for every authoring form — `[concept.Text]` table (incl. one with a `[concept.Text.structure]` sub-table), `Text = "..."` under `[concept]`, dotted `concept.Text = "..."` — with surrounding comments; idempotence.
- [ ] Convergence test: bundle redeclaring more than one native concept converges error-by-error across iterations (the `mode="before"` validator raises one at a time).
- [ ] Wire test: blueprint-channel `ValidationErrorItem` carries the fix through the shared builder.

### 🛑 CHECKPOINT B — hard stop before Phase C

- [ ] **Verify**: `make agent-check` green; full `make agent-test` green.
- [ ] **Record for cold start**: update this file (B decisions: enum home, source-guard behavior observed); fold blueprint-channel findings into the design doc. Commit.
- [ ] **Review fan-out**: Sonnet-5 sub-agent running `/code-review` on the Phase B diff only (`git diff <checkpoint-A-sha>..HEAD`), no inherited context — diff pointer only. Triage, fix, defer, commit.

## Phase C — `strip-namespace` (STRETCH — gated on rename mechanics; dropping it is a valid outcome)

Trigger: `INVALID_PIPE_CODE_SYNTAX` from same-domain dotted pipe codes. Fix: position-preserving rename of the `[pipe.<domain>.<code>]` key to `<code>` plus rewrite of every internal reference. **Gate first, build second.**

### C.1 — Rename-mechanics spike (timeboxed, go/no-go)

- [ ] Timeboxed spike: can tomlkit rename a table key **position-preserving** (no `del`+re-add reordering, comments intact)? Investigate container-body manipulation; prove with a throwaway golden test.
- [ ] Confront the **array-of-tables addressing gap**: `steps[].pipe` / `branches[].pipe` rewrites need to address items inside arrays — decide the `FixOp` extension (index path segments vs a dedicated op) or conclude the shape can't express it cleanly.
- [ ] **GO/NO-GO decision** recorded in the design doc and the master plan (step 2 exit requires it either way). NO-GO → skip to CHECKPOINT C with the verdict; the rule stays out of wave 1 rather than shipping a reordering bug or a contorted op shape.

### C.2 — Implementation (only on GO)

- [ ] Enrichment: typed raise for the dotted-code sites (`pipelex_bundle_blueprint.py:121-123`, :146-148) carrying the offending code structurally; categorizer unwrap (kill the message matching for this error type).
- [ ] Planner guards: strip only when the prefix equals the bundle's own domain; suppress on collision (bare code already declared); never rewrite cross-package qualified refs. (Salvage reference: the old branch's `_should_strip` — semantics to be confirmed against its code, reimplemented under TDD.)
- [ ] Ops: `rename_table_key` implementation in the applier + reference-rewrite ops driven by `collect_pipe_references()` (`main_pipe`, `steps[].pipe`, `branches[].pipe`, `branch_pipe_code`, `outcomes` values, `default_outcome`).
- [ ] Add `new_key` to `_fix_fingerprint` in the same change (deferred item 1b — rename ops differing only in `new_key` must not collide).
- [ ] Golden tests: rename preserves position/comments; every ref site rewritten; idempotence; collision suppression.

### 🛑 CHECKPOINT C — hard stop before step exit

- [ ] **Verify**: `make agent-check` green; full `make agent-test` green (on NO-GO too — C.1's throwaway must not leak into the tree).
- [ ] **Record for cold start**: update this file with the GO/NO-GO verdict and (on GO) decisions on op-shape extensions; design doc updated. Commit.
- [ ] **Review fan-out** (only if C.2 produced changes): Sonnet-5 sub-agent running `/code-review` on the Phase C diff only, no inherited context — diff pointer only. Triage, fix, defer, commit.

## Phase D — step exit (= master-plan CHECKPOINT 1)

- [ ] **Abstraction verdict** recorded in the design doc: did `SuggestedFix`/`FixOp` survive multi-op fixes, delete-shaped fixes, the blueprint channel, and (if attempted) rename + array addressing unchanged — or what had to bend? This is the gate the human-CLI step (master-plan step 5) reads.
- [ ] strip-namespace decision reflected in the master plan (step 2 exit criterion).
- [ ] Full gates: `make agent-check` + `make agent-test` green.
- [ ] Update `wip/autofix/README.md` and the master plan "Where we are" section; mark step 2 done, note that step 3 (hardened loop / multi-file targeting — deferred items 0 and 1) is next and may already have partial groundwork from B.2's source threading.
- [ ] **Final review fan-out**: Sonnet-5 sub-agent running `/code-review` over the *entire* step-2 diff (`git diff <phase-0-sha>..HEAD`), no inherited context — diff pointer only. Triage, fix, defer, commit.
- [ ] Update this file to its final state (everything checked or explicitly moved to a deferred doc) so it can be rewritten as the step-2 PR reviewer's guide when the PR goes up — same lifecycle as the spike's.

## Decisions taken during this step (fill at checkpoints)

- A.1 prerequisite-guard layer: _pending_
- A.2 no-`inputs`-table op shape: _pending_
- B.1 error-type enum home: _pending_
- C.1 GO/NO-GO on strip-namespace (+ op-shape extension if GO): _pending_

## Out of scope for step 2 (already tracked elsewhere)

- Real multi-file targeting / `is_single_file` from resolved dirs — master-plan step 3 (deferred items 0, 1).
- `pipelex-agent fix bundle` command — step 4. Human CLI + `💡 Suggested fix` rendering — step 5 (gated).
- Changelog, docs page, conformance fixture regeneration, API pin bumps — step 6 (ship wave).
- Pruning rules — post-wave-1 (D4).
