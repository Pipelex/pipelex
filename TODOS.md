# Autofix — Phase 0 spike TODOS

**STATUS: NOT STARTED** (plan written 2026-07-07). Branch `feature/Autofix`, worktree `_autofix` (treat as repo root). Commit locally; do not push without Louis.

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

- [ ] Read the three wip/autofix docs; skim the old branch's `match_sequence_output.py` via `git show`
- [ ] Re-verify the code-map line refs and model field lists above; fix this doc where drifted
- [ ] Skim `test_validation_errors.py` + one bundle-validation test to learn fixture conventions (inline mthds content vs `tests/data/` files) and pick the fixture approach for the spike
- [ ] Green baseline: `.venv/bin/pytest -x -q tests/unit/pipelex/pipeline/`
- [ ] Settle the import-layering micro-decision (where `SuggestedFix`/`FixOp` live) — record it in this file

### 1 — Enrich the typed error (red-green)

- [ ] RED: test that a sequence bundle with a wrong output concept produces a `PipeValidationError` carrying the expected output ref (full bundle representation: concept + multiplicity + optionality marker)
- [ ] RED: same for the multiplicity-mismatch case, including a sub-pipe `output_multiplicity` override fixture
- [ ] GREEN: add the expected-ref field to `PipeValidationError`; compute it at both raise sites in `PipeSequence.validate_output_with_library` (salvage the override logic from the old branch)
- [ ] Thread the field through `categorize_pipe_validation_*` → `PipesAndConceptValidationErrorData`

### 2 — Fix wire models

- [ ] Define `FixOpKind` (`set_key` / `delete_key` / `delete_table` / `rename_table_key`), `FixOp`, `FixSafety`, `SuggestedFix` per the design-doc sketch, in the layering-safe home chosen at recon
- [ ] Add `suggested_fix: SuggestedFix | None = None` to `ValidationErrorItem`
- [ ] Tests: serialization round-trip; `exclude_none` keeps non-fixable errors byte-identical to today

### 3 — Planner

- [ ] RED: error-data with expected ref + `INADEQUATE_OUTPUT_CONCEPT` on a PipeSequence → `SuggestedFix(fix_code="match-sequence-output", ops=[set_key ["pipe", <code>] output = <expected>])`; multiplicity variant
- [ ] RED: suppression cases → `None`: PipeParallel/PipeCondition, missing expected ref, missing pipe_code
- [ ] GREEN: `planner` module (pure functions over error-data, keyed on `error_type` + structured fields, never message strings)
- [ ] Hook the planner into `build_validation_error_items`; extend `test_validation_errors.py` to assert fixes ride the wire items

### 4 — Applier (golden format-preservation tests)

- [ ] Fixture `.mthds` files with comments, mixed inline/block table styles, deliberate key ordering + `.golden.mthds` expected outputs after the fix
- [ ] RED: apply `set_key` → byte-equal to golden; idempotence (apply twice = same bytes); guarded application (op targeting a missing path is skipped and reported, not raised); basic `delete_key`/`delete_table` semantics
- [ ] GREEN: applier over a tomlkit DOM (in-place mutation, never rebuild containers), returning an applied/skipped report per op

### 5 — Minimal convergence loop

- [ ] RED: single-iteration fixture — fix applied, re-validate → `is_valid`
- [ ] RED: cascade fixture needing two iterations (nested sequences where fixing the inner one changes the outer one's expected output)
- [ ] RED: no-progress bail — same fix fingerprint proposed twice (e.g. its op targets a synthetic pipe so the applier skips it) → loop exits loudly with the bail reported, never spins
- [ ] GREEN: async loop reusing `validate_bundle` — validate → collect SAFE fixes → apply per file → re-validate; `max_iterations` default 5; fingerprint = (fix_code, source, table_path, key, value); result model with fixes_applied, iterations, final is_valid, remaining errors

### 6 — CHECKPOINT 0

- [ ] `make agent-check` green
- [ ] `make agent-test` green
- [ ] Update `wip/autofix/suggested-fixes-design.md` CHECKPOINT 0 with findings: did tomlkit in-place mutation preserve style as promised; final enriched-error shape; loop mechanics verdict; anything that changes Phase 1
- [ ] Update this file: check boxes, flip STATUS, record decisions taken + open questions; next step = master-plan step 2 (wave-1 engine)
- [ ] Commit on `feature/Autofix` (no push without Louis)

## Micro-decisions to settle during the spike

- [ ] Enriched field name: `expected_output_ref` vs a generic `expected_value` (later rules add their own per-family facts either way)
- [ ] Expose the expected ref on the `ValidationErrorItem` wire too, or keep it internal? (default: internal — the wire gets only `suggested_fix`)
- [ ] Use or delete the empty `PipelexBundleBlueprintFixableErrorType` stub
- [ ] Layering home for the fix models (see gotcha above)
