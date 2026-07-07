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
- **In-place mutation, never rebuild** in the applier; golden byte-compare tests are the regression net for format preservation. *(Superseded from Phase A′ on: the applier stops owning canonical formatting and hands the serialized doc to `pipelex_tools.format_mthds`; goldens become the formatter's canonical output.)*
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

- [x] **Branch logistics.** PR #1027 still open from `feature/Autofix` → created stacked branch `feature/Autofix-step2` off it. Note: the docs-archival commit had already been pushed to `origin/feature/Autofix` (docs-only, harmless on the reviewed PR); step-2 code commits go on the stacked branch only.
- [x] Plan + archival move committed as `5e62bd43c` (phase-base SHA for checkpoint diffs).
- [x] Sanity: `make agent-check` and `make agent-test` green at base (verified 2026-07-07).

## Phase A — `sync-controller-inputs` (first multi-op, in-place table-sync shape)

Trigger: `MISSING_INPUT_VARIABLE` / `EXTRANEOUS_INPUT_VARIABLE` / `INPUT_STUFF_SPEC_MISMATCH` on a **controller** pipe. Fix: in-place sync of the `inputs` table with `needed_inputs()` — add/update/delete keys inside the existing table without rebuilding it. Because the enrichment carries the *full* expected mapping, one fix repairs all input drift for that pipe even though validation aborts at the first error.

### A.1 — Enrichment: `expected_inputs` on the typed error

- [x] RED: integration tests (`tests/integration/pipelex/pipeline/test_controller_inputs_enrichment.py`) — controller missing/extraneous/mismatch each carry the full mapping; cross-domain qualified ref pinned; PipeCondition missing-expression-var and unresolved-dep suppression pinned. Note: PipeLLM prompt-var missing/extraneous surface on the **blueprint channel** (static validation, message-reconstructed lookalikes) — pinned as such, they never reach the pipe-validation planner.
- [x] `expected_inputs: dict[str, str] | None` on `PipeValidationError` + error data. Also added `declared_inputs` (same rendering) — see A.2 decision.
- [x] Populated at the `generic_validate_inputs_with_library` raise sites where `the_needed_inputs` is in hand (missing-var, mismatch, extraneous), via `_expected_inputs_for_fix` gated on `self.is_controller`. The `required_variables()` site is **not** enriched: for controllers it fires for condition-expression vars whose needed spec comes from the declared inputs themselves (unknowable — and `needed_inputs()` would raise `InputStuffSpecNotFoundError` there); for sequences it never fires. Ref rendering factored into `StuffSpec.to_bundle_representation(relative_to_domain=...)`, reused by the PipeSequence enrichment (duplication removed).
- [x] **Optionals-marker guard**: declared spec matching needed on concept+multiplicity → author's declared rendering preserved (`?`/`!` kept); derived rendering only for added/changed variables. Pinned by `test_declared_optional_marker_preserved_in_expected_inputs`.
- [x] Threaded through `categorize_pipe_validation_with_libraries_error` (single function covers both the direct and pydantic-unwrapped call paths).
- [x] **Prerequisite-clean guard verdict: no guard code needed — validation ordering already guarantees it.** `validate_pipe_library_with_libraries` resolves every controller dependency first (raising `UNRESOLVED_PIPE_DEPENDENCY` immediately) and skips `validate_with_libraries()` for controllers with unresolved cross-package deps, so input-drift errors structurally cannot co-occur with unresolved-ref errors in one report and `needed_inputs()` is trustworthy wherever the input checks fire. Pinned by `test_unresolved_dependency_precludes_input_errors`.

### A.2 — Planner: multi-op fix

- [x] RED: planner unit tests — the input-drift error types (parametrized) → one SAFE `sync-controller-inputs` fix; suppression: no `expected_inputs` / no `declared_inputs` / no `pipe_code` / empty diff → `None`.
- [x] **Decision: the error data also carries `declared_inputs`** (the current declaration rendered exactly like `expected_inputs`), so the planner stays pure (no file access) and diffs the two mappings: `set_key` per added/changed variable, `delete_key` per extraneous one, order deterministic (expected order for sets, declared order for deletes). An empty diff (two concepts rendering to the same relative ref) yields `None` — a no-op fix would spin the loop into its fingerprint bail.
- [x] **No-`inputs`-table decision: single `set_key` on `["pipe", <code>]` with the whole mapping.** `TomlValue` widened to `TomlScalar | dict[str, TomlScalar]`; the applier writes dict values as a canonical inline table.
- [x] `description` is one line naming the variables added/updated/removed.

### A.3 — Applier + loop

- [x] RED: golden byte-compare fixtures (`tests/data/fixes/controller_inputs_{inline,block,missing_table}.mthds` + goldens) covering inline form, block form with comments, add+update+delete in one fix, idempotence.
- [x] **Applier finding (abstraction stress, resolved in-applier): tomlkit's incremental inline-table edits leave non-canonical whitespace** (double separator after a delete, no brace padding on fresh tables), which `plxt format` would churn — goldens could not be byte-stable. Resolution: the applier re-emits a *mutated inline table* with canonical `{ key = value, ... }` spacing (TOML forbids comments inside inline tables so nothing is lost; the line's trailing comment/indent is transplanted via trivia). Block tables stay strictly in-place. Fresh dict values are written as canonical inline tables.
- [x] Convergence tests: drifted controller inputs fixed in one iteration; **natural cross-rule cascade** pinned (inputs are validated before outputs, so the input error masks the output error — round 1 `sync-controller-inputs`, round 2 `match-sequence-output`).
- [x] Wire test: `sync-controller-inputs` rides `ValidationErrorItem` through the shared builder.

