# Deferred from the Phase 3 review: write scope, rename fidelity, and a backup name this run did not claim

Three findings from the `/code-review high` pass over the Phase 3 staged changes were deliberately not fixed. Each is a decision rather than a defect, and each is written down here so the decision is taken on purpose rather than by omission. The other findings from that pass — the narrowed-path spelling and the rescue-copy promise — were fixed in the same change.

## 1. The migration runner follows a symlink out of the directories it was told to walk

`migrate_file` in `pipelex/migration/runner.py` calls `read_file_snapshot(file_path.resolve())`, so a configuration file that is a symlink is read, backed up and atomically replaced **at the link's target**. That resolution is deliberate and documented — replacing the link path would put a regular file where the link was and leave the real file unmigrated — and it is what the `.mthds` fix loop does with its own targets.

The difference is what the fix loop does *next*. `pipelex/pipeline/fixes/fix_loop.py` pairs its `.resolve()` with `_partition_by_write_scope` / `is_target_in_write_scope`, so a resolved target that lands outside the directories the loop was given is refused rather than written. The migration runner has no equivalent, so:

> `.pipelex/pipelex.toml` is a symlink to `/somewhere/else/config.toml`. The run rewrites `/somewhere/else/config.toml` and drops a `.bak.<stamp>` beside it — a file and a directory the walk never named.

**Why it is not fixed here.** The behaviour is arguably right: the file the user means *is* the one at the end of the link, and a dotfiles-managed configuration is exactly the case symlink-following exists for. Refusing it would break the setup the resolution was added to support. But "we write outside the walked directories" is a claim worth making on purpose, and today it is made by accident — the docs asserted the two callers agreed, which on this half they did not.

**The decision to take.** One of:

- **Keep it, and say so.** The run's write scope is "the resolved target of any file the walk claims", full stop. Cheapest, and consistent with the reason the resolution exists. The doc sentence in `docs/migration-ledger.md` → "Backups" has already been trimmed to state this honestly.
- **Guard it like the fix loop.** Add a write-scope check against the walked configuration directories and block a resolved target outside them as `UNWRITABLE`. This makes the two callers genuinely agree, at the cost of refusing the dotfiles case unless the real directory is also walked.

## 2. A rename still rewrites the assignment's spacing and drops a deliberate quoting

`_renamed_key` in `pipelex/pipeline/fixes/applier.py` builds `SingleKey(new_key)` and carries forward only the `_dotted` flag. The separator (`previous.sep`) and the key type (`previous.t`) are left to tomlkit's defaults, so:

```toml
old    = 1  # keep me     →     new = 1  # keep me
"old"  = 1                →     new = 1
```

The comment and the line's position survive — that is what the body-level rename was written to preserve, and it does preserve it. Column alignment and an intentionally quoted bare-safe key do not.

**Why it is not fixed here.** It is not a regression: the previous `Container._replace` path did the same, and `_renamed_key`'s own docstring states the choice ("Everything else — quoting, separator — is left to tomlkit's own construction, so renaming an ordinary key yields exactly the key the library would have built for it"). But it sits against two claims made elsewhere in the same changeset — `docs/migration-ledger.md` → "A rename changes a name, and nothing else about the line", and the engine's "no canonical reflow, because a one-key rename must not rewrite a user's spacing" — and configuration migration, unlike the `.mthds` path, has no canonical reflow afterwards to normalise the result.

**The decision to take.** Either carry `previous.sep` and `previous.t` forward alongside `_dotted` (a one-line change, and the claims then hold literally), or narrow the claims to what is actually promised: the *line* keeps its position and its comment, the *assignment* is renormalised. Worth checking what a carried-forward `sep` does when the old and new names differ in length — preserving the old padding around a longer name is not obviously better than renormalising it, and that is the real question behind this one.

## 3. A backup name already taken is reported as this run's copy

`write_backup` reserves its name with `O_CREAT | O_EXCL`; when the name is taken it returns `WrittenBackup(path=destination, was_created=False)` — a path it did not write and whose contents it never read. `_write_migrated_file` then commits and reports `backup_path=backup.path, was_written=True`, so the plan names a file this run did not produce.

**Why it is not fixed.** This is the module's documented policy working exactly as intended: the stamp resolves to the second, two runs of the same file can address one name, and the copy already there is a copy of an *older* state — the original, if anything is. Naming it is correct and useful; the user can restore from it.

The scenarios where it is *not* correct both require a file to be sitting at `<file>.bak.<this run's exact UTC second>` from a source other than a concurrent run — a hand-made backup that happens to match the stamp format to the second, or a zero-byte reservation left by a run killed inside the microsecond window between `_reserve_name` and the rename, found by a re-run within the same second. Guarding those would be a guard for a case that does not happen, which this codebase deliberately does not write.

What *was* wrong on this path — the `state_uncertain` report promising to keep a copy it had not moved out of the pruning rotation — is fixed: `keep_backup_for_rescue` now returns `RescuedBackup(path, was_rescued)` and the report tells the user to take the copy now when it could not be secured.

A second thing was wrong on it and is now fixed too, found by the PR #1113 bot review: the *creator* of a shared name could delete a copy the adopting run was already relying on. Run A writes `bak.T`; run B finds the name taken, adopts it as its restore point, commits and prunes; A's commit is then refused *because B's landed*, and `_discard_backup` unlinked `bak.T` on the reasoning that a write that did not happen has nothing to back up. That reasoning is about A's own actions, and it left the migrated file with no copy of the original anywhere. `_discard_backup` now asks the file what it holds: a refused write discards its copy unless the file already carries the text this run was going to write, which only the other run can have put there. A user's own edit is unaffected — the file then holds the user's text, and the copy goes as it always did.

**Residual worth knowing.** If this ever needs revisiting, the honest lever is not a content check but the plan's vocabulary: `MigrationPlan.backup_path` currently means "where a copy of the pre-migration file is", not "where this run wrote one", and nothing in the report distinguishes the two.

## Residual, unrelated to the three above

`_declared_paths_this_file_carries` now reports the spelling the end of the replay leaves. Where a later `safe` entry *deletes* the material, there is no later spelling and the report falls back to the spelling the file carried when the entry was reached — a key the migrated file no longer has. Left alone on purpose: `test_material_a_later_entry_retires_leaves_nothing_to_say_to_a_file_migrated_that_far` pins that such a file is still reported, and changing what happens there is a decision about the reporting *predicate*, not about which spelling to name.
