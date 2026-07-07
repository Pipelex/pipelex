# Autofix — Phase 0 spike TODOS

**STATUS: SPIKE COMPLETE — CHECKPOINT 0 cleared 2026-07-07** (plan written 2026-07-07). Chain proven end-to-end on `match-sequence-output`: enriched typed error → planner → tomlkit applier → convergence loop, all TDD, `make agent-check` + `make agent-test` green. Branch `feature/Autofix`, worktree `_autofix` (treat as repo root). Commit locally; do not push without Louis. **Next step = master-plan step 2 (wave-1 engine): remaining safe rules (`sync-controller-inputs`, `strip-native-concept-redecl`, `strip-namespace` if position-preserving rename lands clean), hardened loop (multi-file targeting).**

**Session hand-off (2026-07-07):** clean-context code review done + triaged. Findings: (1) multi-file corruption risk (a source-less fix could patch a same-named pipe from another domain, since no raise site sets `file_path`) → fixed with a minimal scoping guard in `fix_loop.py` (`_applicable_safe_fixes` drops source-less fixes when `library_dirs` is set) + `tests/unit/pipelex/pipeline/fixes/test_fix_loop_multi_file_scoping.py`; real multi-file targeting stays Phase 1; (2) conformance fixture staleness → belongs to the cross-repo sync wave; (3) unconditional `expected_output_ref` computation → accepted (trivial cost on a cold path). Deferrals recorded in `wip/autofix/deferred-checkpoint-0-review-items.md`. Next action = commit on `feature/Autofix` (checkpoint-0 commit; no push). New source surfaces: `pipelex/suggested_fix.py` (wire models), `pipelex/pipeline/fixes/{planner,applier,fix_loop}.py`; enrichment in `pipe_sequence.py` + `expected_output_ref` threaded through `core/pipes/exceptions.py` → `handle_pipe_errors.py` → `core/exceptions.py`; planner hooked in `pipeline/validation_errors.py`; `is_inadequate_output` property on `PipeValidationErrorType`; stub enum `PipelexBundleBlueprintFixableErrorType` deleted. Tests: `tests/unit/pipelex/test_suggested_fix.py`, `tests/unit/pipelex/pipeline/fixes/`, `tests/integration/pipelex/pipeline/test_sequence_output_enrichment.py`, `test_fix_convergence_loop.py`, golden fixtures `tests/data/fixes/`. Changelog deliberately deferred to master-plan step 3.

## What this is

Step 1 of the autofix master plan: prove the whole suggested-fixes chain end-to-end on ONE rule — `match-sequence-output` (a PipeSequence's `output` must equal its last step's output). Chain: **enriched typed error → fix planner → tomlkit applier → convergence loop**. TDD throughout (red before green). No CLI command in this spike — everything driven by tests.

Read first:

- `wip/autofix/master-plan.md` — the step ladder (this spike = step 1).
- `wip/autofix/suggested-fixes-design.md` — architecture, approved decisions D1–D4, wire-model sketch (`FixOp`/`SuggestedFix`), rule guards, salvage map.
- `wip/autofix/old-plan-to-auto-fix.md` — superseded old plan, reference only.
- Old branch salvage (do NOT check out): `git show feature/Bundle-fixer:pipelex/pipeline/fix_rules/match_sequence_output.py` — has the last-step output derivation incl. the sub-pipe multiplicity-override handling.

## Cold-start code map

Line refs verified 2026-07-07 — re-verify at recon, they will drift.