### 🛑 CHECKPOINT A — hard stop before Phase A′

- [x] **Verify**: `make agent-check` green; **full** `make agent-test` green (not just targeted tests).
- [x] **Record for cold start**: A tasks checked off, A.1 prerequisite-guard verdict and A.2 no-table decision recorded in "Decisions taken"; `SuggestedFix`/`FixOp` shape findings folded into the design doc (`TomlValue` widening, inline-table canonicalization).
- [x] **Review fan-out** (done 2026-07-07): Sonnet-5 `/code-review` sub-agent on the Phase A diff, no inherited context (diff pointer only). The agent fanned out multi-angle; it hit a session-limit mid-run but the angle reports were harvested. Triage outcome:
  - **Fixed (confirmed correctness defects):** (1) the inline-table canonicalizer crashed on supported dotted input keys (`"cv.name"` → `KeyAlreadyPresent`) and on nested inline-table values (whole-pipe inline form → `UnexpectedCharError`) — rebuilt to render via tomlkit natively + outer-brace-padding splice; pinned by two new applier regression tests. (2) `declared_inputs` was missing from `PipeValidationError.desc()` (asymmetry with `expected_inputs`) — added. (3) stale hardcoded line-numbers/counts in this file — removed.
  - **Design question raised by Louis** ("use plxt's Python lib to format?"): assessed NO — `pipelex-tools`/`plxt` is a dev-only dep (Rust binary, no Python API) and `plxt format` is whole-file; shelling out from the runtime fix loop would add a runtime toolchain dep and break the surgical "untouched lines stay byte-identical" contract. plxt stays the canonical-style oracle at golden-generation time; the runtime applier delegates rendering to tomlkit. Written up in the design doc.
  - **Deferred/reviewed (no over-engineering):** enum-match classifier duplication (house style, keep), trivia-preservation dup with `toml_sync`, per-`table_path` batch canonicalization (perf), `_*_for_fix` micro-duplication, two op-shapes early-warning, `FixOp.value` wire-schema forward note — all in `wip/autofix/deferred-checkpoint-a-review-items.md`.

## Phase A′ — adopt `format_mthds` as the canonical-output backend (do this cold-start)

**Decision (Louis, 2026-07-07): ADOPT.** Replace the applier's hand-rolled inline-table canonicalization with a single in-process `pipelex_tools.format_mthds` pass, and add `pipelex-tools-py` as a **core runtime dep**. This deletes the fragile formatting code (the crash-prone `_canonical_inline_table` string/native builders and the trivia transplant), guarantees zero drift from the toolchain's canonical style, and makes the applier crash-proof on any valid TOML. Two calls settled here: **(a)** core runtime dep, not an optional extra; **(b)** the applier's output philosophy shifts from "surgical byte-preservation of untouched lines" to "canonical whole-file MTHDS" — correct for a fix tool, and a no-op on already-formatted files (the norm: MTHDS is formatted on save + CI-enforced).

**Why before Phase B:** it deletes applier code that B (delete-shaped blueprint fix) and C (position-preserving rename) would otherwise extend; C's `RENAME_TABLE_KEY` gets simpler on a format-pass backend (no need to hand-preserve position formatting).

**Facts (verified 2026-07-07):**

