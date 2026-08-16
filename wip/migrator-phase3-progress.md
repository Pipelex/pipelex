# S6 — Migrator Phase 3: working tracker

The charter is [`wip/migrator-3/sequencing.md` § S6](../../wip/migrator-3/sequencing.md) at the **workspace root** (from this repo: `../wip/migrator-3/sequencing.md`), with the phase content in `plan.md § Phase 3`. This file is the session-crossing record of what S6 has built, what it decided, and what is still open. Open the charter first, then this.

**Venue.** `_migrator/`, branch `feature/Migrator-3`, cut from `origin/dev` = `0aa8913f2` (the Phase 2 squash merge). Milestone 1 is committed as `077744b3d`; nothing pushed yet, no PR open yet.

## Build order chosen for this session

The charter lists a great many deliverables without an order. The order below was chosen so that everything touching the **golden format** happens first and the goldens are regenerated exactly once, before any other work can be built on top of a format that then moves:

1. **The golden-format bucket + the narrowing relation** — done, see below.
2. **R9 + the "what does `unsafe` promise" pass** — not started.
3. **The applier's dotted-key rename policy, the backup/replace semantics pass, the `UNWRITABLE` wording** — not started.
4. **The commands** — `pipelex migrate`, `pipelex-agent migrate`, the downgrade diagnosis, the rendering-rule test — not started.
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

## Already true before this session started (do not rebuild)

- **The directory walk's overlap refusal** — the S6 "Done when" item carried from the #1110 review — **is already built and tested**: `SurfaceRegistry.surface_for_file_name` raises `MigrationRegistryError` naming the file, and `tests/unit/pipelex/migration/test_surface_resolution.py::test_a_file_two_globs_both_claim_stops_by_name` proves it with the `pipelex_*.toml` / `*_local.toml` pair. It landed in Phase 2 ahead of schedule. **What is still owed** is the #1111 note-5 half: use the *real* specimen — `.pipelex/inference/backends/pipelex_gateway.toml`, which matches the `pipelex-config` tier glob and is claimed by nothing — rather than a synthetic name, and pin that the walk is **non-recursive** (it is: `files_by_surface_in_directory` skips anything that is not a file, so the `inference/backends/` subdirectory is never descended). That is a test, not a behaviour change.

## Still open, in the charter's own words

Everything in [§ S6](../../wip/migrator-3/sequencing.md#s6--migrator-phase-3) not listed under Milestone 1 above. The ones that must be settled *here* rather than at S7:

- **The dotted-key rename policy** — renaming a table written in dotted-key form swallows the scalars after it. Reproduced in round 3; the reshape's table renames will meet it on the first machine. Refuse with a `CONFLICT` naming the section, or preserve dotted-ness through `_replace_key_in_container`; either way a red/green fixture in `test_fix_applier_config_surface_shapes.py`.
- **The backup and replace semantics pass** — the same-second backup collision (M), a symlinked target replaced by a regular file (N), the backup kept after an uncertain-state failure being pruned by the next successful run, ownership/ACL/xattr loss, and whether a directory `fsync` is owed. One policy decision, written into the contract's "Backups" paragraph. `file_transaction.py` is shared with the `.mthds` fix loop.
- **The `UNWRITABLE` wording and the reason enum** — for a single-file commit the only reachable `FixTransactionError` is post-commit cleanup, i.e. the write *landed*; the wording describes an unreachable path.
- **R9** — the op-free `unsafe` entry declares the paths whose domain narrowed; `check-ledger` demands the declaration name at least one path the fingerprint at the entry's own version still has; the rehearsal reads it. Built together with the sibling question (an `unsafe` entry silenced by a later `safe` rename of its target) as one pass over what `unsafe` promises.

Then the phase's own body: the two commands, boot tolerance, `report_validation_error`, the downgrade diagnosis, the telemetry-remedy retirement, `doctor`, the drift-contract review list (plus the four validator sites R8 names), the `add-migration` skill, `/release` step 3b, the `command-surface-map.md` rows, and publishing the contract in the nav.

## Rulings this session took on its own authority

The charter says the format bucket is to be "decided and recorded here" — it does not route it to Louis, unlike R1–R9. The three decisions above were taken on that basis, each with its reasoning written into `docs/migration-ledger.md` rather than only here. **R9 itself is already ruled** (option 2, 2026-08-16) and is a build task, not a decision.
