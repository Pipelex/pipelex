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

## Observations recorded in passing (no action decided)

- `pipelex/libraries/crate_qualification.py` — the cross-package **io**-ref deferral branch in `_qualify_io_ref` (`QualifiedRef.has_cross_package_prefix(io_ref) → return io_ref`) looks unreachable: `PipeBlueprint.generic_validate_inputs`/`generic_validate_output` reject any io ref that does not match `MULTIPLICITY_PATTERN`, and `alias->dom.Concept` cannot match it. Either cross-package concept refs in pipe io are intentionally illegal (making the branch and the module-docstring line about it dead) or the blueprint validator has a gap. Worth a one-line clarification when someone is next in that file.