- `pipelex-tools-py` (PyPI, import `pipelex_tools`) is a PyO3 **in-process** extension built from `../vscode-pipelex/crates/pipelex-py` — **distinct** from the `pipelex-tools` CLI-binary dev-dep already in `pyproject.toml`. Same `taplo` engine as the `plxt` CLI, fully offline (embedded MTHDS schema), ships PEP 561 stubs. Already a runtime dep of `pipelex-api` (precedent for a Python host calling it in a request path).
- `format_mthds(content: str, *, options=None) -> {"formatted": str, "changed": bool, "diagnostics": [Diagnostic]}`. Never raises on bad content (returns input unchanged + blocking `kind:"syntax"` diagnostics); raises `ValueError` only for a bad *option* value. Whole-document canonical reformat (aligns entries within a table, normalizes inline-table/array spacing) — matches what the extension writes on save.
- Our current goldens are already `format_mthds`-idempotent (`changed=False`, byte-identical, 0 diagnostics on all three), so migration is low-risk: `format_mthds(apply(fixture))` equals today's golden as long as the semantic edit is right.

**Tasks:**

- [ ] Add `pipelex-tools-py>=<pin>` to `[project.dependencies]` in `pyproject.toml` (via `uv`). Confirm `import pipelex_tools; pipelex_tools.format_mthds("a=1")` works in the pipelex venv. It's a compiled abi3 wheel — verify the CI/runner/worker platforms have published wheels (Ubuntu/macOS/Windows are).
- [ ] Integration point = `fix_loop.py`: after `apply_fix_ops` mutates the tomlkit DOM, serialize (`tomlkit.dumps`) → `format_mthds(dumped)["formatted"]` → that is the written text (and the text re-validated next iteration). Surface `diagnostics` defensively: any `kind:"syntax"` entry means the applier produced malformed TOML → that's a planner/applier bug, raise `PipelexUnexpectedError` (never silently write). `changed` is informational.
- [ ] Delete from `applier.py`: `_canonical_inline_table`, `_canonicalize_mutated_inline_table`, and the inline-table-building dict branch of `_as_tomlkit_value` (a plain dict value on the whole-mapping `SET_KEY` is fine — `format_mthds` canonicalizes it). `apply_fix_ops` stops canonicalizing; keep the SET/DELETE/DELETE_TABLE semantics and the guarded-skip contract intact.
- [ ] Regenerate goldens from the new pipeline (apply → `format_mthds`) and byte-compare. Expect ~no change (already idempotent). The F1 dotted-key and F2 whole-pipe-inline regression tests stay — they now pass by construction (the real parser can't crash on valid TOML).
- [ ] Update `suggested-fixes-design.md` (supersede the CHECKPOINT-1 canonicalization bullets with the `format_mthds` backend) and tick the now-moot deferred items in `deferred-checkpoint-a-review-items.md` (per-`table_path` batch canonicalization and the `toml_sync` trivia duplication both dissolve — no hand-rolled formatting left). Update the working-convention bullet at the top of this file.

### 🛑 CHECKPOINT A′ — hard stop before Phase B

- [ ] **Verify**: `make agent-check` green; **full** `make agent-test` green.
- [ ] **Record for cold start**: decisions + outcomes in this file and the design doc; commit (don't push).
- [ ] **Review fan-out**: Sonnet-5 sub-agent running `/code-review` on the Phase A′ diff only (`git diff <checkpoint-A-sha>..HEAD`), no inherited context — diff pointer only. Triage, fix real defects, defer tradeoffs to `wip/autofix/`, commit.

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

- A.1 prerequisite-guard layer: **no guard code** — validation ordering (deps resolved before any `validate_with_libraries`) makes co-occurrence impossible; pinned by test. The `required_variables()` raise site stays unenriched (condition-expression vars are unknowable).
- A.2 no-`inputs`-table op shape: **single `set_key` of the whole mapping on `["pipe", <code>]`**; `TomlValue` widened to allow a flat scalar dict, applier writes it as a canonical inline table. Companion decision: error data carries `declared_inputs` alongside `expected_inputs` so the planner can diff without file access.
- A.3 applier shape finding: mutated inline tables are re-emitted with canonical spacing (comment-safe by TOML grammar); block tables remain strictly in-place.
- B.1 error-type enum home: _pending_
- C.1 GO/NO-GO on strip-namespace (+ op-shape extension if GO): _pending_

## Out of scope for step 2 (already tracked elsewhere)

- Real multi-file targeting / `is_single_file` from resolved dirs — master-plan step 3 (deferred items 0, 1).
- `pipelex-agent fix bundle` command — step 4. Human CLI + `💡 Suggested fix` rendering — step 5 (gated).
- Changelog, docs page, conformance fixture regeneration, API pin bumps — step 6 (ship wave).
- Pruning rules — post-wave-1 (D4).
