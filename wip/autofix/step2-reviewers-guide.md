# Autofix — wave-1 rule breadth (step 2 reviewer's guide)

This branch delivers **step 2 of the autofix master plan**: three more fix rules, each a deliberately different fix *shape*, landed on the stacked branch `feature/Autofix-step2` (PR #1031, base `feature/Autofix` — stacks on the step-1 spike, PR #1027). Design docs: `wip/autofix/master-plan.md` (the step ladder), `wip/autofix/suggested-fixes-design.md` (architecture, per-checkpoint findings, the step-2 abstraction verdict). Reviewer's guide for step 1: `wip/autofix/spike-reviewers-guide.md`.

## The chain, in one pass

1. **`sync-controller-inputs`** (Phase A) — first multi-op fix. `PipeAbstract.generic_validate_inputs_with_library` (`pipelex/core/pipes/pipe_abstract.py`) is enriched with `expected_inputs`/`declared_inputs` (both rendered via `StuffSpec.to_bundle_representation`), gated on `self.is_controller` so operator raise sites stay unfixable. The planner (`planner.py`) diffs the two mappings into `set_key`/`delete_key` ops on the `inputs` table — one fix repairs all input drift for a pipe even though validation aborts at the first error. The applier mutates the inline/block table in place.
2. **Canonical-output swap** (Phase A′, mid-step) — the applier's hand-rolled inline-table canonicalization (crash-prone on nested/dotted keys) was replaced by a single `pipelex_tools.format_mthds` pass (`applier.serialize_and_format`), now a **core runtime dep** (`pipelex-tools-py`). Output philosophy shifted from "surgical byte-preservation" to "canonical whole-file MTHDS" — a no-op on already-formatted files. `apply_fix_ops` stays pure DOM mutation; `serialize_and_format` owns rendering and raises `PipelexUnexpectedError` on any `kind="syntax"` diagnostic (never silently writes).
3. **`strip-native-concept-redecl`** (Phase B) — first blueprint-channel fix and first delete-shaped fix in production. `validate_concept_keys` now raises a typed `NativeConceptRedeclarationError` carrying `concept_code`; a new blueprint-channel planner path (`plan_fix_for_blueprint_validation_error`) emits `delete_key` on `["concept"]`, which covers every authoring form (table, inline, dotted) because tomlkit represents them all as one `concept` table. First fix with a populated `SuggestedFix.source`, exercising the loop's source/`library_dirs` guard live.
4. **`strip-namespace`** (Phase C, stretch — **GO, shipped**) — the last unexercised op kind, `RENAME_TABLE_KEY`, proven end-to-end via tomlkit's private, position-preserving `Container._replace`. A typed `InvalidPipeCodeSyntaxError` carries `offending_code`/`stripped_code`, gated by `_strippable_same_domain_pipe_code` (same-domain prefix, valid bare tail, no collision). The feared array-of-tables `table_path` widening **never materialized**: same-domain qualified `steps[]/branches[]` references already resolve to the bare code, and only declaration keys + `main_pipe` enforce snake_case — so the fix touches only those two sites.

## Invariants a reviewer should check

- **Structural suppression throughout, never message-sniffing.** Each new fix keys off a field set only at the raise site that knows the correct value (`expected_inputs`, `concept_code`, `stripped_pipe_code`); the planner never re-derives or matches on error text.
- **`format_mthds` guarantee.** Every applier write goes through one canonical-format pass; a syntax diagnostic aborts loudly rather than writing malformed TOML. All new fixtures are `format_mthds`-idempotent.
- **Collision and ordering safety in the rename path.** `_rename_key_in_place` handles all three tomlkit container shapes (plain `Table`, `OutOfOrderTableProxy` with the pipe's fields split across interleaved chunks, inline `AbstractTable`) and renames the key in **every** chunk — the checkpoint-D fix for a pipe whose header and block `.inputs` straddle an intervening `[concept]` section (previously orphaned the block under a phantom key while reporting APPLIED). `main_pipe` retarget is collision-gated at the categorizer (`_main_pipe_strip_would_retarget`), and the fix loop pre-scans sibling bundles flat across **all** domains (`_sibling_pipe_codes`) before allowing a rename, bailing loudly rather than writing a colliding rename.
- **No abstraction drift.** `SuggestedFix`/`FixOp` absorbed multi-op, delete-shaped, blueprint-channel, and rename fixes with no structural change — the only wire edit was widening `TomlValue` to admit a flat scalar dict (Phase A.2). See the design doc's "Step-2 exit — abstraction verdict" section.
- **No behavior change for non-fixable errors.** All new fields are additive on already-`exclude_none` models.

## Test map

- `tests/integration/pipelex/pipeline/test_controller_inputs_enrichment.py` — Phase A enrichment (missing/extraneous/mismatch, cross-domain refs, optionals-marker preservation, PipeCondition suppression).
- `tests/unit/pipelex/pipeline/fixes/test_fix_planner.py` — `sync-controller-inputs` planning + suppression.
- `tests/unit/pipelex/pipeline/fixes/test_fix_applier_inputs_sync.py` + `tests/data/fixes/controller_inputs_*.mthds` — golden byte-compare (inline/block/missing-table forms).
- `tests/integration/pipelex/pipeline/test_native_concept_redecl_enrichment.py` — Phase B typed-error enrichment across authoring forms.
- `tests/unit/pipelex/pipeline/fixes/test_blueprint_fix_planner.py` — blueprint-channel planning for both B and C.
- `tests/unit/pipelex/pipeline/fixes/test_fix_applier_native_concept.py` + `native_redecl_*.mthds` — Phase B golden fixtures, idempotence, guarded skip.
- `tests/integration/pipelex/pipeline/test_strip_namespace_enrichment.py` — Phase C typed-error enrichment (rename + `main_pipe`, collision/cross-package suppression).
- `tests/unit/pipelex/pipeline/fixes/test_fix_applier_strip_namespace.py` + `strip_namespace_rename.mthds`/`.golden.mthds` — position/comment preservation, collision-skip, key-absent-skip.
- `tests/unit/pipelex/pipeline/fixes/test_fix_convergence_loop.py` — cross-rule cascades (inputs mask outputs; two redeclarations converge one per iteration; rename + `main_pipe` in one pass) and the checkpoint-D interleaved-chunk regression.
- `tests/unit/pipelex/pipeline/test_validation_errors.py` — all three fixes ride `ValidationErrorItem` through the shared builder.

## Known deferrals

Per-checkpoint deferred items (design tradeoffs, not defects) live in `wip/autofix/deferred-checkpoint-{a,a-prime,b,c,d}-review-items.md` — notably: `main_pipe`-to-nonexistent-pipe strip, the one-rename-per-iteration convergence cap, comment reflow on a deleted `[concept.X]` table, an upstream `pipelex_tools` stub/runtime-export mismatch. Real multi-file targeting and the `pipelex-agent fix bundle` command are out of scope for step 2 (master-plan steps 3–4).

## Next steps (not in this PR)

Master-plan step 3: hardened loop with real multi-file targeting (thread `file_path` from raise sites, fix `is_single_file` derivation) — may reuse Phase B's `SuggestedFix.source` threading. Then step 4 (`pipelex-agent fix bundle`), gated human CLI surfacing (step 5), and the ship wave (step 6).
