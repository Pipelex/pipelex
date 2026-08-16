# Deferred from the PR #1113 bot review

Three findings from the review bots on PR #1113 were verified as real and deliberately not fixed. Each is a decision rather than a defect, and each is written down here so the decision is taken on purpose rather than by omission. The rest of that review's findings were fixed in the same change.

Two further findings — an occupied `.bak.<stamp>` reported as this run's copy, and an `unsafe` entry reported at a spelling a later `safe` entry deletes — were already recorded, before this review, in [`migrator-write-scope-and-rename-fidelity.md`](migrator-write-scope-and-rename-fidelity.md) §3 and § "Residual". They are unchanged and are not repeated here.

## 1. `is_remappable` credits a union whose container branch it cannot reach

`is_remappable` in `pipelex/migration/narrowing.py` answers "can a `remap_value` on this path ever rewrite anything", and it answers yes when **any** top-level union member is string-typed. For `enum | list[enum]` that is true of the scalar branch, so the coverage gate credits a remap for the whole path — while the applier skips the list value because it is not a string. A file carrying the list keeps a retired spelling behind a green gate.

The reasoning is sound and the shape does not exist. The only scalar-plus-composite union on any registered surface is `cogt.img_gen_config.img_gen_param_defaults.size` → `SizeTier | ImageSize`, rendered `enum | table`. Its non-string branch is a `BaseModel`, and `_gather_enum_members` never descends into one, so every member recorded on that path genuinely does come from the string branch and the credited remap reaches all of them. Reaching the hole needs a branch that is *both* a container *and* enumerated — `enum | list[enum]`, `literal | list[literal]`, or `str | dict[str, enum]` — and none is written anywhere in `pipelex/`.

**Why it is not fixed here.** The fix is not local: `is_remappable` would have to ask "does any *non*-string branch carry enumerated spellings", which changes what the predicate means for every union path and which two accountings then read differently. The only test that can exercise it is one built on a model shape the repo's own standards discourage, so the guard would be pinned by a fixture and by nothing real.

**The decision to take.** Either take the change — `_records_enumerated_members` (added in this same PR for the container-widening fix) makes it about four lines — or leave the predicate as it is and say in its docstring that a union is answered by its string branches alone. Worth doing either way: **`is_remappable` has no direct unit test at all** today, only the indirect coverage-gate one, and it now gates two separate accountings.

## 2. Bounds are aggregated per kind across union members, losing which member each came from

`_fold_bound` / `_merge_carriers` in `pipelex/migration/fingerprint.py` merge the members of a union into one bound map, one constraint kind at a time. Which member a bound belonged to is gone by the time `narrowing.py` compares two versions, and the aggregate can then move in a direction the accepted values did not. Both directions were reproduced against the real projection:

- **A tightening that widened.** `int` → `Annotated[int, Field(ge=1)] | Annotated[int, Field(le=0)]` reports both a tightened lower bound and a tightened upper bound, into an aggregate box (`ge=1 ∧ le=0`) that is empty and that neither member has. Every value valid before is still valid; the domain strictly grew.
- **A narrowing that went unreported, which is worse.** `Annotated[int, Field(ge=1, le=10)] | Annotated[int, Field(ge=100, le=200)]` tightened to `ge=150` on the second member aggregates to `{ge: 1, le: 200}` on both sides. The gate says nothing while every file carrying `120` stops validating.

Reaching either needs a union with **two or more bound-carrying members**. There is none: the only union carrying any bound on any surface is `pipeline_execution_config.max_concurrency` → `Annotated[int, Field(ge=1)] | Literal["unbounded"]`, one non-empty pool, so the across-members fold never runs across anything.

**Why it is not fixed here.** The cheap-looking fix — drop a kind that is absent from some member's pool, the "honest union" — is family-blind: the fingerprint stores `gt` and `ge` as separate kinds and only `narrowing.py` knows they are one lower-bound family, so it would drop a real `ge=1` because a sibling member spells its lower bound `gt=0`. That converts the module's *preferred* error, an over-report the author can read and act on, into its *dispreferred* one, a silent under-report. Reading a union correctly means recording bounds per member in the golden and comparing member-wise, which is a fingerprint-format change and a comparator rewrite.

**The decision to take.** Leave it until a surface actually grows a union with two bounded members, then do it properly (per-member constraint sets in the golden). The docstring of `_fold_bound` was corrected in this pass to state the limitation instead of claiming, as it did, that symmetry makes inventing a narrowing impossible — it does not, once the member set moves.

## 3. A rescue copy can be pruned out from under the rename that was rescuing it

`keep_backup_for_rescue` in `pipelex/migration/backup.py` reserves the `.rescue.<stamp>` name and then renames `.bak.<stamp>` onto it. Between those two steps a *third* run of the same file can commit and call `prune_backups_except`, which deletes by name shape and so takes the `.bak.` copy the rename was about to move. The rename then fails, the reservation is cleaned up, and the function returns `RescuedBackup(path=backup_path, was_rescued=False)` — a path that no longer exists, which the report hands to the user with "copy it aside before the next successful run of this file".

Nothing is lost that was not already going to be pruned, and the run in question is one whose write it could not vouch for either way. What is wrong is the promise: the docstring said the returned path always names a file that exists.

**Why it is not fixed here.** Closing it means coordinating pruning with rescue across processes — a lock file — and pruning is deliberately name-shaped rather than ownership-aware. That is real machinery for a module that no command drives yet (`pipelex migrate` does not exist). The docstring was corrected in this pass to state the window rather than deny it.

**The decision to take.** Revisit when `pipelex migrate` lands and concurrent runs become something a user can actually produce. The honest lever then is probably not a lock but pruning that spares backups younger than some age, which fixes this and nothing else has to change.
