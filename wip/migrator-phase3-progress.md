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

⚠ **S6 is past half.** The pre-S7 bucket is closed (part 1, on `dev`), **the two `migrate` commands are built** (milestone 5) and **the downgrade diagnosis is built** (milestone 6), both on `feature/Migrator-3b`. What remains is the rest of the phase body — boot tolerance, `report_validation_error`, the telemetry-remedy retirement, `doctor`, the skills, the specs rows, and publishing the contract. See [What is actually left](#what-is-actually-left) at the bottom before planning a session.

## Build order chosen for this session

The charter lists a great many deliverables without an order. The order below was chosen so that everything touching the **golden format** happens first and the goldens are regenerated exactly once, before any other work can be built on top of a format that then moves:

1. **The golden-format bucket + the narrowing relation** — done, see below.
2. **R9 + the "what does `unsafe` promise" pass** — done, see Milestone 2 below.
3. **The applier's dotted-key rename policy, the backup/replace semantics pass, the `UNWRITABLE` wording** — done, see Milestone 3 below. That closes the "must be settled before S7" bucket.
4. **The commands** — `pipelex migrate`, `pipelex-agent migrate`, the rendering-rule test — done, see Milestone 5 below. The **downgrade diagnosis** (`unexplained[]`) was deliberately carried out of this milestone and is where the next session starts.
5. **The downgrade diagnosis** — done, see Milestone 6 below.
6. **Boot tolerance, `report_validation_error` on the real plan, the telemetry remedies retired, the `doctor` row** — not started. **This is where the next session starts.**
7. **The skills (`add-migration`, `/release` step 3b), the `config-docs` drift-contract review list, `command-surface-map.md` rows, publishing the contract in the nav** — not started.

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

## Where this session paused

**Paused right after milestone 6 was committed.** `feature/Migrator-3b` = *"Migrator Phase 3, milestone 6: name what the migration cannot explain"*, working tree clean, **still no upstream** — the first push is `git push -u origin feature/Migrator-3b`. `make agent-check`, `make cl`, `make cmig`, `make docs-check`, `make drift-check` (with the changes staged) and the **full `make agent-test`** were all green before the commit.

### Groundwork already done for boot tolerance (item 2), so the next session does not redo it

**The import cycle everyone would fear is not there.** `pipelex.migration.engine` + `pipelex.migration.ledger` pull in only `pipelex.system.configuration.config_model` — not `configs`, not `config_loader`, not `telemetry_config`. What pulls the configuration models into the migration package is `migration/surfaces.py` (the **registry**), and boot tolerance does not need it: a loader already knows its own surface id and its own list of paths. So the helper may import the engine and the ledger at module level from `config_surface.py`.

**"The healthy path never loads tomlkit" is about parsing, not importing.** `config_loader` already imports tomlkit through `tools/misc/toml_utils.py`. The property to keep is that a healthy boot never *re-reads* the files as a DOM and never reads a ledger.

**The three loaders and their merge steps** (each calls `strip_reserved_meta` today, which is the seam the contract points at):

| Surface | Loader | What sits between the merge and the validate |
|---|---|---|
| `pipelex-config` | `config_loader.py` `ConfigLoader.load_config` | `extra_overrides` deep-merged on top; a unit-testing layer below |
| `telemetry-config` | `telemetry_config.py` (`load_telemetry_config`) | `${VAR}` substitution over every string |
| `pipelex-service-config` | `pipelex_service_config.py` `load_pipelex_service_config_if_exists` | nothing |

Because those steps differ, **the helper cannot own the whole load**. The shape that works is a helper owning the *failure path only* — given a surface id and the same ordered path list the loader merged, it reads each existing file, replays that surface's `safe` entries in memory, deep-merges the migrated documents in the same order, and hands back the merged dict plus the per-file `MigrationPlan`s — returning nothing when no operation applied, since then the failure is not staleness. The loader re-runs its own post-merge steps and re-validates.

**Decision taken, and the reason worth keeping:** *boot tolerance does not run the downgrade diagnosis.* On the boot path the model has already spoken — pydantic's own extra-field list is the unexplained set, and it is more accurate than a path walk because it knows about validators. The diagnosis exists for the `migrate` command, where nothing validates the file. So the `migration` block on a configuration validation error carries the **plans**, and the "unexplained paths still fail the boot" clause of the contract is satisfied by the re-validation failing, not by a second diagnosis.

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
2. **Boot tolerance** in one shared helper called by all three config-surface loaders. `pipelex/system/configuration/config_surface.py` is the home — it already owns the reserved-`[meta]` read side, and `declared_schema_version` landed there in Milestone 5.
3. **`report_validation_error` on the real plan** — note `core/validation.py`'s current `migration_config` is the old *renaming* config, not the ledger plan. Consumer removed, `migration` field kept. This is also the **third channel of the rendering-rule test**, which is written and waiting for it (`TestNoValueFromAUsersFileIsEverRendered` names the gap in its docstring).
4. **The two telemetry remedies retired** — `check_telemetry_config`'s old-shape sniff in `doctor_cmd.py` and `handle_telemetry_config_validation_error`'s banner in `error_handlers.py`. Both currently tell a user to re-initialize the file that Milestone 5 proved is migratable.
5. **`doctor`: the pending-migrations row and `--fix`** delegating to the migrate command.
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

**The next session starts at boot tolerance.**

## Rulings this session took on its own authority

The charter says the format bucket is to be "decided and recorded here" — it does not route it to Louis, unlike R1–R9. The three decisions above were taken on that basis, each with its reasoning written into `docs/migration-ledger.md` rather than only here. **R9 itself is already ruled** (option 2, 2026-08-16) and is a build task, not a decision.

Milestone 3 took the policy calls the charter routed here by name — preserve dotted-ness rather than refuse it; follow a symlink rather than refuse or clobber it; never overwrite or remove a copy this run did not make; take a copy the run cannot vouch for out of the pruning rotation by name; carry the mode and not the ownership or the extended attributes; `fsync` the directory once, after the backup and before the replace. Each is written into `docs/migration-ledger.md` rather than only here.

Milestone 5 took two on the same basis, both written into `docs/migration-ledger.md`: **a migration's write scope is the resolved target of any file the walk claims** (the `.mthds` fix loop's scope guard is not copied, because a configuration directory is where a user keeps links to files they own); and **`min_supported_schema_version` gets a reader rather than a softened sentence** — a file declaring a version below its ledger's floor is refused by name, reading the reserved key exactly as tolerantly as boot strips it.

Milestone 2 took three further rulings on that same basis, each written into `docs/migration-ledger.md` rather than only here: the coverage gate now demands a declaration from an `unsafe` entry rather than accepting the word (without it R9 is half-built); convergence exempts a `VALUE_DOMAIN_NARROWED` report and nothing else (without it R9's ruled shape cannot be written at all); and forward tracing stops at `unsafe` entries (a rehearsal may guess, an application may not). The third is the one that leaves a named open question, listed above.
