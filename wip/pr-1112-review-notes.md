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
