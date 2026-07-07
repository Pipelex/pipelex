# Autofix — suggested fixes for `.mthds` validation errors (reviewer's guide)

This branch delivers **step 1 of the autofix master plan**: the whole suggested-fixes chain proven end-to-end on ONE fix rule — `match-sequence-output` (a `PipeSequence`'s declared `output` must equal its last step's effective output). There is deliberately no CLI command yet; everything is driven by tests. Design docs: `wip/autofix/master-plan.md` (the step ladder), `wip/autofix/suggested-fixes-design.md` (architecture, approved decisions D1–D4, checkpoint findings).

## The chain, in one pass

1. **Enriched typed error.** `PipeSequence.validate_output_with_library` (`pipelex/pipe_controllers/sequence/pipe_sequence.py`) computes `expected_output_ref` — the ref an author would write: bare concept code when same-domain or native, qualified `domain.Code` otherwise, with multiplicity (honoring the sub-pipe `output_multiplicity` override) and optionality marker rendered by `format_concept_with_multiplicity`. It rides `PipeValidationError` (`pipelex/core/pipes/exceptions.py`) and is threaded through `categorize_pipe_validation_with_libraries_error` (`pipelex/core/pipes/handle_pipe_errors.py`) into `PipesAndConceptValidationErrorData` (`pipelex/core/exceptions.py`). The validator states the semantic fact at detection time, so the planner cannot drift from the validator.
2. **Wire models.** `pipelex/suggested_fix.py` — a low-level module (stdlib + pydantic only) so `base_exceptions.py` imports it cycle-free: `FixOpKind` (`set_key`/`delete_key`/`delete_table`/`rename_table_key`), `FixOp`, `FixSafety` (`safe`/`unsafe`), `SuggestedFix`. `ValidationErrorItem` (`pipelex/base_exceptions.py`) gains `suggested_fix: SuggestedFix | None` — serialized `exclude_none`, so non-fixable error payloads are byte-identical to before (pinned by test).
3. **Planner.** `pipelex/pipeline/fixes/planner.py` — a pure function over error-data, keyed on `error_type.is_inadequate_output` (exhaustive-match property on the enum) + presence of `expected_output_ref` + `pipe_code`, never on message strings. Emits one SAFE `set_key ["pipe", <code>] output = <expected>` op. Hooked into `build_validation_error_items` (`pipelex/pipeline/validation_errors.py`) — the ONE shared builder every consumer (CLI/API/MCP) flows through.
4. **Applier.** `pipelex/pipeline/fixes/applier.py` — mutates a tomlkit DOM **in place, never rebuilds containers**, so comments, ordering, and table style of untouched content survive by construction (golden byte-compare tests pin it). An op whose target path is absent is skipped-and-reported, not raised (synthetic pipes have no TOML to patch); a malformed op raises `PipelexUnexpectedError` (planner bug). `rename_table_key` exists on the wire enum but the applier raises for it — position-preserving rename is Phase 1, nothing emits it yet.
5. **Convergence loop.** `pipelex/pipeline/fixes/fix_loop.py` — async `fix_bundle_file`: validate (reusing `validate_bundle` wholesale — NO parallel validation pipeline) → collect applicable SAFE fixes → apply → re-validate, to a fixed point bounded by `max_iterations`. Cascades are expected (validation aborts at the first `PipeValidationError`, so nested mismatches converge error-by-error). Non-convergence bails loudly via fix fingerprints (`fix_code|source|per-op` identity): a fingerprint proposed twice ends the loop with `bail_reason` instead of spinning.

## Invariants a reviewer should check

- **Structural suppression, not type-sniffing.** `INADEQUATE_OUTPUT_CONCEPT`/`_MULTIPLICITY` are also raised by PipeParallel, PipeCondition, and operator sites — their output choice is ambiguous, so they must get NO fix. Only the two `PipeSequence` raise sites set `expected_output_ref`; the planner's field-presence requirement suppresses everything else. Tests pin the missing-field → `None` behavior.
- **Multi-file scoping guard.** No raise site sets `PipeValidationError.file_path` today, so `SuggestedFix.source` is always `None`. A source-less fix is only provably targeted at the file being fixed under single-file validation — with `library_dirs`, a same-named pipe from another domain could resolve to this file's table (pipe codes are only unique per domain). `_applicable_safe_fixes` therefore drops source-less fixes when `library_dirs` is set: multi-file bundles get no fixes rather than a wrong patch. Real multi-file targeting is Phase 1 (`wip/autofix/deferred-checkpoint-0-review-items.md`).
- **Presentation stays out of the contract.** The fix ops are the contract; no rendered diffs, exit codes, or prose verdicts leak into the wire models.
- **No behavior change for non-fixable errors.** `suggested_fix` is additive and `exclude_none`; existing consumers see identical payloads.

## Test map

- `tests/integration/pipelex/pipeline/test_sequence_output_enrichment.py` — enrichment: wrong concept, multiplicity, `nb_output` override, optionality marker.
- `tests/unit/pipelex/test_suggested_fix.py` — wire round-trip, plain-string enum serialization, byte-identity for non-fixable items.
- `tests/unit/pipelex/pipeline/fixes/test_fix_planner.py` — planning + suppression cases.
- `tests/unit/pipelex/pipeline/fixes/test_fix_applier.py` — golden byte-compare (`tests/data/fixes/*.mthds` + `.golden.mthds`), idempotence, guarded skip, delete semantics.
- `tests/unit/pipelex/pipeline/fixes/test_fix_loop_bail.py` — no-progress fingerprint bail (stubbed validator).
- `tests/unit/pipelex/pipeline/fixes/test_fix_loop_multi_file_scoping.py` — source-less fixes dropped under `library_dirs`, still applied single-file.
- `tests/integration/pipelex/pipeline/test_fix_convergence_loop.py` — single-pass fix, two-iteration cascade (nested sequences), already-valid no-op.
- `tests/unit/pipelex/pipeline/test_validation_errors.py` — fixes ride the wire items through the shared builder.

## Known deferrals (deliberate, not gaps)

See `wip/autofix/deferred-checkpoint-0-review-items.md`: real multi-file fix targeting (thread `file_path` from raise sites — Phase 1); conformance fixture regeneration in the sibling `conformance/` repo (cross-repo sync wave, after a release reaches `pipelex-api`); `expected_output_ref` computed on the happy validation path too (accepted: trivial cost, laziness would duplicate code). One deleted surface: the empty, unreferenced `PipelexBundleBlueprintFixableErrorType` stub enum. Changelog entry is deferred to master-plan step 3 (ship wave) — the spike introduces no user-facing surface.

## Next steps (not in this PR)

Master-plan step 2 (wave-1 engine): remaining safe rules (`sync-controller-inputs`, `strip-native-concept-redecl`, `strip-namespace` if position-preserving rename lands clean), hardened loop with multi-file targeting, then the agent-CLI surface (wave 1, D3).
