# PR #1099 review — deferred items

Deferred findings from the SWE-agent review triage of PR #1099 (Pipe-refs). Each was verified as real; they are deferred as judgment calls, not dismissed.

## Hardcoded domain literals in test blueprints (all-or-none sweep)

**Reporter:** cubic-dev-ai (three threads). **Verified:** confirmed, cosmetic.

Three PR-touched test files qualify `SubPipeBlueprint(pipe=...)` refs with a hardcoded domain literal even though the module defines a domain constant used elsewhere in the same file:

- `tests/integration/pipelex/pipes/controller/pipe_parallel/test_pipe_parallel_absence.py` — `"test_optionals_par.opt_par_find"` / `.opt_par_base` vs `_DOMAIN_CODE`
- `tests/integration/pipelex/pipes/optionals/test_liftable_pipes_inventory.py` — two hunks (sequence steps and parallel branches) vs `_DOMAIN_CODE`
- `tests/integration/pipelex/pipes/controller/pipe_parallel/test_pipe_parallel_unresolvable_structure_class.py` — `"test_usc.usc_branch"` vs `DOMAIN_CODE`

**Why deferred:** a verification sweep found the same pattern in six more PR-touched files that define a domain constant — `test_lift_sequence.py`, `test_lifted_parallel_companion_slots.py`, `test_optional_gate_tolerates_missing.py`, `test_parallel_optional_combine_validation.py`, `test_redundant_force_warning.py`, and `test_taint_sequence_validation.py` (the last with ~20 refs). Fixing only the three flagged files would make the tree *less* consistent than it is now; fixing all of them is a purely cosmetic sweep of dozens of edits on an already-large PR. All-or-none, in a dedicated cleanup — not piecemeal in review follow-ups.

**Recommendation:** if the sweep is done, interpolate the module constant everywhere (`f"{_DOMAIN_CODE}.xxx"`), matching the pattern in `test_pipe_parallel_branch_type_validation.py`. Note `test_pipe_structure_in_sequence.py` also hardcodes a domain prefix but defines no constant — it is not part of this pattern.

## Ambiguity as a first-class CLI outcome (design decision, round 2)

**Reporter:** cubic-dev-ai (two threads, both judged false positives on their stated claim). **Verified:** no authored contract is violated today.

The bot demanded exit 2 for ambiguous bare codes in `pipelex which`/`show`; that requirement exists only in cubic's auto-generated PR-summary block. The authored contract (changelog, `docs/building-methods/libraries.md`) promises a clean error naming the candidates, which holds and is test-pinned. But the triage surfaced a real open design question: `which` and `show` collapse *not found* and *ambiguous* into exit 1, so a script cannot tell the two apart; and there is no ambiguity-specific exception class for pipes — callers distinguish "a `PipeLibraryError` that is not a `PipeNotFoundError`", relying on subclass ordering (see `_validate_core.py`'s two arms). The workspace rule prefers structured verdicts over message-matching.

**If ever decided yes:** add `PipeCodeAmbiguousError(PipeLibraryError)` in `pipelex/libraries/pipe/exceptions.py` (mirroring `AmbiguousInputsFilesError`), raise it at both ambiguity sites in `pipe_library.py`, regenerate the error-identity snapshot and error pages (`make gei` / `make gep`), give `which`/`show` a dedicated exit-2 arm, and state the exit code in the changelog and docs (today neither does). It is a product decision about CLI contract, not a bug — exit 0/1/2 semantics are currently scoped to verdict-producing commands (`validate`/`fix`/`resolve`).

## Observations recorded in passing (no action decided)

- `pipelex/libraries/crate_qualification.py` — the cross-package **io**-ref deferral branch in `_qualify_io_ref` (`QualifiedRef.has_cross_package_prefix(io_ref) → return io_ref`) looks unreachable: `PipeBlueprint.generic_validate_inputs`/`generic_validate_output` reject any io ref that does not match `MULTIPLICITY_PATTERN`, and `alias->dom.Concept` cannot match it. Either cross-package concept refs in pipe io are intentionally illegal (making the branch and the module-docstring line about it dead) or the blueprint validator has a gap. Worth a one-line clarification when someone is next in that file.
- `pipelex/pipe_machinery/pipe_abstract.py` — `PipeAbstract.domain_code` is the one identity field with no validator (`code` has one). A `field_validator` calling `validate_domain_code` would make the `f"{domain_code}.{code}"` pipe-library key invariant structural instead of assumed, and would make the diagnostics-path `QualifiedRef.parse` calls in `pipelex/libraries/library.py` provably safe. Deliberately not done in review follow-ups — it widens the change surface for a state the loader already makes unreachable.
