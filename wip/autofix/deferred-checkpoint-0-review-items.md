# Deferred items from Checkpoint 0 code review

Items surfaced by the clean-context code review of the Phase 0 spike (and the PR bot round) that are real but deliberately NOT addressed in the spike, per the no-over-engineering rule. Each belongs to an already-planned later step.

## 0. `is_single_file` must derive from the RESOLVED library dirs (Phase 1, with multi-file targeting)

Cubic finding, arbitrated VALID-but-DEFER. `fix_bundle_file` gates source-less fixes on `library_dirs is None`, which is wrong in both directions: an explicit `library_dirs=[]` is a documented "no libraries" value (`resolve_library_dirs` docstring) that IS single-file yet gets fixes dropped (safe-only over-filtering — reduced capability, never a wrong patch); and `library_dirs=None` can fall through to hub defaults or `PIPELEXPATH` and load OTHER files while the gate still calls it single-file. The band-aid one-liner (`not library_dirs`) would fix only the harmless direction. The correct fix — compute the gate from the resolved `effective_dirs` (`resolve_library_dirs(library_dirs)`) — is entangled with real multi-file targeting (item 1 below) and lands with it in Phase 1. No production caller passes `[]` today.

## 1. Real multi-file fix targeting (Phase 1)

The spike's convergence loop refuses to apply source-less fixes when `library_dirs` is set (`_applicable_safe_fixes` in `pipelex/pipeline/fixes/fix_loop.py`) — a safe no-op, not a solution. The review found the underlying gap: `SuggestedFix.source` is populated from `PipeValidationError.file_path`, and **no raise site in the codebase ever sets `file_path`**, so the source-based file check is dead code today. The scoping guard prevents the corruption scenario (same `pipe_code` in two domains → fix patches the wrong file's table), but multi-file bundles get no fixes at all.

Phase 1 must thread the declaring file into the enriched errors — either set `file_path` at the raise sites (the pipe/library layer knows the source file) or carry a domain qualifier the loop can check against the target file's `domain` key. Until then, `fix` only fixes single-file bundles. This matches the master plan's "hardened loop (multi-file targeting)" Phase 1 item.

## 1b. `_fix_fingerprint` must include `new_key` when rename ops land (Phase 1)

gstack pre-landing review finding, deferred. The no-progress fingerprint in `fix_loop.py` hashes each op as `kind:path:key:value` and omits `new_key` — two `rename_table_key` ops differing only in `new_key` would collide and trigger a false no-progress bail. Zero impact today (no planner emits rename ops; the applier raises for them). Add `new_key` to the fingerprint in the same Phase 1 change that implements position-preserving rename.

## 1c. Ship-wave changelog must mention the additive wire field

Once released, `suggested_fix` surfaces in `/validate` API payloads (additive, `exclude_none`). The master-plan step 3 changelog entry should call out the new optional field so API consumers know about it.

## 2. Cross-repo fixture regeneration (sync wave)

A fixture in our cross-repo spec suite pins the exact JSON body of an `INADEQUATE_OUTPUT_MULTIPLICITY` error from a live `pipelex-api`. Once this enrichment (`suggested_fix` on `ValidationErrorItem`, `expected_output_ref`) reaches the runner API via a pipelex release + pin bump, that fixture needs regeneration. Belongs to the already-tracked cross-repo schema-sync step (master plan) — nothing to do in this repo now.

## 3. Accepted as-is: unconditional `expected_output_ref` computation

`PipeSequence.validate_output_with_library` now computes `expected_output_ref` before the compatibility checks, so it also runs on the happy path. Reviewed and accepted: the cost is one string format + attribute reads on a validation (not execution) path, and computing it lazily would re-duplicate the code the change deduplicated. Not deferred work — recorded so a later reviewer knows it was a deliberate call.
