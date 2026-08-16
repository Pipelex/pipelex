# S6 — Migrator Phase 3: working tracker

The charter is [`wip/migrator-3/sequencing.md` § S6](../../wip/migrator-3/sequencing.md) at the **workspace root** (from this repo: `../wip/migrator-3/sequencing.md`), with the phase content in `plan.md § Phase 3`. This file is the session-crossing record of what S6 has built, what it decided, and what is still open. Open the charter first, then this.

**Venue.** S6 lands as **two** PRs, not the one the charter assumes.

- **Part 1 — `feature/Migrator-3`: MERGED.** PR [#1113](https://github.com/Pipelex/pipelex/pull/1113), `dev` = `490d189df`. Milestones 1–4 below. The branch is deleted local and remote.
- **Part 2 — `feature/Migrator-3b`**, cut from `dev` = `490d189df`, **no upstream set** (first push is `git push -u origin feature/Migrator-3b`). This is the branch a new session works on. Milestone 5 onwards.

Record both numbers against S6.

✅ **Cold-start state (part 1, on `dev`).** Two commits, both pushed, working tree clean:

1. *"Migrator Phase 3, milestone 1: settle the golden format before S7 freezes it"*
2. *"Migrator Phase 3, milestones 2-3: what an unsafe entry promises, and catching a narrowing"* — milestones 2 and 3 together, plus the fixes from a `/code-review high` pass over them.

`make agent-check` and the full `make agent-test` are both green on the branch as pushed.

⚠ **S6 is well past half.** The pre-S7 bucket is closed (part 1, on `dev`), and on `feature/Migrator-3b` the two `migrate` commands (milestone 5), the downgrade diagnosis (milestone 6), boot tolerance (milestone 7), the validation-error report (milestone 8) and the telemetry-remedy retirement (milestone 9) are all built. What remains is the rest of the phase body — the `doctor` pending-migrations row and `--fix`, the drift-contract review list, the skills, the specs rows, and publishing the contract. See [What is actually left](#what-is-actually-left) at the bottom before planning a session.

## Build order chosen for this session

The charter lists a great many deliverables without an order. The order below was chosen so that everything touching the **golden format** happens first and the goldens are regenerated exactly once, before any other work can be built on top of a format that then moves:

1. **The golden-format bucket + the narrowing relation** — done, see below.
2. **R9 + the "what does `unsafe` promise" pass** — done, see Milestone 2 below.
3. **The applier's dotted-key rename policy, the backup/replace semantics pass, the `UNWRITABLE` wording** — done, see Milestone 3 below. That closes the "must be settled before S7" bucket.
4. **The commands** — `pipelex migrate`, `pipelex-agent migrate`, the rendering-rule test — done, see Milestone 5 below. The **downgrade diagnosis** (`unexplained[]`) was deliberately carried out of this milestone and is where the next session starts.
5. **The downgrade diagnosis** — done, see Milestone 6 below.
6. **Boot tolerance** — done, see Milestone 7 below.
7. **`report_validation_error` on the real plan** — done, see Milestone 8 below.
8. **The telemetry remedies retired** — done, see Milestone 9 below.
9. **The `doctor` pending-migrations row and `--fix` delegating to the migrate command** — not started. **This is where the next session starts.**
10. **The skills (`add-migration`, `/release` step 3b), the `config-docs` drift-contract review list, `command-surface-map.md` rows, publishing the contract in the nav** — not started.

## Milestone 1 — the golden-format bucket (DONE)

The charter required this to be *decided and recorded* in S6, before S7 freezes the format. All three questions are answered, the goldens were regenerated once, and the contract moved in the same change.

### (a) P — a binding bound merged with a union member's own

**Decided: the two sources do not merge the same way, and are intersected rather than pooled.**

`_collect_constraints` (`pipelex/migration/fingerprint.py`) used to flatten the field's own metadata and every union member's `Annotated` carriers into one list and take the widest of each kind. That recorded `le=100` for a field whose own `Field(le=6)` was the real ceiling — verified against pydantic, which applies the field-level bound on top of the member's. Now:

- the **binding** pool (field metadata, plus any `Annotated` wrapper met before a union) merges by **strictest**, because pydantic applies all of them;
- each **union member** gets its own pool merged by strictest, and the pools merge across each other by **widest**, because a union accepts a value if any member does;
- the two results are **intersected** (strictest), because a value must satisfy the binding bound *and* land in some member's domain.

One overclaim is kept deliberately and is now written down in the contract: a kind present on some members and not others is kept rather than dropped, so a tightening stays visible on the common `Annotated[int, Field(ge=1)] | Literal["auto"]` shape.

**No golden moved** — no live surface has the mixing shape.

### (b) `key = "*"` under a `remap_value`

**Decided: both halves of the "teach the applier" reading, not the "stop gathering" reading.**

- `RemapValueOp` now accepts `key = "*"`, meaning *each key of the addressed table*. The applier (`pipelex/pipeline/fixes/applier.py`, `_remap_every_value`) rewrites every string value the mapping names; any rewrite makes the operation `APPLIED`, none makes it `SKIPPED`, and a remap cannot collide so there is no conflict rule to invent. This is the **only** shape in which a member renamed beneath an open mapping can be repaired at all, since the keys are the user's.
- Every **other** kind refuses a `*` key when the op is parsed (`_refuse_wildcard_key` in `pipelex/suggested_fix.py`, on `set_key`, `delete_key`, `rename_table_key` both sides, `move_key` both sides). Unrefused they are *dead* operations — a literal lookup for a key spelled `*` that skips forever.
- `_gather_enum_members` now **stops at an open mapping's boundary**. The members belong to the `*` child record, whose own value is the enumerated one; recording them on the container as well made coverage demand a remap at a path whose value is a table, a demand with no legal answer. Every other container is still descended into — a `list[enum]` has no child record, so the list's own path is the only place a lost member is visible.
- Coverage now only **credits** a remap on a path a remap can reach (`is_remappable` in `narrowing.py`: the path's own value must be string-typed). For a `list[enum]` it names `unsafe` as the only remedy instead of offering a remap the author would write and never see fire.

**The one golden move of this session**, and the only one: `pipelex-config/fingerprint@1.json` lost the duplicated `enum_members` on `pipelex.log_config.package_log_levels`. `preferred_agent_targets` (a `list[enum]`) keeps its members, by design.

### (c) `list[Model]` recorded as a terminal `list[table]`

**Decided: the blind spot stays, and the reason is now in the contract.** Recording an item model's fields under a synthetic segment would make a renamed field inside an `OtlpExporterConfig` *visible* to the coverage gate — and then *demanded*, with no operation in the vocabulary able to address anything beneath an array of tables and therefore no remedy an author could write. A gate whose refusal has no legal answer is worse than a blind spot the contract names. The revisit trigger is recorded: the day an addressing syntax for arrays of tables exists, the two are one change.

### Alongside, in the same milestone

- **Q, the crying-wolf shapes in the narrowing relation** (relation only, no format move): a container whose argument widened (`list[int]` → `list[int | str]`) is now read structurally; `int` is absorbed by `float`; `enum` and `literal` absorb each other, since what moved between two member *sets* is `lost_enumerated_spellings`' to report; and over an integral type `gt=n` and `ge=n+1` are folded to the same bound, so the swap stops reading as a tightening. `_is_integral` sets the string-typed members aside first, so `int | literal` counts.
- **`umig` no longer rides in `make up`**, and refuses to overwrite a head golden recording a path, spelling or value domain the models lost (`_refuse_a_destructive_head_overwrite`, `MigrationSnapshotRefusedError`). The refusal names both readings — a real removal wants a bump and an entry, a format change over an unreleased version wants `make umigf` (new target, `--force`). This is what makes the *first* golden regeneration of this session an explicit act rather than muscle memory.
- **The head-link remedy text** in `coverage.py` now names the `make umigf` escape beside the bump, which was Session 9's finding.

### Files touched in milestone 1

```
pipelex/migration/fingerprint.py        binding/member constraint split; enum gathering stops at an open mapping; INTEGER_TYPE / REAL_TYPE
pipelex/migration/narrowing.py          is_remappable; structural container widening; int→float; enum↔literal; integral bound folding
pipelex/migration/coverage.py           credit only reachable remaps; head-link remedy text
pipelex/migration/snapshot.py           the head-overwrite refusal
pipelex/migration/exceptions.py         MigrationSnapshotRefusedError
pipelex/suggested_fix.py                _refuse_wildcard_key on every kind but remap_value
pipelex/pipeline/fixes/applier.py       _remap_one_value / _remap_every_value (the `*` key)
pipelex/cli/dev_cli/_dev_cli.py         --force on update-migration-schemas
pipelex/cli/dev_cli/commands/update_migration_schemas_cmd.py
Makefile                                umigf; umig out of `up`
docs/migration-ledger.md                the three decisions, the wildcard-key rule, the regenerator paragraph
pipelex/migration/goldens/pipelex-config/fingerprint@1.json    the one format move
tests/unit/pipelex/migration/test_fingerprint.py
tests/unit/pipelex/migration/test_narrowing.py
tests/unit/pipelex/migration/test_coverage_gate.py
tests/unit/pipelex/migration/test_ledger_check.py
tests/unit/pipelex/migration/test_snapshot_guard.py            (new)
tests/unit/pipelex/test_fix_op_union.py
tests/unit/pipelex/pipeline/fixes/test_fix_applier_migration_ops.py
tests/data/errors/error_identity.txt      regenerated (`make gei`) for the new error class
docs/errors/migration-snapshot-refused-error.md, docs/errors/platform-and-tooling.md   regenerated (`make gep`)
```

A new `PipelexError` subclass needs both regenerators, and neither is in `agent-check`: `make gei`
(the identity snapshot, caught only by the *full* `agent-test`) and `make gep` (the per-class
reference page, caught by nothing at all). `MigrationSnapshotRefusedError` is the one this session
added.

### Verified at the pause

`make agent-check` green. `make cl` green, `make cmig` green. `make umig` is a no-op on the tree as committed. Full `make agent-test` green — every test passed, working tree clean.

## Milestone 2 — what an `unsafe` entry promises (DONE, committed and pushed)

R9 (ruled option 2 on 2026-08-16) and the round-2 sibling — an `unsafe` entry silenced by a later `safe` rename of its target — were built as the single pass the charter asked for. The promise is now written once, in `docs/migration-ledger.md` § "What an `unsafe` entry promises":

> An `unsafe` entry is reported on every run, to every file that still carries the material it is about — at whatever spelling that material has reached — and to no other file.

### The two halves

**(a) R9 — the entry declares what it is about.** `MigrationEntry.declared_narrowed_paths` is a new ledger field carrying the paths whose *value domain* narrowed, spelled as the fingerprint at the entry's own version records them (`*` included). An op-free entry must carry one (refused at parse otherwise, since it could be reported to nobody, ever); a `safe` entry may not carry one at all (a narrowing a remap repairs is that remap's business, one it cannot repair is what `unsafe` means). `check-ledger` gained `DECLARED_NARROWED_PATH_IS_ABSENT`: a declared path the entry's own version does not record is either a misspelling or a *removal*, and a removal is accounted for by the operation that removes it.

**And the coverage gate no longer accepts the bare word.** `_check_narrowing_accounting` and `_check_enum_accounting` used to `return []` for any `unsafe` entry. They now require the narrowed / member-losing path to appear in `declared_narrowed_paths`. Without that, R9 would have been half-built: the ledger would accept a declaration and the gate would never ask for one.

**(b) The sibling — material moves, and the entry follows it.** New module `pipelex/migration/material.py`: pure ledger arithmetic (no fingerprint, no model, no filesystem, so the engine stays the function the gates replay) that traces an entry's material **back** through the entry's own operations — it is never applied, so a file it blocks keeps the previous spelling — and **forward** through every later `safe` entry. A later `unsafe` entry moves nothing (never applied); material a later entry deletes stops being traced. `unsafe_op_variants` respells the operations' **sources only**, because only the source decides whether the rehearsal would do something.

**Scope boundary, deliberate and recorded in the contract: a rehearsal may guess, an application may not.** Forward tracing is confined to `unsafe` entries, whose operations are rehearsed against a copy and discarded — the worst a wrong guess costs is one report too many. A **`safe`** entry silenced the same way (by its own `CONFLICT`, after which a later entry renames the table around it) has the identical mechanism and is left alone, because repairing it would mean *writing* at a spelling its author never wrote. **That is an open question for a later session** — it is a question about what a `safe` entry promises, and it was not in R9's scope.

### The collision this uncovered, and how it was resolved

The declaration's predicate is **presence**, not violation — the engine is model-free by design, and R9's ruling explicitly refused to thread a model into it. So a *current* reference document sets the narrowed path like every healthy file does, the entry speaks, and `_check_convergence` refused the ledger: **R9's ruled shape was unbuildable as first written** (reproduced before it was fixed).

Resolved as narrowly as it can be: a third `BlockedEntryReason`, `VALUE_DOMAIN_NARROWED`, weaker than `UNSAFE` — *this file sets a key whose accepted values narrowed, check it by hand*, versus *this file has the old shape*. Convergence exempts that reason and nothing else; an `unsafe` entry whose **operations** fire on a witness still fails, because that says the checked-in reference document carries retired material. `BlockedEntry.narrowed_paths` lists the paths **as the ledger spells them** (`levels.*`, never the user's own `levels.my_package`), so the rendering rule holds for keys as well as values.

### Files touched in milestone 2

```
pipelex/migration/material.py        NEW — back/forward tracing of an entry's material through the ledger
pipelex/migration/ledger.py          declared_narrowed_paths + two validators
pipelex/migration/engine.py          the two predicates split; the new reason; ledger passed to the rehearsal
pipelex/migration/plan.py            BlockedEntryReason.VALUE_DOMAIN_NARROWED; BlockedEntry.narrowed_paths
pipelex/migration/documents.py       document_carries_path — `*` matches exactly one segment
pipelex/migration/ledger_check.py    DECLARED_NARROWED_PATH_IS_ABSENT; the convergence exemption
pipelex/migration/coverage.py        unsafe must declare, on both the narrowing and the enum half
docs/migration-ledger.md             § "What an `unsafe` entry promises" + the rules threaded through
CHANGELOG.md                         one Added bullet
tests/unit/pipelex/migration/test_unsafe_promise.py   NEW
tests/unit/pipelex/migration/{conftest,test_ledger_models,test_ledger_check,test_coverage_gate,test_transform_check}.py
```

The new tests were mutation-tested against the pre-fix engine: five of them go red, which is the guarantee they are meant to hold.

### Verified at the pause

`make agent-check` green, `make cl` green, `make cmig` green, and the full `make agent-test` green — every test passed.

## Milestone 3 — the write path: dotted keys, backups, and what a blocked file means (DONE, committed and pushed)

The last of the "must be settled before S7" bucket. Three things the charter listed separately turned out to be one pass over the code that actually touches a user's file.

### (a) The dotted-key rename — fixed at the root, not refused

The defect reproduced immediately and is worse than the round-3 note recorded. `[a]` / `k.x = 1` / `m = 3`, rename `k` → `kk`, gives `[a.kk]` with **`m` beneath it** — `a.m` became `a.kk.m`, verdict `applied`, nothing said. Renaming an *inner* segment of `k.x.y = 1` re-rendered the chain as a top-level `[k.xx]`, moving the subtree out of `[a]` entirely and leaving `a` empty. Both are silent data corruption on an ordinary TOML layout.

**Root cause:** dotted-ness is a private flag tomlkit's parser sets on the key, not a property of the name, and `Container._replace_at` builds a fresh `SingleKey` whenever the name changes. The renderer then emits a block header — and a block header absorbs every scalar after it in the same table.

**Decided: preserve, do not refuse.** A rename has exactly one correct answer on a dotted key, the layout is ordinary TOML no formatter rewrites, and refusing would strand the reshape's table renames on any file written that way. Same shape as round 3's stale `display_name`, fixed the same way.

`_replace_key_in_container` no longer calls `Container._replace` at all; it renames the container's body entries where they sit. That drops three things the primitive did that a *rename* has no business doing: losing the dotted flag, collapsing a key written as several dotted lines into one rebuilt value (the dict facade for that shape holds only the last chunk), and injecting a cosmetic blank line after the renamed table. Index bookkeeping stays byte-for-byte what `_replace_at` did, **including its asymmetry** — the raw-storage staleness is deliberately not half-repaired here, because the stale facade for a nested rename is the parent `Table`'s own dict, a different object holding items rather than values. Repairing every facade kind is its own pass; `test_fix_applier_rename_dom_consistency.py` now says so and pins both halves.

### (b) The backup and replace semantics pass

Five questions, five policies, all written into the contract's "Backups" paragraph:

- **A run never overwrites or removes a copy it did not make** (M). The stamp resolves to the second, so two runs can address one name; `write_backup` now *reserves* it with an exclusive create and keeps whatever is there — an older copy is the original, if anything is — and reports `was_created` so `_discard_backup` skips a copy this run merely found. The reachable damage was a concurrent run's refused write unlinking the other run's real backup.
- **Symlinks are followed** (N). The runner resolves before reading, exactly as the `.mthds` fix loop already resolves its own targets, so the two callers of the shared primitive now agree and `file_transaction.py` needed no change. The plan keeps naming the walked path; the backup lands beside the file that was actually rewritten.
- **A copy the run cannot vouch for leaves the rotation.** It is renamed `.bak.` → `.rescue.`, which `existing_backups_of` does not match, so the next successful run cannot prune away the copy the report told the user to go and get.
- **Ownership, ACLs and xattrs are not carried across** — decided, documented, not implemented. An atomic replace cannot preserve what the process has no right to set, and re-attaching an attribute blindly (a quarantine flag, a security label) is a worse guess than leaving it off. Mode is carried, and that is the security-relevant bit.
- **A directory `fsync` is owed, once** — after the backup lands, before the target is replaced. That is what makes "back up first, replace second" hold across a power loss. The target's own replacement is deliberately not synced: always-replay means a migration lost to a crash is replayed, while a lost backup is lost.

### (c) `UNWRITABLE`, and the reason enum

The round-3 reading is confirmed: for the single-file commit the runner performs, a failed replace re-raises its own `OSError`/`FixWriteConflictError` (a rollback of nothing is trivially complete), so the only `FixTransactionError` reaching a plan is the post-commit cleanup one. `FileBlockedReason` now carries one member per **state the file is in** rather than per exception caught — `UNREADABLE`, `UNPARSEABLE`, `UNWRITABLE`, `CHANGED_DURING_RUN`, `STATE_UNCERTAIN` — each with its own docstring and a row in the contract. `STATE_UNCERTAIN` is the only one that cannot promise the file is as it was found, which is exactly why it is not folded into `UNWRITABLE`: the next move is to compare against the rescue copy, not to fix a permission and re-run. Its wording no longer asserts which way the write went, because the runner genuinely cannot tell — only that the file does not hold what it wrote.

### Files touched in milestone 3

```
pipelex/pipeline/fixes/applier.py    _replace_key_in_container rewritten; _renamed_key; _rehome_key_indexes
pipelex/migration/backup.py          WrittenBackup; name reservation; rescue names; directory fsync
pipelex/migration/runner.py          symlink resolution; the new reasons; rescue on an uncertain write
pipelex/migration/plan.py            FileBlockedReason: UNREADABLE + STATE_UNCERTAIN, all documented
docs/migration-ledger.md             "A rename changes a name"; the blocked-reason table; Backups rewritten
CHANGELOG.md                         a Fixed section
tests/unit/pipelex/pipeline/fixes/test_fix_applier_config_surface_shapes.py     the dotted red/green fixtures
tests/unit/pipelex/pipeline/fixes/test_fix_applier_rename_dom_consistency.py    re-aimed at the new implementation
tests/unit/pipelex/migration/test_runner.py                                     symlink, collision, rescue, the reasons
```

Every new runner test was mutation-tested: dropping the resolve, clobbering the backup, discarding unconditionally, skipping the rescue rename, and folding `.rescue.` back into `.bak.` each turn exactly the intended test red.

### Verified at the pause

`make agent-check` green, `make cl` green, `make cmig` green, `make docs-check` green, `make drift-check` green **with the changes staged**. Full `make agent-test` green.

## Already true before this session started (do not rebuild)

- **The directory walk's overlap refusal** — the S6 "Done when" item carried from the #1110 review — **is already built and tested**: `SurfaceRegistry.surface_for_file_name` raises `MigrationRegistryError` naming the file, and `tests/unit/pipelex/migration/test_surface_resolution.py::test_a_file_two_globs_both_claim_stops_by_name` proves it with the `pipelex_*.toml` / `*_local.toml` pair. It landed in Phase 2 ahead of schedule, and the synthetic pair stays — a two-claimant refusal needs two globs that both match, which no real file in the tree produces. **What is still owed** is the #1111 note-5 half, which is a *different* claim about a *different* specimen: that the walk is **non-recursive**, pinned with the real `.pipelex/inference/backends/pipelex_gateway.toml`. That file matches the `pipelex-config` tier glob but sits one directory down, and `files_by_surface_in_directory` skips anything that is not a file, so the walk never descends to it — which is exactly what the test would assert. That is a test, not a behaviour change, and it neither replaces nor re-aims the overlap test.

## Still open, in the charter's own words

Everything in [§ S6](../../wip/migrator-3/sequencing.md#s6--migrator-phase-3) not listed under Milestone 1 above. The ones that must be settled *here* rather than at S7:

- ~~**The dotted-key rename policy**~~ — done, see Milestone 3(a).
- ~~**The backup and replace semantics pass**~~ — done, see Milestone 3(b).
- ~~**The `UNWRITABLE` wording and the reason enum**~~ — done, see Milestone 3(c).
- ~~**R9**~~ — done, see Milestone 2. What it left open: **a `safe` entry silenced by its own `CONFLICT` plus a later rename** has the same mechanism and was deliberately not fixed, because repairing it means writing at a guessed spelling.
- ~~**The #1111 note-5 half** (the walk is non-recursive, pinned with the real specimen)~~ — done, see Milestone 5.
- ~~**The symlink write scope**~~ — decided in Milestone 5 and written into the contract: the write scope is the resolved target of any file the walk claims.

**The "must be settled before S7" bucket is closed.** Two named follow-ups came out of it, neither blocking: the tomlkit raw-storage staleness wants one pass over every facade kind (`Container`, `Table`, `OutOfOrderTableProxy`) rather than the half-repair a rename can reach; and the `safe`-entry sibling above.

Then the phase's own body: the two commands, boot tolerance, `report_validation_error`, the downgrade diagnosis, the telemetry-remedy retirement, `doctor`, the drift-contract review list (plus the four validator sites R8 names), the `add-migration` skill, `/release` step 3b, the `command-surface-map.md` rows, and publishing the contract in the nav.

## Milestone 4 — the review pass over milestones 2-3 (DONE, in the same commit)

A `/code-review high` over the staged changes produced five findings. Two were fixed, three were deferred with their options written down in [`wip/migrator-write-scope-and-rename-fidelity.md`](./migrator-write-scope-and-rename-fidelity.md).

**Fixed.** The `value_domain_narrowed` report named the spelling the document carried *when the replay reached the entry*, and the later `safe` entries of the same run then renamed the material before the file was written — so a run reporting `reporting.retries` handed back a file calling it `output.retries`. `material.py` gained `spelling_after_replay`, and the report now names the end of that forward trace. Separately, the `state_uncertain` detail promised the pre-migration copy was "kept" on paths where it had not been moved out of the pruning rotation at all — another run's copy, a taken rescue name, or a rename that would not go. `keep_backup_for_rescue` now returns `RescuedBackup(path, was_rescued)` and the report asks the user to take the copy now when it could not be secured.

**Deferred, with the decision spelled out for each.** The migration runner resolves symlinks without the write-scope guard its `.mthds` sibling pairs with `.resolve()`, so a configuration file symlinked outside every walked directory is migrated where it actually lives — keep it and say so, or guard it like the fix loop. A rename still renormalises the assignment's separator and drops a deliberate quoting, which is not a regression but sits against two claims made elsewhere in the same changeset. And a backup name already taken is reported as this run's copy — the documented policy working as designed, whose only misleading cases need a same-UTC-second collision from a non-run source.

The contract's symlink paragraph was trimmed in the same change: it claimed "the two callers of the shared transaction primitive now agree", which on the write-scope half they do not.

## Milestone 5 — the two `migrate` commands (DONE, on `feature/Migrator-3b`)

The first milestone of part 2, and the one the reshape is gated on: until `pipelex migrate` exists, merging the reshape strands every existing `pipelex.toml` in the field.

### What was built

**`pipelex/migration/run.py` — the aiming.** `runner.py` answers *how* a file is migrated and takes everything as a parameter, which is what lets the gates replay it over documents nobody writes. The new module answers *what a real run is aimed at*: the package's own registry, the ledgers shipped beside it, and `config_directories_to_migrate()` — the global `~/.pipelex/` then the project `.pipelex/`, each only if it exists, and a project rooted at the home directory walked once rather than twice. Both commands and (later) `report_validation_error` must aim at the same files, or a user is told one thing by their boot and another by their tool.

**`pipelex migrate`** (`pipelex/cli/commands/migrate_cmd.py`) plans, shows the plan, and asks; `--yes` skips the question, `--dry-run` stops after the plan. Two passes deliberately: the rehearsal is what the user is shown and asked about, the second is the one that writes, and where they disagree the transaction refuses rather than writing over work it never saw. Registered in `_CORE_COMMAND_ORDER` and added to the app callback's skip set, so no readiness check or deck notice runs ahead of a command whose whole point is a broken machine.

**`pipelex-agent migrate`** (`pipelex/cli/agent_cli/commands/migrate_cmd.py`) is the same run for a machine. **It writes only with `--yes`** — it cannot ask, so the default is the safe half of the question — and `--dry-run` is the explicit spelling of that default, which is the loop the charter names. The two together are **refused, exit 2**, rather than resolved: an agent that asks for both has a bug a silent winner would hide. `needs_attention` is the verdict and is deliberately not "did anything get written"; the exit code and the rendering are presentation.

`describe_op` is shared between them, and renders an operation from ledger-supplied material only.

### The end-to-end tests use the real shipped migration

The one thing that made an honest E2E possible today: **`telemetry-config@2` is a real entry about a real file**. A flat first-generation `telemetry.toml` fails `TelemetryConfig`'s `extra="forbid"` and breaks the boot right now, so the charter's "failing boot → migrate → boot succeeds" runs against the package's own `goldens/telemetry-config/before@2.toml` and the ledger the package ships — no fixture invented, no monkeypatching. `tests/e2e/pipelex/cli/test_migrate_commands.py` plants that file in a hermetic HOME **and** a flat `telemetry_override.toml` in a temp project (the tier the telemetry loader actually merges, which is what keeps the boot failure honest), then proves: the boot fails, both files are migrated, exactly one backup each holding what that file used to say, the report names both, and the boot succeeds. The agent loop (`--dry-run --format json` → `--yes`) is the same scenario read as JSON.

**The boot probe is `pipelex-agent models`** — the cheapest command that performs a full boot including the telemetry load. `pipelex show config` is *not* a probe: it exits 0 on a machine whose telemetry cannot load, because it never reads it. Worth knowing before inventing a lighter one.

**The bootstrap proof** plants a root key no model knows at the top of `pipelex.toml`, confirms a booting command exits 1 on it, and shows both `migrate` commands still run. A second test in the same class is the one that matters more: with that same broken `pipelex.toml` in place, a stale `telemetry.toml` beside it is **still migrated**. A command that ran but declined to do anything would pass the first test and be useless.

**The rendering rule**, on the two channels that exist: a realistic secret is planted as the old `project_api_key`, which the shipped entry *moves*, and asserted absent from stdout and stderr of four invocations (human dry-run, human apply, agent JSON, agent Markdown) while the migrated file demonstrably carries it. The third channel — the `migration` block on a configuration validation error — joins when `report_validation_error` lands, and the test's docstring says so.

### `min_supported_schema_version` now has a reader

The charter's "the command reads them or they go", settled for the floor by **giving it a reader** rather than softening the sentence. `declared_schema_version` (in `config_surface.py`, beside the strip that already lived there) reads the reserved `[meta] schema_version` **exactly as tolerantly as boot strips it** — a string, a float, a `bool`, a non-table `[meta]` are all "no declaration", because a malformed declaration boots fine and migration must not be stricter than the reader the key exists for. `migrate_file` refuses a file below its ledger's floor with a new `FileBlockedReason.UNSUPPORTED_SCHEMA_VERSION`, writing nothing. Dormant today (every floor is 0, and nothing writes the key) and pinned with a synthetic ledger; it earns its place the day a squash moves a floor.

Note what this uncovered: **a squash cannot actually be expressed today** — `check_entries_are_contiguous_and_named_for_their_version` requires entries to start at 2 and be contiguous — so the floor is a *declaration* the reader now enforces, not something derivable from the entries. That is worth knowing before anyone tries to squash a ledger.

`MigrationReport` gained `changed_plans`, `unexplained_plans` and `needs_attention`; `written_plans` and `blocked_plans` finally have readers. **`MigrationLedger.entry_for_version` still has none** — see below.

### Decisions taken in this milestone

- **The symlink write scope is settled and written into the contract**, closing §1 of `migrator-write-scope-and-rename-fidelity.md` in favour of keeping the current behaviour and saying so: *a migration's write scope is the resolved target of any file the walk claims*. The `.mthds` fix loop guards its scope because it is handed a bundle directory; a configuration directory is a place a user keeps links to files they own, and a dotfiles repository is the ordinary reason one is there. Refusing it would decline to migrate exactly the machines whose owner was most deliberate.
- **The walk is not recursive, and that is now pinned with the real specimen** (#1111 note 5): `.pipelex/inference/backends/pipelex_gateway.toml` matches the `pipelex-config` tier glob exactly. Both halves are tested — it is not claimed where it lives, *and* the same name at the top level is claimed — because without the second half the first would still pass if the glob stopped matching, and would be proving nothing about recursion.
- **The replay-time `TOMLKitError` catch got an honest message.** The parse now happens up front (for the floor read), so a `TOMLKitError` from the replay is an operation failing on a document that is valid TOML — an applier bug, not a bad file. It is still caught at the per-file boundary rather than aborting the walk, and the detail now says what it is.

### Files touched in milestone 5

```
pipelex/migration/run.py                          NEW — which directories, which registry, which ledgers
pipelex/migration/runner.py                       up-front parse; the floor refusal; the honest replay-error detail
pipelex/migration/plan.py                         UNSUPPORTED_SCHEMA_VERSION; changed_plans/unexplained_plans/needs_attention
pipelex/system/configuration/config_surface.py    declared_schema_version
pipelex/cli/commands/migrate_cmd.py               NEW — the human command + describe_op
pipelex/cli/agent_cli/commands/migrate_cmd.py     NEW — the machine command
pipelex/cli/_cli.py, pipelex/cli/agent_cli/_agent_cli.py   registration, ordering, the no-boot skip set
subject_grants.toml                               _render_markdown (positional-Callable protocol)
docs/migration-ledger.md                          NEW § "The commands"; the floor bullet; the blocked-reason row; the symlink decision
docs/tools/cli/migrate.md                         NEW user-facing page (+ index row, + mkdocs nav)
pipelex/cli/agent_cli/CLAUDE.md                   the migrate row and its markdown structure
CHANGELOG.md                                      two Added bullets
tests/e2e/pipelex/cli/test_migrate_commands.py    NEW — both commands, the bootstrap, the rendering rule
tests/unit/pipelex/migration/test_migration_run.py NEW — directories, walk depth, the floor, the reserved-key read
tests/unit/pipelex/migration/conftest.py          build_ledger gained min_supported_schema_version
.drift/acks/{cli-docs,config-docs}.toml           both contracts reviewed and acked
```

Mutation-tested: dropping the project directory from the walk, making `--yes` not write, removing the floor refusal, and making the walk recursive each turn exactly the intended tests red.

## Milestone 6 — the downgrade diagnosis (DONE, on `feature/Migrator-3b`)

`unexplained[]` had renderers on both commands and nothing ever put anything in it. It does now, and the charter's sentence about the downgrade direction — *"that diagnosis is computable from the ledger alone"* — turned out to be wrong and was corrected in the contract in the same change.

### Where it runs, and why there

**In the runner, on the document the run leaves behind.** `run.py` was the other candidate and cannot do it: on a dry run the migrated document exists only in memory, and re-reading the file afterwards would diagnose the *pre*-migration shape — reporting every stale key the ledger is about to repair. So `migrate_file` diagnoses `replay.text`, which is the only place that document is.

**It is the first thing in the migration package that needs a model, and the engine stayed model-free.** The question goes to the surface's *fingerprint*, not to the model directly, which is what keeps the new module (`diagnosis.py`) as pure as `material.py`: a fingerprint, a document, a ledger and the blocked entries in, a list of `UnexplainedPath` out. `compute_surface_fingerprint` moved off `snapshot.py` (the *regenerator*) and onto `Surface.fingerprint_at()`, where both readers can have it without the runner importing the golden-writing machinery. It costs about 2 ms per file and reads nothing but the package's own files, so the bootstrap property is untouched.

### The four rules that make the answer worth reading

- **A tree walk, not a diff of two flat path sets.** That is what buys the two properties a set diff cannot have: an unknown *table* is named once instead of once per key inside it, and the schema spelling of every ancestor is known by the time a child is reported.
- **A blocked entry answers for its own material.** An `unsafe` entry is never applied, so the old shape it is about is still in the file — already reported, by name, with the entry's guidance. Calling the same key an unexplained typo would contradict the report two lines above it. The subtraction **deliberately over-covers** (op sources plus `declared_removed_paths`, each also traced forward through later `safe` entries), because every path it removes is one the same report names in `blocked[]`. A `remap_value` contributes nothing: it moves a value and leaves the path where it was, so subtracting it would silence a real typo sitting at a remapped key. This is `MigrationLedger.entry_for_version`'s **first caller** — the #1113 review's open "remove it or keep it" question is answered by keeping it.
- **A key the user chose is never rendered.** Beneath an open mapping the schema says `levels.*` where the file says `levels.my_package`, and a typo *inside* such an entry is reported at `queues.*.retreis`. Same rule as `narrowed_paths[]`, and the walk gets it for free by carrying the schema spelling alongside the document path.
- **A document nesting below a path the schema says is a scalar is left alone.** That is a type error, which the model reports far better, and descending would invent unknown paths beneath a path the schema knows perfectly well. Together with the reserved-`[meta]` strip — performed exactly as boot performs it — that is what keeps the diagnosis silent on files it has nothing to say about.

### What the note says

One note for every finding, and deliberately so: *the current schema has no setting there, and no ledger entry retires it — either the name is a typo, or this file was written by a newer pipelex than the one running, so check whether you are on an older branch or an older build.* The two readings are indistinguishable to a schema that knows neither name, and guessing would send half the users to the wrong fix.

**A reserved-path cross-reference was considered and rejected.** `derive_reserved_registry` could say "this path was retired at version N and is still here" — but a reserved path surviving a replay means a *blocked* entry, which the subtraction above already accounts for, so the branch would never fire.

### The witnesses

- **Every real surface's reference document and kit template diagnose clean** (`test_real_surfaces.py`). Both are at the current schema by construction, so a finding in either is the diagnosis being wrong about our own schema rather than a stale document. It was green on the first run, which is what made the design trustworthy before any of the unit tests existed.
- **The e2e bootstrap fixture was already the specimen.** `_break_the_configuration` plants `not_a_real_setting = true` at the top of `pipelex.toml` — a root key no model knows and no entry removes — so the diagnosis is now asserted against the very file that breaks the boot, through the real binary. Both bootstrap tests changed exit expectation from 0 to **1**: `needs_attention` is now true on that machine, which is correct, and the second one is the better test for it — a broken `pipelex.toml` needing a human does not stop the stale `telemetry.toml` beside it from being migrated.

### Files touched in milestone 6

```
pipelex/migration/diagnosis.py         NEW — the walk, the blocked-entry subtraction, the note
pipelex/migration/documents.py         path_matches_pattern / path_is_at_or_under_pattern extracted; one definition of `*`
pipelex/migration/runner.py            _diagnose, on the migrated document
pipelex/migration/surfaces.py          Surface.fingerprint_at()
pipelex/migration/snapshot.py          compute_surface_fingerprint removed, calls the method
docs/migration-ledger.md               "The downgrade direction" rewritten; the unexplained rule in "What the engine reports"
CHANGELOG.md                           one Added bullet
tests/unit/pipelex/migration/test_diagnosis.py     NEW
tests/unit/pipelex/migration/test_real_surfaces.py the clean-witness over our own documents
tests/unit/pipelex/migration/test_migration_run.py the migrated-document-not-the-read-one pair
tests/unit/pipelex/migration/conftest.py           ExampleConfig grew the paths its fixtures' migrated documents carry
tests/e2e/pipelex/cli/test_migrate_commands.py     the diagnosis through the real binary; two bootstrap exit codes
```

`ExampleConfig` growing a `reporting` block is worth noticing rather than skipping: the synthetic surface's model now has to name the paths the synthetic *migrated* documents carry, or the diagnosis reports them and every runner test gains noise about something it was not testing.

Mutation-tested: dropping the reserved-meta strip, the open-node `*` fallback, the blocked-entry subtraction, the stop-at-an-unknown-table, the scalar-descend guard, the schema spelling, the remap exclusion, the forward trace, the `declared_removed_paths` source, and diagnosing the document as it was read each turn exactly the intended tests red.

## Milestone 7 — boot tolerance (DONE, on `feature/Migrator-3b`)

A stale configuration no longer stops the boot. Each surface's loader validates as it always did and, only when that fails, replays its ledger over the same files **in memory**, re-runs its own post-merge step, and validates again — booting with a warning that names the files and the `pipelex migrate` remedy. Nothing is written; a tolerated boot leaves the directory exactly as it found it, which is why the warning keeps coming back until the command is run.

**The shared helper owns the failure path, not the load** — `replay_surface_files_in_memory` in `config_surface.py`, which was already the home of the reserved-`[meta]` strip. The three loaders differ between their merge and their validate (programmatic overrides / `${VAR}` substitution / nothing), so a helper owning the whole load would have to know about all three. It takes the surface id and the same ordered path list the loader merged, and hands back the migrated merge plus a `MigrationPlan` per file. The overrides in particular are re-applied by the caller, because they are a layer of the *load* while the replay only sees the *files*.

### Three things the groundwork had wrong or had not seen

**The engine cannot be imported at module level, and the mechanical guard would not have caught it.** `pipelex/migration/engine.py` imports `pipelex.pipeline.fixes.applier` — `pipeline` is an *interpreter* package, and the configuration loaders sit in `runtime_hub`'s closure, the kernel layer whose stated property is that importing it loads zero interpreter modules. The previous session's groundwork checked the reverse direction only (that the engine pulls in no configuration model, which is true) and concluded a module-level import was fine. It is not. And `make agent-check` would not have caught it: `check-hub-layering` does reachability to `interpreter_hub`, which `pipeline.fixes.applier` does not reach, so the lint stays green. Measured rather than assumed — a module-level import there was tried, and it turns **nine** entry points of `tests/unit/pipelex/test_kernel_layer_import_closure.py` red while every gate in `agent-check` passes. Only the full `make agent-test` sees it. So the engine import is deferred into the retry — which also makes "the healthy path is untouched" literal rather than approximate. `migration.plan` and `migration.ledger` are clean and are imported normally.

**`PipelexConfig` does not raise `ValidationError`.** `ConfigRoot` gives itself a custom `__init__` that translates pydantic's error into `ConfigValidationError`, and pydantic v2 routes `model_validate` through a custom `__init__` — so the main configuration raises the translated one while a plain-model surface raises pydantic's. An `except ValidationError` would have switched boot tolerance off for the one surface everything depends on, silently and with every test passing. Both are caught, via `CONFIG_REFUSED` in `config_loader.py`.

⚠ **The same fact makes an existing branch dead, and it belongs to item 3.** `runtime_boot.py`'s `except ValidationError as validation_error:` around `setup_config` — the one that calls `report_validation_error(category="config", ...)` and raises `PipelexConfigError` — can never fire, because what `setup_config` raises is `ConfigValidationError`. Pre-existing, unchanged by this milestone, and precisely item 3's business, since that dead branch is one of `report_validation_error`'s two config-side callers. Verified by hand, not inferred.

**A failure *inside* the retry must never become the failure the user sees.** A missing ledger came back as `MigrationLedgerError` and replaced a legible "extra forbidden field: `not_a_real_setting`" with an internal path nobody can act on. The retry now declines on `MigrationLedgerError`; a broken packaged ledger stays loud where it should be loud (`make cl`, `pipelex migrate`). Same reasoning already applied to an unparseable file — and there the retry abandons *entirely* rather than skipping the file, because skipping drops a layer from the merge and a re-validation that then succeeded would boot on a configuration the user does not have.

### Decisions recorded in the contract

**Boot tolerance does not run the downgrade diagnosis.** On this path the model has already spoken, and pydantic's extra-field list is the same answer and a better one — it knows about validators, which a path walk does not. The diagnosis is for `pipelex migrate`, where nothing validates the file.

**The re-validation is what decides, and that is stronger than a second gate.** The contract's "unsafe entries, conflicts and unexplained paths still fail the boot" reads as a *description of why the re-validation fails*, not as an extra refusal on top of it: material an `unsafe` entry is about is still in the file, so the model refuses it; and a `VALUE_DOMAIN_NARROWED` report the model accepts was never a reason to refuse a boot, since that report says *check this key* and the model has now checked it.

### The two e2e tests changed premise, and a fourth finding came out of it

`test_migrate_commands.py` opened both of its end-to-end tests by asserting **the machine does not boot** — that was the scenario. Boot tolerance makes it boot, so the full `make agent-test` caught them (nothing in `agent-check` did). They now assert the machine boots on *both* sides of every command, which is the tolerance property itself, and the migration is still measured on the files.

⚠ **The agent CLI cannot see the warning, by contract.** The boot probe is `pipelex-agent models`, and `pipelex-agent` calls `silence_logging_for_agent_cli()` as its first act so nothing pollutes its two structured streams. So the e2e asserts the boot, not the warning — the warning is asserted per surface in `test_boot_tolerance.py`. The consequence is worth carrying into item 5: **a machine consumer never learns of a pending migration from a boot.** It has to ask — `pipelex-agent migrate --dry-run`, or the `doctor` pending-migrations row — which makes that row more load-bearing than it looked when it was listed.

### Where it landed

```
pipelex/system/configuration/config_surface.py     the helper, the warning builder, the three surface-id constants
pipelex/system/configuration/config_loader.py      config_file_paths extracted; load_config_validated; CONFIG_REFUSED
pipelex/system/telemetry/telemetry_config.py       the retry, re-running the ${VAR} substitution
pipelex/system/pipelex_service/pipelex_service_config.py  the retry, one file
pipelex/runtime_hub.py                             setup_config goes through load_config_validated
pipelex/cli/commands/plugins_cmd.py                same, for free
pipelex/migration/ledger.py                        packaged_migration_dir moved here off the registry
pipelex/migration/surfaces.py                      imports the surface-id constants instead of spelling them
docs/migration-ledger.md                           "Boot tolerance" rewritten against what was built
CHANGELOG.md                                       one Added bullet
tests/unit/pipelex/system/configuration/test_boot_tolerance.py   NEW
tests/e2e/pipelex/cli/test_migrate_commands.py     both e2e tests re-premised on a machine that boots
docs/tools/cli/migrate.md                          the boot warning is how users will meet the command
docs/contribute/hub-layering.md                    pipelex.migration accounted for (see the drift ack)
```

`packaged_migration_dir` moved off `surfaces.py` (the registry, which imports every configuration model) and onto `ledger.py`, so a loader can reach a ledger without reaching a registry. The surface ids are now constants in `config_surface.py` that the registry imports, so the loader and the registry cannot drift apart on a string literal.

The stale documents in the tests are **real** where they can be: `telemetry-config@2` and its shipped `before@2.toml`. The other two surfaces have empty ledgers, so their tests plant a synthetic one in a temporary migration directory via `packaged_migration_dir` — the wiring is what is under test there.

Mutation-tested: dropping the reserved-meta strip, skipping an unparseable file instead of abandoning the retry, abandoning on a missing file instead of skipping it, reporting a clean surface as stale, letting a ledger failure escape, merging the text as read instead of as replayed, dropping the programmatic overrides from the retry, catching only pydantic's `ValidationError`, re-raising from a failed retry instead of yielding, and building the warning from the file instead of from the ledger — each turned exactly the intended tests red.

⚠ **A process note worth keeping.** During that mutation loop a `git checkout <file>` reverted an *unstaged* edit and silently undid part of the milestone; the next three test runs were measuring a tree that no longer had the code. Mutation loops over uncommitted work must back up with `cp` and restore with `cp` — never with git.

## Milestone 8 — `report_validation_error` on the real plan (DONE, on `feature/Migrator-3b`)

The old `MigrationConfig` / `migration_maps` consumer is gone and a **dry-run scan of the surface that refused** has taken its place, riding the error twice: as a paragraph in the message and as the structured `migration` block a machine consumer branches on. `error_domain` stays `"config"`.

### The signature changed, and `category` did not survive it

`report_validation_error(*, category, validation_error) -> str` became `report_validation_error(*, validation_error, surface_id=None) -> ValidationErrorReport`. `category` selected a renaming map and had no other reader, so with the maps retired it named nothing; `surface_id` expresses the one asymmetry left — **naming a surface is what turns the scan on**. The two `.mthds` callers (`validate_bundle.py`, `library_manager.py`) and `runtime_boot`'s backend/deck helper name none, deliberately: none of those has a ledger, and a `pipelex migrate` remedy for a `.mthds` bundle sends a user to a command with nothing to do. That is pinned twice — no block, *and* the walk never happens.

`MigrationConfig` keeps `migration_maps` and loses both methods, with the reason in its docstring: the field is dead but the `[migration]` table ships and `extra="forbid"` would refuse every user file still carrying one, so the reshape entry is what removes both halves — sequencing rule 3. Two now-dead subject grants came out of `subject_grants.toml` with the methods.

### The block had to live in `base_exceptions.py`, and that cost a module move

`ErrorReport` references the block as a typed field, and `base_exceptions` cannot import the migration package: `plan.py` → `ledger.py` → `migration.exceptions` → `base_exceptions`. The precedent is `ValidationErrorItem`, which lives there for exactly this reason.

Rather than declare a second projection of `MigrationPlan` that would drift from the first, the cycle was **broken**: `MigrationSafety` moved out of `ledger.py` into a new `pipelex/migration/safety.py`, which leaves `plan.py` depending only on stdlib, pydantic, `safety` and `suggested_fix` — all already in `base_exceptions`' closure. `plan.py`'s docstring now states that constraint the way `suggested_fix.py` states its own. So `MigrationErrorBlock.plans` is `list[MigrationPlan]`: **the same shape `pipelex-agent migrate --dry-run --format json` emits under its own `plans` key**, and an agent that parses one has already parsed the other.

`migration` is deliberately **not** in `_STRICT_KEPT_FIELDS`, and the contrast with `validation_errors` is written beside it: validation errors describe the caller's own submitted bundle, a pending migration describes the *host's* configuration directories.

### Three defects found, all real, all fixed

**(a) Scoping the scan by building a one-surface registry silently corrupted the answer.** `SurfaceRegistry.surface_for_file_name` resolves ownership by *"an exact base file claims before any glob, **across all surfaces**"* — and its docstring names `pipelex_service.toml` as the very case it exists for, since that file is one surface's base file and a match for `pipelex-config`'s `pipelex_*.toml`. Handing `migrate_directories` a registry holding only `pipelex-config` removed the other claimant from that arbitration, so the glob won: the file was replayed under the wrong ledger and diagnosed against the wrong model, and its perfectly ordinary `agreement` and `onboarding` settings came back reported as *paths this build knows nothing about*. **Measured in a real run's stderr, not reasoned about.** The fix is `migrate_directories(only_surface_id=...)`: arbitration first with the full registry, filter second. Mutation-tested — reverting it turns the regression test red on exactly `pipelex_service.toml`.

**(b) The boot's `except ValidationError` around `setup_config` was dead**, as Milestone 7 predicted, and so was the doctor's. `PipelexConfig` is a `ConfigRoot`, whose custom `__init__` translates pydantic's error into `ConfigValidationError`, so neither arm ever fired for the one configuration everything depends on — a bad `pipelex.toml` produced a bare traceback rather than the field-level translation the arm existed to produce. Both now catch `CONFIG_REFUSED` and go through one shared `raise_config_setup_error`, with `pydantic_error_behind` (new, beside `CONFIG_REFUSED` in `config_loader.py`) reaching through either shape. A refusal carrying no pydantic error is re-raised as itself.

**(c) The agent CLI printed two error envelopes on one stream.** `agent_error` leaves through `typer.Exit`, which is a `RuntimeError` and **not** a `SystemExit`, so `models_cmd`'s `except SystemExit: raise` never caught it and the broad `except Exception` below reported it a second time. Two JSON documents on stderr is not JSON — `json.loads` gives *"Extra data"*. Pre-existing, and found because the new e2e is the first test to parse that stream instead of substring-matching it. Fixed at both sites (`models_cmd`, `check_model_cmd`) and pinned by an explicit single-envelope assertion.

**(d) And one trap this milestone introduced and closed in the same pass.** `MigrationPlan` carries real `Path` values, so `ErrorReport.to_dict()` — the documented serialization surface, handed straight to `json.dumps` by the webhook delivery path — could no longer be serialized once a block rode on it. Not reachable from a pipeline run today, since nothing raises a `PipelexConfigError` inside one, but leaving it would be a trap for whoever wires the next consumer. `to_dict` now dumps that one field in JSON mode; dumping the whole report in JSON mode would have re-serialized every other field and every round-trip with it. `from_dict` still round-trips, because pydantic accepts a string for a `Path`.

### Decisions taken in this milestone

- **The scan runs only on the failure path and only when a surface is named**, so it is a filesystem walk and a ledger replay that a healthy boot never pays for — and the migration import is deferred inside the function, for the kernel-layer reason Milestone 7 established (`core/validation.py` is in `runtime_boot`'s closure; `make agent-check` would not catch a module-level import, only the full `make agent-test`).
- **A failure inside the scan never becomes the failure the user sees**, same rule as the boot retry — but the catch is `(MigrationError, OSError)` rather than blanket, so an applier bug still surfaces as the bug it is. Both halves are tested.
- **The block is present iff the scan found something**, and only non-clean plans are listed. Absence is the verdict "this is not staleness", which is what "consumers branch on the block's presence" requires to mean anything.
- **The message is presentation** and carries the pydantic analysis plus a paragraph in the same order as `stale_configuration_warning`, because the two are read in the same places.

### Files touched in milestone 8

```
pipelex/migration/safety.py                       NEW — MigrationSafety, moved out of ledger.py to break the cycle
pipelex/migration/plan.py                         the low-level constraint stated; imports safety
pipelex/migration/ledger.py + 5 siblings + 7 test modules   re-pointed at migration.safety
pipelex/migration/runner.py                       migrate_directories(only_surface_id=...)
pipelex/migration/run.py                          scan_config_surface — the dry run, aimed at one surface
pipelex/base_exceptions.py                        MigrationErrorBlock; ErrorReport.migration; PipelexConfigError carries it
pipelex/core/validation.py                        REWRITTEN — the scan, the block, the prose, raise_config_setup_error
pipelex/system/configuration/config_loader.py     pydantic_error_behind, beside CONFIG_REFUSED
pipelex/system/configuration/configs.py           MigrationConfig: methods retired, field and reason kept
pipelex/runtime_boot.py, pipelex/cli/commands/doctor_cmd.py   the dead arms fixed, one shared helper
pipelex/cli/agent_cli/commands/agent_output.py    the migration block on the error payload
pipelex/cli/agent_cli/commands/{models,check_model}_cmd.py    the double-envelope fix
pipelex/pipeline/validate_bundle.py, pipelex/libraries/library_manager.py   .message, no surface
subject_grants.toml                               two dead grants removed
docs/migration-ledger.md                          NEW § "Reporting a stale configuration on a validation error"
docs/tools/cli/agent-cli.md                       the error envelope: one document, and the `migration` field
docs/tools/cli/migrate.md                         the boot-failure path names the command; the agent loop
docs/configuration/index.md                       the `[migration]` line, which the previous config-docs ack parked for here
pipelex/cli/agent_cli/CLAUDE.md                   the migration-field bullet
CHANGELOG.md                                      one Added bullet, two Fixed
tests/unit/pipelex/core/test_validation_report.py RE-AIMED — was about hub state, is now about the scan
tests/e2e/pipelex/cli/test_migrate_commands.py    NEW class: the third channel, through the real binary
.drift/acks/{config-docs,cli-docs}.toml           both reviewed and acked
```

Mutation-tested: building the scan's registry from one surface, dropping the JSON-mode dump of the `migration` field, widening the scan's catch to a blanket `except Exception`, and returning a block when the scan found nothing — each turned exactly the intended tests red.

The re-aiming of `test_validation_report.py` is worth noticing rather than skipping: its two tests existed because the helper *read the hub* and crashed when there was not one. It no longer touches the hub at all, so that concern moved — the bootstrap property is now that the **scan** runs on a machine with no hub and no configuration, which is where it is asserted.

⚠ **The e2e's boot assertion changed, and it is a contract change.** `TestTheBootstrapPath` asserted `"ConfigValidationError" in boot.stderr`; a boot failure now reports `PipelexConfigError`, which is the class that carries `error_domain: "config"` and the block. Anything downstream matching on that error type sees a different name.

## Milestone 9 — the two telemetry remedies retired (DONE, on `feature/Migrator-3b`)

Both of them told a user to re-initialize a file the shipped `telemetry-config@2` entry exists to carry forward. `pipelex init telemetry` **writes a fresh file**, so on the one case they named — the flat pre-`[custom_posthog]` format — the remedy discarded the PostHog key, the Langfuse credentials and the OTLP exporters it was supposed to be helping with. There turned out to be a third one, and a fourth site that was worse than any of them.

### There were four, not two

The tracker named `check_telemetry_config`'s old-shape sniff and `handle_telemetry_config_validation_error`'s banner. Also found and retired:

- **`AGENT_ERROR_HINTS["TelemetryConfigValidationError"]`** — the agent-side twin of the banner, and leaving it would have had the human CLI say `pipelex migrate` while the agent CLI said `pipelex init telemetry` about the same file.
- **`doctor --fix`'s prompt**, which is the one that could actually destroy something. `can_fix_telemetry` was `"format has changed" in telemetry_message.lower()`, and on a match `--fix` offered *"Reset telemetry configuration using the new format?"* → `init_cmd(focus=InitFocus.TELEMETRY)`. Answering yes on a migratable file rewrote it from the template.

That last one is also why the row could not simply be reworded: the message **was** the contract between the probe and the repair machinery, in three places (`display_health_report`, `do_doctor_cmd` twice). Rewording it would have switched the whole `--fix` telemetry path off in silence, with every test still green.

### What was built

**The error carries the answer.** `load_telemetry_config` now raises through `report_validation_error(surface_id=TELEMETRY_CONFIG_SURFACE_ID)`, so a `TelemetryConfigValidationError` carries the same `MigrationErrorBlock` a `PipelexConfigError` does. The message is byte-identical to before plus the migration paragraph — `format_pydantic_validation_error` is literally `analyze_pydantic_validation_error(exc).error_msg`, which is what `report_validation_error` builds on.

**`TelemetryConfigError` is now a `PipelexConfigError`.** It is one — and the reparenting is what gives it both halves for free: `error_domain = CONFIG` from the class (so its `AGENT_ERROR_DOMAINS` entry went, which `test_agent_output_drift.py` — the lookup-dict guard, not a drift *contract* — requires the moment a class declares its own) and the ability to carry a block. Checked every `except PipelexConfigError` site before doing it: `reporting_manager`, `tracing_assembly` and both doctors, none of which load telemetry — `setup_doctor_runtime` only does `setup_config`.

**The doctor row is a verdict, not a sentence.** `check_telemetry_config` returns a `TelemetryConfigCheck(finding, message)` over a new `TelemetryConfigFinding` — `HEALTHY`, `NOT_FOUND`, `UNPARSEABLE`, `OUT_OF_DATE`, `INVALID` — and every caller branches on it. `finding.is_repaired_by_initializing` is the property that answers the destructive question, and it is True for exactly one member: there is nothing in a file that is not there to lose. `OUT_OF_DATE` gets `pipelex migrate`, `UNPARSEABLE`/`INVALID` get a person, and regeneration is still offered on those two but described as what it is — *"start the file over, discarding what is in it"*. The agent doctor emits `finding` on the envelope and derives one recommended action per finding through a match/case.

### Two defects fixed along the way

**(a) The probe was stricter than the loader it reports on.** `check_telemetry_config` validated the raw document without `strip_reserved_meta`, so a `telemetry.toml` carrying the migration machinery's reserved `[meta]` table booted perfectly well and was reported invalid. Dormant today (nothing writes the key) and reachable the moment anything does.

**(b) The scan had to be scoped to the directory the probe read.** `scan_config_surface` gained `config_dirs`, because the doctor validates *one* resolved file — `--global` inspects `~/.pipelex/` — while the default walk is both directories. Without it, a stale global file would make a `--global`-inspected project file report `out_of_date`, sending the reader to a migration that does nothing for the file on their screen. Mutation-tested: reverting it turns two tests red.

### One I nearly shipped

The doctor's scan had no guard around it. Milestone 8's rule — *a failure inside the scan is never the failure the user sees* — costs more in the doctor than anywhere else: an exception escaping the probe reaches `doctor_cmd`'s own outer handler, which prints one line and exits, so a broken packaged ledger would have replaced **every row the user came for** with "Unexpected error". Caught in self-review, not by a test. The catch is `(MigrationError, OSError)` like the others, and both halves are now pinned — the fallback, and an applier bug still surfacing as itself.

### The module split this forced, and why it was the right answer

`make agent-check`'s pyright caught a **real import cycle**: `telemetry_config → core.validation → migration.run → migration.runner → migration.surfaces → telemetry_config`. `surfaces.py` builds the registry and therefore imports every configuration model, this surface's included.

**Deferring the import does not help** — `core.validation`'s reach into `migration.run` is already deferred and pyright counts it as an edge all the same. Tried it; the cycle report was unchanged. Worth knowing before anyone tries the same thing on `pipelex_service_config.py`.

So the module was split the way `system/configuration/` already splits: **`telemetry_config.py` keeps the models, the new `telemetry_loader.py` holds `load_telemetry_config`**. That makes the edges run one way — the registry reads the models, the loader reads the registry — and it is cheap, because everything in the registry's closure (`otel_factory`, `surfaces` itself) imports only models. `telemetry_factory.py` was the single production importer of the loader.

This is the same shape Milestone 7 hit and solved by moving `packaged_migration_dir` off `surfaces.py` onto `ledger.py`, one level up: *a loader must be able to reach the migration package without reaching the registry.*

### Deliberately not done

**`pipelex_service_config.py` is the third surface and was left alone.** It has boot tolerance and no block — but it also has **no hardcoded remedy to retire**, anywhere: nothing in the CLI catches `PipelexServiceConfigValidationError` by name, and it carries agreement/onboarding state rather than settings a user tuned. Closing the gap means the same models/loader split (`surfaces.py` imports `PipelexServiceConfig` from it), which is a change item 4 does not justify. Named here so it reads as a decision rather than an oversight.

**`--fix` does not yet run the migration.** `OUT_OF_DATE` is reported and `pipelex migrate` is named, but fix mode offers nothing for it — deliberately, because "`--fix` delegating to the migrate command" is item 5, whose pending-migrations row covers every surface and would supersede a telemetry-only version built here. What item 4 owed was that fix mode stop offering the *destructive* thing, and it does.

### Files touched in milestone 9

```
pipelex/system/telemetry/exceptions.py            TelemetryConfigError is a PipelexConfigError
pipelex/system/telemetry/telemetry_loader.py      NEW — the loader, out of the registry's closure
pipelex/system/telemetry/telemetry_config.py      models only now
pipelex/system/telemetry/telemetry_factory.py     re-pointed at the loader
pipelex/migration/run.py                          scan_config_surface(config_dirs=...)
pipelex/cli/commands/doctor_cmd.py                TelemetryConfigFinding / TelemetryConfigCheck; every text sniff gone
pipelex/cli/agent_cli/commands/doctor_cmd.py      _telemetry_action; `finding` on the envelope
pipelex/cli/error_handlers.py                     the banner rebuilt from the error
pipelex/cli/agent_cli/commands/agent_output.py    the hint rewritten; the domain entry removed
docs/migration-ledger.md                          NEW § "Every surface reports it the same way, and none of them says start over"
docs/configuration/config-practical/telemetry-config.md   NEW § "When telemetry.toml will not load"
docs/tools/cli/{migrate,init,agent-cli}.md, docs/under-the-hood/init-cli-flows.md
pipelex/cli/agent_cli/CLAUDE.md                   the doctor row names the finding
CHANGELOG.md                                      one Changed, two Fixed
tests/unit/pipelex/system/telemetry/test_telemetry_stale_remedy.py   NEW
tests/unit/pipelex/cli/{test_doctor_config_checks,test_doctor_cmd,test_doctor_display_report,test_doctor_fix_mode,test_agent_doctor_cmd,test_error_handlers_more}.py
tests/e2e/pipelex/cli/test_migrate_commands.py    NEW class: the doctor row and the agent envelope, both through the real binary
.drift/acks/{config-docs,cli-docs}.toml           both reviewed and acked
```

Mutation-tested: dropping the block from the raise, un-parenting the error class, dropping the migration prose from the message, making a fresh file "repair" an out-of-date one, dropping the reserved-`[meta]` strip, letting the scan inherit the whole walk, giving every finding one remedy again, removing the doctor's scan guard, and widening that guard to a blanket `except` — each turned exactly the intended tests red.

Also corrected in passing: `TestNoValueFromAUsersFileIsEverRendered`'s docstring still said the third rendering channel would arrive "when `report_validation_error` starts reporting the real plan". Milestone 8 landed it, as its own class, for the reason that class's docstring gives.

## Where this session paused

**Paused right after milestone 9 was committed.** Working tree clean. The **branch** has an upstream — `origin/feature/Migrator-3b`, whose head is milestone 8 — so **only milestone 9 is unpushed**: the branch is one commit ahead of its remote. (Milestone 8 was pushed between sessions; the note that said otherwise was written before that happened.) `make agent-check` with everything staged (so `drift-check` is a real green), `make docs-check`, and the full `make agent-test` were all green on the exact tree that was committed.

Both drift contracts came open again at milestone 9 and were acked with the reviews written into the ack rationales: `config-docs` (which produced the telemetry page's new "When telemetry.toml will not load" section) and `cli-docs` (which produced the finding on the agent doctor's documented envelope, the `agent-cli.md` note that the telemetry error carries the block too, and the honest `init.md` warning that init replaces a file wholesale).

At milestone 8 the same two were acked: `config-docs` produced the `docs/configuration/index.md` fix the *previous* ack had explicitly parked for that milestone, and `cli-docs` produced the agent-CLI error-envelope documentation and the `migrate.md` agent paragraph.

### Milestone 7's own ack record, kept

Three contracts were acked at milestone 7: `hub-layering-convention`, `cli-docs` and `config-docs`.

## What is actually left

Measured against the charter's own **Done when** list ([§ S6](../../wip/migrator-3/sequencing.md#s6--migrator-phase-3)), verified against the tree rather than against this file:

| Done when | State |
|---|---|
| The golden format is final for S7 (format bucket, dotted-key rename, `umig`, backup/replace in the contract) | ✅ Milestones 1 and 3 |
| R9 is built | ✅ Milestone 2 |
| The walk stops by name on a file two surfaces' globs both claim | ✅ Behaviour and test landed in Phase 2; the #1111 note-5 half landed in Milestone 5 (`TestTheWalkIsNotRecursive`, both halves, real specimen) |
| `pipelex migrate --help` / `pipelex-agent migrate --help`, the bootstrap test, both end-to-end tests | ✅ Milestone 5 — and the end-to-end pair runs against the **real** `telemetry-config@2` entry rather than current-shape fixtures, which is stronger than the charter asked for |
| `release/SKILL.md` step 3b; `.claude/skills/add-migration/` | ❌ Neither exists |

The phase body the charter lists under **Do**, in the order the next session should take it:

1. ~~**The downgrade diagnosis**~~ — done, see Milestone 6.
2. ~~**Boot tolerance**~~ — done, see Milestone 7.
3. ~~**`report_validation_error` on the real plan**~~ — done, see Milestone 8. The third channel of the rendering-rule test landed with it, as a new e2e class (`TestABootFailureCarriesThePendingMigration`) rather than inside `TestNoValueFromAUsersFileIsEverRendered`, because the reachable specimen is different: boot tolerance means a file the ledger *can* explain never reaches the error surface at all, so the channel is exercised by a key no entry explains, whose value is the planted secret.
4. ~~**The two telemetry remedies retired**~~ — done, see Milestone 9. There were four, and the worst of them was `doctor --fix`'s offer to reset a migratable file. The third surface, `pipelex_service_config.py`, was deliberately left alone — it has no wrong remedy to retire, and closing its gap costs the same models/loader split.
5. **`doctor`: the pending-migrations row and `--fix`** delegating to the migrate command. Milestone 9 built the telemetry *finding* and left `--fix` silent on `OUT_OF_DATE` on purpose, so this item now has two halves: the row that reports pending migrations across **every** surface, and fix mode actually running the command. Milestone 7's note that a machine consumer never learns of a pending migration from a boot is what makes the row load-bearing.
6. **The `config-docs` drift contract's `review` list** plus the four validator sites R8 names (`KitConfig._validate_targets`, `DryRunConfig.validate_image_urls`, `ImgGenConfig.validate_quality_mapping`, `LLMConfig.validate_effort_to_budget_mapping`).
7. **The skills**: `.claude/skills/add-migration/`, and `/release` step 3b.
8. **`docs/specs/command-surface-map.md` rows** — that file is in the **workspace-root** repo, not this one.
9. **Publish the contract**: delete `docs/migration-ledger.md`'s Status banner, remove its `not_in_nav` entry and comment, add a Migration Ledger row to the nav's Project section.

Then the PR to `dev` from `feature/Migrator-3b`.

### Small items still owed, folded in from the #1113 review

- ~~**`MigrationLedger.entry_for_version` still has no caller.**~~ Answered by Milestone 6: the downgrade diagnosis looks a blocked entry's own operations up from the `to_schema_version` its `BlockedEntry` carries, which is the first real caller. It stays.
- **`is_remappable` has no direct unit test** and gates two accountings; and §1 of `pr-1113-review-notes.md` (credit a union by its string branches alone and say so, or ask the non-string branches — about four lines on `_records_enumerated_members`) is still undecided. Cheap, and it belongs with whoever next touches `coverage.py`.
- **The rescue-copy race** (`pr-1113-review-notes.md` §3): a third run's prune can take the `.bak.` a rescue is about to rename. The commands now make concurrent runs producible, so this is decidable — revisit as an age-sparing prune, not a lock.
- Deliberately past S7's freeze, with named triggers, in `pr-1113-review-notes.md` and `migrator-write-scope-and-rename-fidelity.md`: per-member bounds in the golden, the `safe`-entry sibling, the tomlkit raw-storage staleness pass, rename fidelity (§2), the taken-backup-name report, and the residual. §1 of the write-scope note is **closed** by Milestone 5.

**The next session starts at item 5, the `doctor` pending-migrations row and `--fix`.** Milestone 9 built the telemetry half of it — `check_telemetry_config` now answers with a `TelemetryConfigFinding` and the report names `pipelex migrate` for an out-of-date file — and stopped there on purpose, because a row that covers *every* surface would supersede a telemetry-only `--fix`. What is owed: a health row that runs `scan_config_surface` (or the whole-walk `migrate_config_directories` dry run) across all three surfaces and reports what is pending, and fix mode offering to run the migration rather than nothing. `TelemetryConfigCheck`'s shape is the precedent to follow — a finding a caller branches on, never a sentence it greps, which is the defect Milestone 9 fixed inside the doctor itself.

Milestone 7's inherited finding — the dead `except ValidationError` around `setup_config` — **is fixed**, at both of that function's config-side callers, and the same defect turned out to exist in the doctor.

## Rulings this session took on its own authority

The charter says the format bucket is to be "decided and recorded here" — it does not route it to Louis, unlike R1–R9. The three decisions above were taken on that basis, each with its reasoning written into `docs/migration-ledger.md` rather than only here. **R9 itself is already ruled** (option 2, 2026-08-16) and is a build task, not a decision.

Milestone 3 took the policy calls the charter routed here by name — preserve dotted-ness rather than refuse it; follow a symlink rather than refuse or clobber it; never overwrite or remove a copy this run did not make; take a copy the run cannot vouch for out of the pruning rotation by name; carry the mode and not the ownership or the extended attributes; `fsync` the directory once, after the backup and before the replace. Each is written into `docs/migration-ledger.md` rather than only here.

Milestone 5 took two on the same basis, both written into `docs/migration-ledger.md`: **a migration's write scope is the resolved target of any file the walk claims** (the `.mthds` fix loop's scope guard is not copied, because a configuration directory is where a user keeps links to files they own); and **`min_supported_schema_version` gets a reader rather than a softened sentence** — a file declaring a version below its ledger's floor is refused by name, reading the reserved key exactly as tolerantly as boot strips it.

Milestone 2 took three further rulings on that same basis, each written into `docs/migration-ledger.md` rather than only here: the coverage gate now demands a declaration from an `unsafe` entry rather than accepting the word (without it R9 is half-built); convergence exempts a `VALUE_DOMAIN_NARROWED` report and nothing else (without it R9's ruled shape cannot be written at all); and forward tracing stops at `unsafe` entries (a rehearsal may guess, an application may not). The third is the one that leaves a named open question, listed above.

Milestone 9 took three on that basis, all written into `docs/migration-ledger.md`: **writing a fresh file repairs exactly one finding, a missing one** — every other unhealthy state holds the user's own settings, so an out-of-date file gets the migration and a broken one gets a person; **a probe's verdict is a field its callers branch on, never a sentence they search** — the doctor's own `--fix` had made the opposite choice and would have lost its repair path to a reword; and **a loader must be able to reach the migration package without reaching the registry**, which is what put the telemetry models and the telemetry loader in two modules. The scope call — leaving `pipelex_service_config.py` alone — is recorded in Milestone 9 above rather than in the contract, because it is a decision about this branch rather than about the ledger.

Milestone 8 took four, each written into `docs/migration-ledger.md` rather than only here: **the scan is scoped by the surface the caller names**, so a `.mthds` bundle or a backend file pays for no walk and is offered no remedy it has none for; **the block carries `MigrationPlan` itself** rather than a projection of it, which is what forced `MigrationSafety` out of `ledger.py` into `safety.py` — a second shape would have drifted from the commands' own; **scoping narrows the answer and never the registry**, because ownership is decided across all surfaces and a one-surface registry hands `pipelex_service.toml` to the wrong ledger; and **a failure inside the scan declines quietly, but only on `(MigrationError, OSError)`** — an applier bug is not a field condition and must keep surfacing.