- `pipelex/pipe_controllers/sequence/pipe_sequence.py:63-115` — `validate_output_with_library`: THE enrichment site. Raises `INADEQUATE_OUTPUT_CONCEPT` (~:85, already carries `provided_concept_code` = last step's concept) and `INADEQUATE_OUTPUT_MULTIPLICITY` (~:98-110). Last step = `self.sequential_sub_pipes[-1]`; expected ref = last step pipe's `output.to_bundle_representation()` adjusted for the sub-pipe's `output_multiplicity` override.
- `pipelex/core/pipes/exceptions.py` — `PipeValidationErrorType` (:98), `PipeValidationError` (:149; fields: message, error_type, domain_code, pipe_code, variable_names, required_concept_codes, provided_concept_code, file_path, explanation).
- `pipelex/core/pipes/handle_pipe_errors.py` — `categorize_pipe_validation_*` helpers: exception → `PipesAndConceptValidationErrorData` (`pipelex/core/exceptions.py:29`). New fields must be threaded here.
- `pipelex/base_exceptions.py:268` — `ValidationErrorItem` (frozen, `extra="forbid"`, serialized `exclude_none`): the wire item every consumer reads; gains `suggested_fix`.
- `pipelex/pipeline/validation_errors.py:24` — `build_validation_error_items`: the ONE shared builder (CLI + API + MCP all flow through it) = planner hook point. Tests: `tests/unit/pipelex/pipeline/test_validation_errors.py`.
- `pipelex/pipeline/validate_bundle.py:222` — `validate_bundle` (the loop must reuse this wholesale — NO parallel validation pipeline, that was the old branch's cardinal sin); `_translate_to_validate_bundle_error` :94.
- `pipelex/tools/misc/toml_utils.py:53,:67` — `load_toml_with_tomlkit` / `save_toml_to_path` (style-preserving primitives; tomlkit already a dep).
- `pipelex/core/bundles/exceptions.py:8` — empty `PipelexBundleBlueprintFixableErrorType` stub from an earlier attempt: use or delete (micro-decision below).
- Multiplicity/marker grammar: `parse_concept_with_multiplicity` in `variable_multiplicity.py` (handles `[]`, `[n]`, `?`, `!`).
- Test home: `tests/unit/pipelex/pipeline/` (see `test_validation_errors.py`, `test_validate_bundle_helper.py` for conventions); `.mthds` fixtures live under `tests/data/`.

## Gotchas (learned from the drift analysis — don't rediscover these)

- **Import layering**: `ValidationErrorItem` is in `base_exceptions.py` (low-level). `SuggestedFix`/`FixOp` models must live somewhere `base_exceptions.py` can import WITHOUT a cycle — NOT in `pipelex/pipeline/fixes/`. Candidates: inside `base_exceptions.py` itself or a new low-level sibling module. Decide at recon; this codebase is import-cycle-sensitive.
- **Optionals markers `?`/`!`**: the expected output ref must carry the last step's optionality marker; verify `to_bundle_representation()` includes it.
- **Synthetic pipes**: `BundleElaborator` synthesizes sequences (`structuring_method = "preliminary_text"`) that have no TOML to patch → applier only applies an op if its target path exists in the DOM (guarded, skipped-not-raised).
- **Planner suppression**: `INADEQUATE_OUTPUT_CONCEPT` is also raised by PipeParallel/PipeCondition — their output choice is ambiguous, NO fix for them. Sequence-only.
- **tomlkit typing is weak**: use narrow `# pyright: ignore[...]` at specific lines, never the old branch's file-level blanket suppressions.
- **Keyword-only args**: bare `*` after the subject param, mechanically enforced by `make agent-check` (`docs/contribute/keyword-only-arguments.md`).
- Changelog entry deferred to master-plan step 3 (ship); no `[Unreleased]` churn from the spike.
- Commands: lint = `make agent-check`; targeted tests = `.venv/bin/pytest -x -q tests/unit/pipelex/pipeline/`; full suite at the end = `make agent-test`; if collection acts weird after moving files = `make cleanderived`.

## Tasks

### 0 — Recon

- [x] Read the three wip/autofix docs; skim the old branch's `match_sequence_output.py` via `git show`
- [x] Re-verify the code-map line refs and model field lists above; fix this doc where drifted — **no drift found, all refs accurate**
- [x] Skim `test_validation_errors.py` + one bundle-validation test to learn fixture conventions (inline mthds content vs `tests/data/` files) and pick the fixture approach for the spike
- [x] Green baseline: `.venv/bin/pytest -x -q tests/unit/pipelex/pipeline/` (92 passed)
- [x] Settle the import-layering micro-decision (where `SuggestedFix`/`FixOp` live) — record it in this file

**Recon decisions (2026-07-07):**

- **D-R1 — Fix-model home**: new low-level module `pipelex/suggested_fix.py` (imports only stdlib + pydantic), so `base_exceptions.py` can import it with no cycle. Not inside `base_exceptions.py` (fixes are not errors), not in `pipelex/pipeline/fixes/` (too high in the layering).
- **D-R2 — Enriched field name**: `expected_output_ref` (precise, self-documenting) over a generic `expected_value`. Carried on `PipeValidationError` and threaded to `PipesAndConceptValidationErrorData`.
- **D-R3 — Wire exposure**: `expected_output_ref` stays internal (error-data only); the wire `ValidationErrorItem` gains only `suggested_fix`.
- **D-R4 — Stub enum**: `PipelexBundleBlueprintFixableErrorType` is empty and referenced nowhere — delete it.
- **D-R5 — Planner keying/suppression**: planner fires on `error_type ∈ {INADEQUATE_OUTPUT_CONCEPT, INADEQUATE_OUTPUT_MULTIPLICITY}` AND `expected_output_ref` present AND `pipe_code` present. Only the two `PipeSequence` raise sites set `expected_output_ref` (verified: PipeParallel ×7, PipeCondition ×2, and 4 operator sites also raise `INADEQUATE_OUTPUT_CONCEPT` but never gain the field), so parallel/condition/operator errors are suppressed structurally, with the missing-field tests pinning it.
- **D-R6 — Expected-ref rendering**: bare concept code when the last step's output concept is same-domain as the sequence or native; qualified `domain.Code` otherwise (matches what an author would write; `to_bundle_representation()` alone would emit fully-qualified refs like `native.Text`). Multiplicity honors the sub-pipe `output_multiplicity` override; presence marker rides via `format_concept_with_multiplicity`.
- **Test homes**: enrichment + convergence loop = integration tests under `tests/integration/pipelex/pipeline/` (inline mthds strings + `load_empty_library` fixture, per `test_validate_bundle_structured_errors.py`); planner + applier = unit tests under `tests/unit/pipelex/pipeline/fixes/`; applier golden `.mthds`/`.golden.mthds` fixtures under `tests/data/fixes/`.

### 1 — Enrich the typed error (red-green)

- [x] RED: test that a sequence bundle with a wrong output concept produces a `PipeValidationError` carrying the expected output ref (full bundle representation: concept + multiplicity + optionality marker) — `tests/integration/pipelex/pipeline/test_sequence_output_enrichment.py`
- [x] RED: same for the multiplicity-mismatch case, including a sub-pipe `output_multiplicity` override fixture (`nb_output = 3`)
- [x] GREEN: add the expected-ref field to `PipeValidationError`; compute it at both raise sites in `PipeSequence.validate_output_with_library` (salvage the override logic from the old branch)
- [x] Thread the field through `categorize_pipe_validation_with_libraries_error` → `PipesAndConceptValidationErrorData`

### 2 — Fix wire models

- [x] Define `FixOpKind` (`set_key` / `delete_key` / `delete_table` / `rename_table_key`), `FixOp`, `FixSafety`, `SuggestedFix` per the design-doc sketch, in `pipelex/suggested_fix.py` (D-R1)
- [x] Add `suggested_fix: SuggestedFix | None = None` to `ValidationErrorItem`
- [x] Tests: serialization round-trip; `exclude_none` keeps non-fixable errors byte-identical to today — `tests/unit/pipelex/test_suggested_fix.py`

### 3 — Planner

- [x] RED: error-data with expected ref + `INADEQUATE_OUTPUT_CONCEPT` on a PipeSequence → `SuggestedFix(fix_code="match-sequence-output", ops=[set_key ["pipe", <code>] output = <expected>])`; multiplicity variant
- [x] RED: suppression cases → `None`: missing expected ref (covers PipeParallel/PipeCondition per D-R5), missing pipe_code, unrelated error type
- [x] GREEN: `pipelex/pipeline/fixes/planner.py` (pure function over error-data, keyed on `error_type.is_inadequate_output` + structured fields, never message strings)
- [x] Hook the planner into `build_validation_error_items`; extended `test_validation_errors.py` to assert fixes ride the wire items

### 4 — Applier (golden format-preservation tests)

- [x] Fixture `.mthds` files with comments, mixed inline/block table styles, deliberate key ordering + `.golden.mthds` expected outputs after the fix — `tests/data/fixes/`
- [x] RED: apply `set_key` → byte-equal to golden; idempotence (apply twice = same bytes); guarded application (op targeting a missing path is skipped and reported, not raised); basic `delete_key`/`delete_table` semantics
- [x] GREEN: `pipelex/pipeline/fixes/applier.py` over a tomlkit DOM (in-place mutation, never rebuild containers), returning a `FixOpApplication` report per op

### 5 — Minimal convergence loop

- [x] RED: single-iteration fixture — fix applied, re-validate → `is_valid` — `tests/integration/pipelex/pipeline/test_fix_convergence_loop.py`
- [x] RED: cascade fixture needing two iterations (nested sequences: fixing the inner surfaces the outer mismatch)
- [x] RED: no-progress bail — same fix fingerprint proposed twice (op targets a synthetic pipe so the applier skips it) → loop exits loudly with the bail reported, never spins — `tests/unit/pipelex/pipeline/fixes/test_fix_loop_bail.py` (stubbed validator)
- [x] GREEN: `pipelex/pipeline/fixes/fix_loop.py` — async `fix_bundle_file` reusing `validate_bundle`; `max_iterations` default 5; fingerprint = `fix_code|source|per-op(kind:path:key:value)` string; `FixBundleResult` with fixes_applied, iterations (apply rounds), final is_valid, remaining errors, bail_reason

### 6 — CHECKPOINT 0

- [x] `make agent-check` green
- [x] `make agent-test` green (full suite)
- [x] Updated `wip/autofix/suggested-fixes-design.md` CHECKPOINT 0 with findings (tomlkit style preservation confirmed; enriched-error shape; loop verdict; Phase-1 gotchas)
- [x] Update this file: check boxes, flip STATUS, record decisions taken + open questions; next step = master-plan step 2 (wave-1 engine)
- [ ] Commit on `feature/Autofix` (no push without Louis)

## Micro-decisions to settle during the spike

- [x] Enriched field name: `expected_output_ref` (D-R2)
- [x] Expected ref stays internal on error-data; the wire gets only `suggested_fix` (D-R3)
- [x] Deleted the empty `PipelexBundleBlueprintFixableErrorType` stub (D-R4)
- [x] Layering home for the fix models: `pipelex/suggested_fix.py` (D-R1)
- Decision taken mid-spike: `RENAME_TABLE_KEY` stays on the wire enum but the applier raises `PipelexUnexpectedError` for it (position-preserving rename = Phase 1, gated on strip-namespace mechanics; nothing emits it in the spike)
