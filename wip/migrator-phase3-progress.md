# S6 — Migrator Phase 3: working tracker

The charter is [`wip/migrator-3/sequencing.md` § S6](../../wip/migrator-3/sequencing.md) at the **workspace root** (from this repo: `../wip/migrator-3/sequencing.md`), with the phase content in `plan.md § Phase 3`. This file is the session-crossing record of what S6 has built, what it decided, and what is still open. Open the charter first, then this.

**Venue.** `_migrator/`, branch `feature/Migrator-3`, cut from `origin/dev` (the Phase 2 squash merge). Nothing pushed yet, no PR open yet.

⚠ **Cold-start state.** Milestone 1 is the branch's only commit (*"Migrator Phase 3, milestone 1: settle the golden format before S7 freezes it"*). **Milestones 2 and 3 are green but uncommitted** — staged working-tree state on top of it, across 22 files. Do not `git checkout`/`git stash` anything before reading the two milestone sections below; commit them first if you want a clean tree.

## Build order chosen for this session

The charter lists a great many deliverables without an order. The order below was chosen so that everything touching the **golden format** happens first and the goldens are regenerated exactly once, before any other work can be built on top of a format that then moves:

1. **The golden-format bucket + the narrowing relation** — done, see below.
2. **R9 + the "what does `unsafe` promise" pass** — done, see Milestone 2 below.
3. **The applier's dotted-key rename policy, the backup/replace semantics pass, the `UNWRITABLE` wording** — done, see Milestone 3 below. That closes the "must be settled before S7" bucket.
4. **The commands** — `pipelex migrate`, `pipelex-agent migrate`, the downgrade diagnosis, the rendering-rule test — not started. **This is where the next session starts.**
5. **Boot tolerance, `report_validation_error` on the real plan, the telemetry remedies retired, the `doctor` row** — not started.
6. **The skills (`add-migration`, `/release` step 3b), the `config-docs` drift-contract review list, `command-surface-map.md` rows, publishing the contract in the nav** — not started.

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

## Milestone 2 — what an `unsafe` entry promises (DONE, uncommitted at the pause)

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

`make agent-check` green, `make cl` green, `make cmig` green, and the full `make agent-test` green — every test passed. Nothing committed yet: milestone 2 is uncommitted working-tree state on top of `9eea2219f`.

## Milestone 3 — the write path: dotted keys, backups, and what a blocked file means (DONE, uncommitted)

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

`make agent-check` green, `make cl` green, `make cmig` green, `make docs-check` green, `make drift-check` green **with the changes staged**. Full `make agent-test` green. Milestones 2 and 3 are both uncommitted working-tree state on top of `9eea2219f`.

## Already true before this session started (do not rebuild)

- **The directory walk's overlap refusal** — the S6 "Done when" item carried from the #1110 review — **is already built and tested**: `SurfaceRegistry.surface_for_file_name` raises `MigrationRegistryError` naming the file, and `tests/unit/pipelex/migration/test_surface_resolution.py::test_a_file_two_globs_both_claim_stops_by_name` proves it with the `pipelex_*.toml` / `*_local.toml` pair. It landed in Phase 2 ahead of schedule. **What is still owed** is the #1111 note-5 half: use the *real* specimen — `.pipelex/inference/backends/pipelex_gateway.toml`, which matches the `pipelex-config` tier glob and is claimed by nothing — rather than a synthetic name, and pin that the walk is **non-recursive** (it is: `files_by_surface_in_directory` skips anything that is not a file, so the `inference/backends/` subdirectory is never descended). That is a test, not a behaviour change.

## Still open, in the charter's own words

Everything in [§ S6](../../wip/migrator-3/sequencing.md#s6--migrator-phase-3) not listed under Milestone 1 above. The ones that must be settled *here* rather than at S7:

- ~~**The dotted-key rename policy**~~ — done, see Milestone 3(a).
- ~~**The backup and replace semantics pass**~~ — done, see Milestone 3(b).
- ~~**The `UNWRITABLE` wording and the reason enum**~~ — done, see Milestone 3(c).
- ~~**R9**~~ — done, see Milestone 2. What it left open: **a `safe` entry silenced by its own `CONFLICT` plus a later rename** has the same mechanism and was deliberately not fixed, because repairing it means writing at a guessed spelling.

**The "must be settled before S7" bucket is closed.** Two named follow-ups came out of it, neither blocking: the tomlkit raw-storage staleness wants one pass over every facade kind (`Container`, `Table`, `OutOfOrderTableProxy`) rather than the half-repair a rename can reach; and the `safe`-entry sibling above.

Then the phase's own body: the two commands, boot tolerance, `report_validation_error`, the downgrade diagnosis, the telemetry-remedy retirement, `doctor`, the drift-contract review list (plus the four validator sites R8 names), the `add-migration` skill, `/release` step 3b, the `command-surface-map.md` rows, and publishing the contract in the nav.

## Rulings this session took on its own authority

The charter says the format bucket is to be "decided and recorded here" — it does not route it to Louis, unlike R1–R9. The three decisions above were taken on that basis, each with its reasoning written into `docs/migration-ledger.md` rather than only here. **R9 itself is already ruled** (option 2, 2026-08-16) and is a build task, not a decision.

Milestone 3 took the policy calls the charter routed here by name — preserve dotted-ness rather than refuse it; follow a symlink rather than refuse or clobber it; never overwrite or remove a copy this run did not make; take a copy the run cannot vouch for out of the pruning rotation by name; carry the mode and not the ownership or the extended attributes; `fsync` the directory once, after the backup and before the replace. Each is written into `docs/migration-ledger.md` rather than only here.

Milestone 2 took three further rulings on that same basis, each written into `docs/migration-ledger.md` rather than only here: the coverage gate now demands a declaration from an `unsafe` entry rather than accepting the word (without it R9 is half-built); convergence exempts a `VALUE_DOMAIN_NARROWED` report and nothing else (without it R9's ruled shape cannot be written at all); and forward tracing stops at `unsafe` entries (a rehearsal may guess, an application may not). The third is the one that leaves a named open question, listed above.
