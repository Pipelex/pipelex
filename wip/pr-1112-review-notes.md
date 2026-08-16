# PR #1112 review triage — Migrator Phase 2

PR [#1112](https://github.com/Pipelex/pipelex/pull/1112) → `dev`, branch `feature/Migrator-2`. Three bots left 33 review threads (greptile 1, codex 5, cubic 27). Every one was read in full and verified against the code by hand; the eight that a first pass had left unverified were verified in the round that executed this triage.

**State: arbitrated and executed.** The clusters marked *Fixed* below are fixed on the branch, TDD-first, with `make agent-check`, `make cl`, `make cmig` and the suite green. The clusters marked *Deferred* are recorded here and their threads left open. The ones marked *Won't fix* were answered on their thread and resolved. The arbitration rule was Louis': fix what needs fixing, defer in doubt, no speculative machinery.

## Disposition

| # | Where | Issue | Reporter(s) | Disposition |
|---|---|---|---|---|
| A | `runner.py`, `backup.py` | `FixTransactionError` and pruning failures escaped `migrate_file`, aborting every sibling | greptile #1, codex #4, cubic #16, #22 | **Fixed** |
| B | `backup.py` | Pruning deleted any `<file>.bak.*`, including a user's own hand-made copy | cubic #28 | **Fixed** |
| C | `backup.py` | Staged backup copy leaked when the replace failed | cubic #21 | **Fixed** |
| D | `narrowing.py` | `Literal['a']` → `Literal[1]` suppressed the lost spelling entirely | cubic #15 | **Fixed** |
| E | `transform_check.py` | An unreadable golden crashed the gate with a raw traceback | cubic #29 | **Fixed** |
| E′ | `surfaces.py:117` | An unreadable packaged kit template crashes the gate | cubic #27 | **Won't fix** — a packaged file missing is a broken install, and the traceback names the path |
| F | `narrowing.py` | Float `multiple_of` modulo reported a widening as a narrowing | codex #5, cubic #24 | **Fixed** |
| G | `ledger.py` | `declared_removed_paths = [""]` satisfies the guard vacuously | cubic #17 | **Won't fix** — not exploitable: `""` is never a reserved prefix, so every op of such an entry is refused as live material and the gate is red anyway |
| H | `test_replay_properties.py` | The "older shape" fixture kept the new keys, so renames conflicted instead of applying | cubic #18 | **Fixed** |
| I | `test_engine.py`, `test_telemetry_back_entry.py` | Tests passed without exercising the guarantee they name | cubic #31, #33 | **Fixed** |
| J | `test_fix_applier_rename_dom_consistency.py`, `applier.py` | Docstring contradicted its own pinned assertion | cubic #30 | **Fixed** |
| K | `test_runner.py` | `_write_ledger` duplicated the `write_ledger_file` fixture | cubic #32 | **Fixed** |
| L | `engine.py` | An op-free `unsafe` entry is structurally unreportable | codex #2 | **Deferred — needs a ruling** |
| M | `backup.py`, `runner.py` | Two runs in the same UTC second can lose the only prior backup | codex #6, cubic #12 | **Deferred** |
| N | `runner.py` | A symlinked config file is replaced by a regular file | codex #3, cubic #8 | **Deferred — policy call** |
| O | `surfaces.py` | `telemetry.project.toml` is not a neutrality witness | cubic #11 | **Deferred** |
| P | `fingerprint.py` | Union-member constraints merged with the field's own | cubic #10 | **Deferred** |
| Q | `narrowing.py` | `gt=0` vs `ge=1` on ints; `list[int]` → `list[int \| str]` | cubic #25, #26 | **Deferred** |
| R | `coverage.py:315` | Any remap over a free-form domain suppresses the narrowing | cubic #7 | **Won't fix — as designed** |
| S1 | `documents.py:40` | A quoted key containing `.` flattens into ambiguous segments | cubic #9 | **Deferred** |
| S2 | `walk.py:208` / `suggested_fix.py` | A wildcard-source `move_key` conflicts on any file with two matched entries | cubic #13 | **Fixed** — refused when the ledger is parsed |
| S3 | `ledger_check.py:255` | A pre-history entry cannot chain through a renamed declared path | cubic #23 | **Deferred**, documented as a constraint |
| S4 | `ledger_check.py:518` | Reserved spellings are keyed at the remap's literal path, not the walked one | cubic #14 | **Deferred** |
| S5 | `transform_check.py:192` | A destination beneath an open mapping, absent from the reference document, was a false red | cubic #19 | **Fixed** |
| S6 | `surfaces.py:247` | A project-level `pipelex_service.toml` is claimed by the service surface | cubic #20 | **Won't fix — as designed** |

## What was fixed, and how

- **A.** `_write_migrated_file` is now the per-file boundary in fact: it catches `FixTransactionError` and decides by re-reading the target whether the write landed (the exception cannot say; the file can) — blocked as unwritable when it did not, written with a warning when it did; and `prune_backups_except` sits inside its own `try`, so a backup that will not prune is a warning on a migrated file rather than an escape that aborts the walk. Tests: a transaction error after the write, one before it, a pruning failure — each with the sibling still migrated.
- **B.** `existing_backups_of` matches the whole name we write, stamp included (`\d{8}T\d{6}Z`). Test: `example.toml.bak.notes` survives while a stamped backup is pruned.
- **C.** `write_backup` unlinks the staged copy when the replace fails. Test: a failed backup leaves the directory holding only the source file.
- **D.** `lost_enumerated_spellings` exempts only a destination that admits `str`, which is what its docstring always said. Test: `Literal['a']` → `Literal[1]` loses `'a'`. The contract's fingerprint section now says a non-string literal's domain is invisible to the projection.
- **E.** The two golden reads in `transform_check.py` translate `OSError`/`ValueError` into `MigrationGoldenError` naming the file, mirroring `read_fingerprint_golden`. Test: a non-UTF-8 `defaults@1.toml` is refused by name.
- **F.** `multiple_of` divisibility is decided over `Fraction(str(x))`. Test: `0.3` → `0.1` is a widening.
- **H.** The older-shape generator drops `title` when it puts `heading` back and `section.enabled` when it puts `chatty` back. A second vacuity meta-test finds a document on which the rename *and* the move apply with nothing blocked, which is what makes the idempotence and prefix-coherence properties claims about a rename.
- **I.** The report-never-echoes test asserts the unsafe entry was reported; the telemetry test asserts the whole migrated document.
- **J.** Both docstrings now say what the pinned assertion measures: the old key stays in the raw dict, the new one is never added outside the table branch.
- **K.** `test_runner.py` uses the conftest fixture.
- **S2.** `MoveKeyOp` refuses a wildcard in its `table_path`, symmetric with the existing refusal on `new_table_path`, and the contract's wildcard section says why: with the destination pinned to one fixed key, "move each entry's key" is many-to-one and conflicts on any file where two matched entries carry the key. `test_a_wildcard_source_is_accepted` became two tests — the move is refused, an in-place kind keeps its wildcard.
- **S5.** The transform comparator's first claim reads the fingerprint *with its wildcards*: `deck.claude.new_name` is recorded as `deck.*.new_name`. Test: a rename beneath an open mapping whose destination the new reference document omits under that entry is tolerated.
- **S3, documented.** The pre-history containment rule reads each source at its literal, pre-entry path; the contract now says so and tells the author to address the material first, then rename it.

## The deferrals, and why

### L. An op-free `unsafe` entry can never reach the user — needs a ruling

`MigrationEntry.ops` is documented as legitimately empty when `safety = "unsafe"` (`ledger.py`), and `check_an_op_free_entry_is_unsafe` enforces exactly that shape: it is *the* form for "a change only a human can make". But `_rehearse_unsafe_entry` (`engine.py`) decides whether to report by rehearsing the entry's operations — and an entry with no operations rehearses to nothing, so it returns early and **the entry is never reported to anyone, ever**.

That is precisely the remedy R8 names for a tightened numeric bound, and the PR body says so: *"or `unsafe`, which is the only remedy a tightened numeric bound has, since no structural operation can repair a value."* The accounting accepts such an entry as sufficient; the engine then guarantees the user never hears about it.

**Not reachable today** — no ledger in the tree carries an op-free entry, and the reshape entry is `safe`. It fires the first time someone writes the shape the contract invites.

The three candidate answers are all design decisions:

1. **Report it always.** Restores the guidance, and reintroduces exactly what the rehearsal rule exists to prevent — a warning at every boot, forever, for every user whose file is already fine.
2. **Give the entry a predicate.** The honest one: the entry declares the paths whose domain narrowed, and the engine reports it when the document carries one of them. Costs a new ledger field, a contract change, and a `check-ledger` rule — but it is the only option that reports to the users who need it and stays silent for the rest.
3. **Refuse the shape.** Make an op-free entry illegal and force every narrowing to be expressible. Cheapest, and it contradicts the contract's own sentence plus R8's stated remedy.

A fourth road is tempting and wrong: have the engine validate the document against the model. The engine is deliberately model-free and filesystem-free — that is what lets the gates and a user's migration run the same code — and threading a model into it would cost that.

**Recommendation: (2), in Phase 3**, where `pipelex migrate` and boot tolerance land and the reporting surface exists to carry it. **Louis' call.**

### M. Same-second backup collision

`write_backup` clobbers an existing backup of the same stamp, and `runner.py` unlinks that path on a failed commit as though this run had created it. Two migrations of the same file inside one UTC second, the second having something to apply and failing to commit, lose the only copy of the original. Narrow, but it is the one scenario backups exist for. The fix is small (report whether the destination pre-existed; unlink only what this run created) but it touches the backup naming the contract states, so it goes with N as one backup-semantics pass.

### N. Symlinked configuration files

Confirmed mechanically: `read_file_snapshot` reads *through* the link, `assert_snapshot_unchanged` compares device/inode of the resolved file, and `replacement_snapshot.path.replace(snapshot.path)` then replaces **the link itself** with a regular file, leaving the real target untouched. A user with a dotfile-managed `~/.pipelex/pipelex.toml → ~/dotfiles/pipelex.toml` silently loses the linkage.

Deferred because the answer is a policy choice, not a bug fix — refuse a symlinked target, resolve and transact the target, or keep today's behaviour and document it — and because `file_transaction.py` is **shared with the `.mthds` fix loop**, so whatever is decided changes that path too.

### O. `telemetry.project.toml` is not a witness

`pipelex/kit/configs/telemetry.project.toml` is a different, sparser shape than the global `telemetry.toml` the telemetry surface uses as its kit witness. Measured: replaying the real `telemetry-config` ledger over it returns `changed=False, steps=0, blocked=0` and the very same string, so this is a latent coverage gap, not a live failure — and the property suite already samples sparse documents. Letting a surface carry several kit witnesses is small; it waits for a need.

### P / Q. Refinements to the R8 relation

- **P (#10)** — for a genuine union, taking the widest bound per kind is correct: a union accepts a value if any member does. The narrow hole is mixing the two sources — a binding top-level `Field(le=6)` merged with a union member's `le=100` yields `le=100`. Exotic; recording it means another golden format change.
- **Q (#25)** `gt=0` and `ge=1` accept the same integers, but `_strictest_bound` calls the swap a tightening — a false breaking verdict on an equivalent schema; the fix needs the value type threaded into `_describe_tightenings`.
- **Q (#26)** `_union_members` treats `list[int | str]` as one opaque member, so `list[int]` → `list[int | str]` reads as a narrowing.

Both Q items are crying-wolf failures. Worth doing as one deliberate pass over the relation, with fixtures per shape, rather than folded into a review round.

### S1. A quoted key containing `.` beneath an open mapping

`_flatten_into` joins segments with `.`, so a user's key `"gpt-4.1"` beneath an open mapping flattens to synthetic segments. Consequences today: none on any checked-in document (no surface document carries such a key), and the head-link model validation catches a misspelled destination regardless. The honest fix is one escaping scheme applied everywhere migration paths are split and joined — walk, applier, fingerprint, documents — which is a design pass, not a review fix.

### S3. Pre-history containment is literal

A pre-history entry that renames a declared table and then addresses a child under the new name is refused, because the containment rule reads the child's source literally against the declaration. Every such chain has an unchained equivalent — address the material first, then rename it — so the contract now states the constraint rather than the code growing a second walk.

### S4. Reserved spellings are keyed at the remap's literal path

`derive_reserved_registry` records a remapped-away spelling under the remap operation's own `table_path.key`; the reuse check at `ledger_check.py` looks it up at the current fingerprint path. An entry that remaps `section.mode` and then renames `section` → `area` in that order stores `section.mode=a`, and a later version bringing `a` back at `area.mode` is not caught. Reordering the ops (rename first) makes it work today. The fix keys reservations by the walk's final path; it needs the walk inside `derive_reserved_registry`, which is a moderate change for an exotic ordering.

## Won't fix, and why

- **E′ (#27)** — `surfaces.py` reads a *packaged* file. Missing or unreadable means a broken install; the traceback names the path; a gate-shaped refusal adds nothing an author can act on.
- **G (#17)** — `[""]` is never a reserved prefix, so every operation of such an entry is refused as acting on live material and the gate is red. Tightening the field's shape would be hygiene, not protection.
- **R (#7)** — by design, and it is what R8 ruled: for a free-form domain narrowed into an enumerated one, no remap can be *proved* complete because the old domain is infinite, so the remap *is* the author's account of the spellings that existed. Requiring `unsafe` there would forbid the exact case the coverage docstring names as the fit for a remap.
- **S6 (#20)** — the walk claims by filename, deliberately: a file named `pipelex_service.toml` is a service configuration wherever it sits, and migrating a stray project-level one is harmless and backed up. Restricting a surface by tier is machinery for a case nobody has.

## Round 2 — `/review` pass of 2026-08-16

Run on the branch after round 1, against `dev` at `052b9df06`, with the S5 charter (`wip/migrator-3/sequencing.md`) as the plan. Sources: the checklist pass, four specialist subagents (testing, maintainability, security/data-safety, a Claude adversarial pass) and a Codex adversarial pass. Every finding below was verified by reading or executing the code before it was acted on; the round-1 deferrals were excluded from the brief and are not repeated here.

**Plan completion.** Every S5 "Done when" item that this PR owns is present: `make cl` exists and is in `check` and `agent-check` (both gates run in under a second, which answers Checkpoint B's timing question); the R8 rule is in `_check_head_link` and in accounting, the whitelist projection with `pattern` excluded is in the fingerprint, the goldens were regenerated once, the contract's coverage row and fingerprint section moved with it, including the sentence naming validator-expressed narrowing as outside the gate; the telemetry back-entry and the `pre_history` verification are in the same PR. The join in `_reshape/` is post-merge work and is not part of this PR. The one commit outside the S5 scope, `cc1bc1b92` (`wip/bugs/enum-completeness-validators-over-user-keys.md`), was already recorded in the charter as riding along by choice.

### Fixed in this round

| Where | Issue | Reporter | What was done |
|---|---|---|---|
| `applier.py` | **Renaming or moving a table whose descendant is written in several chunks (`[a.b]` … `[a.c]` … `[a.b.d]`) re-homed only the first chunk and reported `applied`** — the user's file came out split between the old and the new name, and the next run conflicted. Reproduced on tomlkit 0.14; the parent-level proxy case was already handled, the nested case was not. | Claude adversarial | `_first_split_descendant` guards both operations: `CONFLICT` naming the split table, nothing written. A table interleaved at its own level still moves whole. Contract "Limits" bullet, changelog, and a parametrized red/green test. |
| `coverage.py` | **A remap on a path excused every narrowing of that path, a tightened bound included** — `Annotated[int, ge=1] \| Literal["auto"]` → `Annotated[int, ge=8] \| Literal[...]` with a `safe` remap of `auto` was green on all gates; a file saying `4` fails at boot. Real shape: `max_concurrency`, `seed`. | Claude adversarial | For a remapped origin only the bound half (`describe_tightenings`) is asked; a type change is still the remap's to answer for. Contract row sentence; red/green fixture. |
| `coverage.py` | **An over-deletion beneath a renamed table was invisible** — `rename a→b; delete_key [b] x` with `x` live at v2 was green (over-deletion compared by current spelling, and the convergence witness has no value for an optional `None` child). | Claude adversarial | Over-deletion is now decided by origin: each removed origin is carried through its nearest surviving ancestor's rename and that landing is looked up in the new schema. Red/green fixtures. |
| `runner.py` | **A `FixTransactionError` whose file did not carry the new text deleted the only backup** — with a single-file update that error only comes from the post-commit cleanup path, so `_carries()` false means a concurrent edit or an unreadable target: exactly the state a backup exists for. Also, the cleanup `unlink` calls were unguarded, so a permission error escaped the per-file boundary. | security specialist + Codex (multi-source) | The backup is kept whenever the transaction cannot vouch for the state, and the report names it (`backup_path` on a blocked plan). `_discard_backup` swallows an `OSError` into a warning. Runner docstring and contract "Backups" paragraph aligned; the existing test's assertion flipped, plus tests for the concurrent-edit, commit-`OSError`, unguarded-unlink, non-UTF-8, unreadable and removed-before-read branches. |
| `backup.py` | `existing_backups_of` globbed on the raw file name, so a name carrying a glob metacharacter could match — and prune — a sibling's only backup. | security specialist | Prefix match over `iterdir()`; test with `example_?.toml` beside `example_a.toml`. |
| `ledger_check.py` | `RESERVED_VALUE_REUSED` was produced by no test (its path twin was). | testing specialist | Red and green tests added. |
| `fingerprint.py` | The non-numeric-bound drop had no test. | testing specialist | `Decimal` bound fixture. |
| `docs/migration-ledger.md` | The contract said no surface carries an array of tables; `TelemetryConfig.otlp` is one, and the fingerprint records it as a terminal `list[table]` — a change inside an exporter entry is invisible to the coverage gate. | Codex + Claude adversarial | Both sentences corrected: the blind spot is named beside validator-expressed narrowing, with `otlp` as the live instance. The fingerprint format itself is deferred (below). |
| `reserved.py`, `narrowing.py`, `fingerprint.py` | A third hand-rolled `"."` path join; the union separator defined in two modules. | maintainability | `op_source_path` and one `UNION_SEPARATOR`. |
| `coverage.py`, `reserved.py`, `ledger_check.py`, `transform_check.py` | Docstrings said `check-ledger` reads the `before` document (the transform check does); a hardcoded count; a `MIGRATED_DOCUMENT_REJECTED` message that named the wrong starting document for a pre-history entry. | maintainability | Corrected; `_starting_document_label` used. |
| `pipelex/kit/agent_rules/commands.md`, `codex_commands.md` | The `agent-check` target list an agent without `make` follows omitted `check-ledger`. | checklist + maintainability | Sources fixed and `CLAUDE.md` / `AGENTS.md` regenerated with `make rules`. |
| `docs/migration-ledger.md` | "reads checked-in files and nothing else" — the convergence witness for a model-defaults surface is rendered from the live model (rendered, not fingerprinted). | maintainability | Sentence now says what the code does. |

### Deferred from this round

- **`key = "*"` is a literal key to the applier, and a `remap_value` over a container never fires** (Claude adversarial, verified). The walk spells `levels.*` and `check-ledger` accepts `*` at an open node, but `_expand_table_paths` expands only `table_path`, so a remap with `key = "*"` skips with "key '*' not found", and a remap over a `list[enum]` or `dict` value skips as "not a string" — while `_gather_enum_members` descends into containers, so coverage *demands* exactly those remaps for `pipelex.log_config.package_log_levels`, `preferred_agent_targets`, `img_gen_param_defaults.size`. Two coherent answers: teach the applier to expand a `*` key over an open node's entries (the contract's "each of these" reading, and the natural remedy for `dict[str, Enum]`), and have coverage demand `unsafe` for a lost member the remap cannot reach (`list[enum]`); or stop `_gather_enum_members` at the container boundary, mirroring `_collect_constraints` (the maintainability pass's reading), and regenerate the goldens. Either is a design pass with its own fixtures, and it changes the golden format, so it belongs with the R8 relation refinements (P/Q) — before S7 freezes the format.
- **An `unsafe` entry goes silent after a later `safe` entry renames its target** (Claude adversarial, reproduced): `unsafe@2` remaps `a.mode`, `safe@3` renames `a→b`; run 1 reports both, writes `[b] mode = "legacy"`; run 2 is clean while boot fails on `b.mode`. Either forbid it statically in `check-ledger` (a later entry may not rename a subtree an earlier unsafe entry addresses) or rehearse unsafe entries with their paths traced forward. Goes with L (the op-free unsafe entry) as one "what does `unsafe` promise" pass.
- **`list[Model]` is a terminal `list[table]` in the fingerprint** — a renamed field inside `OtlpExporterConfig` changes nothing and demands nothing. Documented now; recording the item model's fields under a synthetic segment is a format change and waits for the same pre-S7 window as P/Q and the `*`-key question above.
- **`up-migration-schemas` overwrites the head golden unconditionally and rides in `make up`** — a habitual `make up` after deleting a field rewrites `fingerprint@N` and erases the removal the coverage gate would have caught. Pre-existing (Phase 1), but this PR is what makes the chain a proof. Candidate: refuse the snapshot when the stored head shows removals or narrowings against the live model, and take `umig` out of `up`.
- **Replay continues after a blocked entry** (Codex): a rehearsed `unsafe` entry or a partially-applied conflicting `safe` entry does not stop later entries, so later entries — authored against a completed prior version — apply over a hybrid shape. This is what the contract says today ("while the rest of the file's entries proceed") and it is a design choice; recorded so the choice is a choice.
- **`min_supported_schema_version` has no reader** (Codex): the contract says the loader fails loudly below the floor, but no code determines a document's version. Held at zero and reserved for a squash, so it costs nothing today; the sentence overclaims until a squash and a version detection exist — Phase 3 or the first squash, whichever comes first.
- **The replay half of `migrate_file` catches only `TOMLKitError`** — a `PipelexUnexpectedError` from the applier, or a non-`TOMLKitError` from tomlkit, would cross the per-file boundary and abort the siblings. No trigger found; the applier's raises are "applier bug" cases where loud is arguably right. Recorded, not changed.
- **`narrowing.py` reports `int → float` and `enum → literal` (same members) as narrowings** — false reds, no real surface has the shape. Goes with Q.
- **Ownership, ACLs, xattrs and hard-link identity are lost on replace** (Codex) — the shared transaction primitive keeps mode only. Pre-existing on the `.mthds` path; a policy call together with N (symlinks) as the one backup/replace-semantics pass.
- **No directory `fsync` after the backup rename and the target replace** (security + Codex, low confidence): crash-durability of the ordering the contract promises. Cheap on POSIX; a decision on whether the guarantee is meant to hold across power loss.
- Maintainability items left as they are: the six-times hand-rolled ancestor-prefix loop (a helper is worth having when the next site appears); `MigrationReport.written_plans` / `blocked_plans` and `MigrationLedger.entry_for_version` have no caller yet (Phase 3's `pipelex migrate` is the reader — remove them there if it does not read them); a head-link narrowing is reported as `REMOVAL_NEEDS_A_BUMP` while `VALUE_DOMAIN_NARROWED` exists (the message says which; a distinct kind is a taste call); no `UNREADABLE` blocked reason (an unreadable file is reported as `UNWRITABLE` with a detail that says "read"); `_print_issues` duplicated across the two gate commands; `_KIT_CONFIGS_DIR` derived by path arithmetic; the temp-file prefix still says `pipelex-fix-`.
- Testing items left: `documents.py` has no direct test (reached through the transform check and the property suite); the two `MigrationReport` properties are untested because they are unused.

## Round 3 — `/code-review high` of the round-2 changes, 2026-08-16

Run over the staged round-2 diff, before it was committed. Every finding was reproduced in the venv (tomlkit 0.14) or against the gate before it was acted on. Working tracker for the round: `wip/pr-1112-round3-progress.md`.

### Fixed in this round

| Where | Issue | What was done |
|---|---|---|
| `applier.py` | **Round 2's split-descendant `CONFLICT` guard was a workaround for a tomlkit rendering-cache bug, and an incomplete one**: it looked at the merged dict facade of a nested out-of-order table, so a split table inside one of its chunks was invisible and the rename still tore the file with an `applied` verdict; and it fired on dotted keys interleaved inside a single table (`b.x = 1`, `c = 2`, `b.y = 3`), refusing a rename tomlkit performs correctly. The real cause: `Table.invalidate_display_name` walks `values()`, one item per key, so the later chunks of a split table keep the stale header. | The guard is gone. `_refresh_table_headers` walks the *body* of a renamed or moved item (Container body, proxy chunks, AoT elements) and clears every Table's `display_name`, so every chunk re-renders under the new path — rename and move now come out whole for every layout the parser accepts. The round-2 "Limits" bullet and changelog line are replaced; the CONFLICT fixtures became APPLIED-and-whole assertions, with the nested-proxy, interleaved-dotted and array-of-tables shapes added. |
| `coverage.py`, `narrowing.py` | **Round 2's split (`describe_tightenings` for a remapped origin) closed the bound half and left the type half open**: `Annotated[int, ge=1] \| Literal["auto","unbounded"]` → `Literal["unbounded"]` under a `safe` remap of `auto` was green on both gates while `retries = 4` fails at boot. | `describe_narrowing(remapped=...)` exempts only the string-typed members of the old type (`str`, `enum`, `literal`) — what a remap can rewrite — and still reports any other lost member and every tightened bound. `describe_tightenings` is removed. Gate fixture and unit test; contract row reworded. |
| `transform_check.py` | A hardcoded count in a docstring this round rewrote. | Reworded. |

### Deferred from this round

- **Renaming a table written in dotted-key form swallows the scalars after it** (pre-existing, reproduced): `[a]\nk.x = 1\nm = 3` + rename `k→kk` yields `[a]\n[a.kk]\nx = 1\n\nm = 3` — `a.m` becomes `a.kk.m`, verdict `applied`. `_replace_at` re-keys the dotted table with a plain `SingleKey`, so tomlkit renders a block header mid-body. The S4 table renames will meet any user file with a dotted section followed by a sibling scalar. Two remedies: refuse when the item's key `is_dotted` (a `CONFLICT` telling the user to write the section as a header), or preserve dotted-ness through `_replace_key_in_container`. Needs a decision, then a red/green fixture in `test_fix_applier_config_surface_shapes.py`.
- **The `UNWRITABLE` branch of the runner mislabels a landed write.** For the single-file commit the runner performs, `_commit_staged_updates` re-raises the original `OSError`/`FixWriteConflictError` when the replace itself fails (rollback of zero committed updates is trivially complete), so the only reachable `FixTransactionError` is the post-commit cleanup one — the write **landed**, and `_carries()` false means the file was changed or made unreadable afterwards. `blocked_detail` says "the file could not be written", `FileBlockedReason.UNWRITABLE` is documented as leaving the directory untouched, and the contract speaks of "a rollback it could not complete" — an unreachable path. Round 2's own table above states the correct reading. Fix is wording plus possibly a distinct reason (`CHANGED_DURING_RUN`); the reason-enum question goes with the `UNREADABLE` item from round 2.
- **The backup kept after an uncertain-state failure is pruned by the next successful run of the same file** — `prune_backups_except(keep=T2)` unlinks the round-1 copy whose provenance was certain, while the report told the user "the original is kept at T1". Either the message says the copy lives until the next successful run, or a backup made by a run that did not write is exempt from pruning. Policy call, with M/N and the replace-semantics items.
- **The over-deletion loop no longer fires on a rename onto a path the new schema keeps** (`label` live at v2, entry renames `label→title`, `title` new at v2): the old spelling-based loop reported `OVER_DELETION`; the origin-based one carries `label` to `title`, finds it in the new schema, and is silent. `check-ledger` refuses the same entry (`OP_ACTS_ON_LIVE_MATERIAL` + `CONVERGENCE_BROKEN`), so the defect cannot ship, but `check-migration-schemas` alone is green and no test pins either behaviour. Add the fixture, and decide whether the surface gate should say it too.
- **`_over_deleted_landings` mirrors `PathState.trace_to_origin`** (origin→landing vs current→origin, same longest-recorded-prefix loop). Round 2 said the ancestor-prefix loop earns a helper "when the next site appears"; this is that site — a `PathState.landing_of_origin` would let the caller collapse to one loop. Do it with the item above.
- Minor, confirmed: `reserved.py` keys a remap's value reservation by its op-time spelling, so a remap-then-rename in one entry never trips `RESERVED_VALUE_REUSED` (goes with S4 above); `str(chunk_key)` renders quoted/whitespace key text in a detail message; the `or {}` unpack repeated in `describe_narrowing`.
