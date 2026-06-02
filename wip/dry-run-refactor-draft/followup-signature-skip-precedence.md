# Follow-up — strict signature validation can be bypassed by a cross-package-SKIPPED pipe

**Status:** ✅ FIXED in-branch 2026-06-02 (see Resolution below) · **Severity:** medium (silent strict-mode false-negative) · **Surfaced:** `/review`, 2026-06-02 · **Branch of origin:** `feature/Validate-with-signatures-4-fix-dry-run`

## One-line

`BundleValidator.validate_pipes` runs the strict signature pre-pass over the **post-wiring-drop** pipe list (`sweepable_pipes`), so a pipe that is dropped to SKIPPED for an unresolved cross-package dependency is **never signature-checked** — a bundle that should fail strict `validate` (it contains an unimplemented `PipeSignature`) passes vacuously.

## Where

`pipelex/pipeline/bundle_validator.py` — `validate_pipes`:

```python
# step 1: wiring pass — drops PipeNotFoundError pipes to SKIPPED, out of sweepable_pipes
for pipe in pipes:
    try:
        pipe.validate_with_libraries()
    except PipeNotFoundError as not_found_error:
        results[pipe.pipe_ref] = DryRunOutput(... status=DryRunStatus.SKIPPED ...)
        continue
    sweepable_pipes.append(pipe)

# step 2: signature pre-pass — runs over the SURVIVORS only
if not allow_signatures:
    self._signature_pre_pass(pipes=sweepable_pipes)   # <-- the bug: should see the dropped pipes too
```

## Why it's a regression (verified against the deleted code)

The old `pipe_run/dry_run.py::dry_run_pipes` (now deleted) ran the aggregated signature pre-pass over the **full** input `pipes` list **first**, before any per-pipe `PipeNotFoundError` → SKIPPED determination (that determination lived inside `dry_run_pipe`, called only after the pre-pass). So the old order was: **signature pre-pass (all pipes) → per-pipe sweep (with SKIPPED tolerance)**. The new order is the inverse: **wiring drop (SKIPPED) → signature pre-pass (survivors)**.

This is the unintended interaction of two *individually correct* decisions:

- **D7** — run the `validate_with_libraries` wiring pass before the signature pre-pass (to preserve wiring-vs-signature error precedence across *different* pipes).
- **Phase-3a finding #1** — a controller referencing an *unloaded cross-package* sub-pipe is recorded SKIPPED and **dropped from both the signature pre-pass and the sweep**, rather than aborting the whole sweep (partial-bundle tolerance).

Neither decision is wrong on its own. Their composition is what leaks: "dropped from the signature pre-pass" silently widened from "this one pipe's wiring is incomplete" to "this one pipe's *signatures are also exempt*."

## Reproduction shape

A single controller (`PipeParallel` / `PipeBatch` / `PipeCondition`) that, in strict mode (`allow_signatures=False`):

- **branch A** reaches an unimplemented local `PipeSignature` (detectable — `collect_signature_refs` uses `get_optional_pipe`, so it still walks the resolved branch even when another branch is unresolved), **and**
- **branch B** references a cross-package pipe that is not loaded in this sweep (so `validate_with_libraries()` raises `PipeNotFoundError` and the pipe is dropped to SKIPPED in step 1).

Old: `SignaturesNotAllowedError` (or, on the main-CLI path, a hard `PipeNotFoundError`) — validation **fails**. New: the pipe is SKIPPED, no signature error raised — validation **passes**. This is exactly the incrementally-stubbed-bundle case `BundleValidator` is meant to police, so it is reachable in the intended workflow, not a contrived corner.

Affects every validate surface routed through `validate_pipes` / `acquire_and_validate`: `validate_bundle`, `validate --all` (main + agent CLI), builder `validate_*`, and `pipelex-api`'s build/validate routes. The hardened signature e2e does **not** cover it (those bundles have no unresolved cross-package dep, so no pipe is dropped before the pre-pass).

## Candidate fix (run the pre-pass over all pipes, before the drop)

```python
# step 2: signature pre-pass — run over the FULL list so a pipe dropped as
# cross-package-SKIPPED in step 1 still gets its signatures checked.
if not allow_signatures:
    self._signature_pre_pass(pipes=pipes)   # not sweepable_pipes
```

A bundle with a legit cross-package-unresolved dep but **no** signatures is unaffected (the pre-pass finds nothing, raises nothing, the pipe still classifies SKIPPED). Only the genuine "unimplemented signature hiding behind a wiring gap" case flips back to a strict failure. This restores the old `dry_run_pipes` precedence while keeping the Phase-3a SKIPPED tolerance for the no-signature case.

**Open question for the deliberate fix:** is "a pipe we can't fully wire is also exempt from signature checking" ever the *desired* strict-mode semantics? If yes, the precedence is correct as shipped and this doc should be closed with an inline comment at the pre-pass site documenting the choice. If no (the likely answer — strict signature mode is a stronger contract than wiring completeness), apply the candidate fix above with a TDD test for the intersection case:

> a controller reaching a `PipeSignature` via one branch AND an unresolved cross-package pipe via another branch → `SignaturesNotAllowedError` (not a silent SKIPPED-pass).

## Resolution (applied in-branch, 2026-06-02)

The semantics question above was answered **no** — strict signature mode is a stronger contract than wiring completeness, so a pipe we can't fully wire is NOT exempt from signature checking. Applied the candidate fix: `validate_pipes` step 2 now calls `self._signature_pre_pass(pipes=pipes)` over the full list (was `sweepable_pipes`), restoring the old `dry_run_pipes` precedence. A wiring-SKIPPED pipe with no signature is unaffected (the pre-pass finds nothing and it stays SKIPPED).

TDD: `tests/unit/pipelex/pipeline/test_bundle_validator.py::TestBundleValidator::test_signature_behind_cross_package_wiring_gap_still_raises` — a pipe dropped to SKIPPED in step 1 (unresolved cross-package dep) that also reaches an unimplemented signature now raises `SignaturesNotAllowedError` at the pre-pass, before any dry-run. Verified RED (DID NOT RAISE) before the fix, GREEN after. Full bundle_validator unit + integration + signature suites + signature e2e green; 777-test cli/pipeline/builder regression sweep green; `make agent-check` clean.
