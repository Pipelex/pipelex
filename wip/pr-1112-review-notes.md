# PR #1112 review triage — Migrator Phase 2

**State: analysis complete, nothing fixed yet.** Every finding below was verified against the code by hand (no subagents). No file has been edited, no PR thread has been replied to or resolved. The next session executes from this document.

PR [#1112](https://github.com/Pipelex/pipelex/pull/1112) → `dev`, branch `feature/Migrator-2`. **All CI is green** (every lint job, all eight test shards, typecheck, `doc-check`, both AI reviewers). Merge state is `MERGEABLE / BLOCKED` — branch protection waiting on a human approval, not a failing check.

Three bots left **33 unresolved threads**: greptile (1), codex (5), cubic (27). They were read in full — none truncated — and deduplicated into the clusters below.

## Disposition summary

| # | Where | Issue | Reporter(s) | Verdict | Disposition |
|---|---|---|---|---|---|
| A | `runner.py:98-109`, `backup.py:74` | `FixTransactionError` and pruning failures escape `migrate_file`, aborting every sibling | greptile #1, codex #4, cubic #16, #22 | **Confirmed** | **Fix** |
| B | `backup.py:71` | Pruning deletes any `<file>.bak.*`, including a user's own hand-made copy | cubic #28 | **Confirmed** | **Fix** |
| C | `backup.py:60` | Staged backup copy leaks when the replace fails | cubic #21 | **Confirmed** | **Fix** |
| D | `narrowing.py:60` | `Literal['a']` → `Literal[1]` suppresses the lost spelling entirely | cubic #15 | **Confirmed** | **Fix** |
| E | `surfaces.py:117`, `transform_check.py:256-272` | An unreadable template or golden crashes the gate with a raw traceback | cubic #27, #29 | **Confirmed** | **Fix** |
| F | `narrowing.py:165` | Float `multiple_of` modulo reports a widening as a narrowing | codex #5, cubic #24 | **Confirmed** (latent) | **Fix** |
| G | `ledger.py:112` | `declared_removed_paths = [""]` satisfies the guard vacuously | cubic #17 | **Confirmed** (not exploitable) | **Fix** |
| H | `test_replay_properties.py:166` | The "older shape" fixture keeps the new keys, so renames CONFLICT instead of applying | cubic #18 | **Confirmed** | **Fix** |
| I | `test_engine.py:268`, `test_telemetry_back_entry.py:41` | Tests pass without exercising the guarantee they name | cubic #31, #33 | **Confirmed** | **Fix** |
| J | `test_fix_applier_rename_dom_consistency.py:6` | Module docstring contradicts its own pinned assertion | cubic #30 | **Confirmed** | **Fix** |
| K | `test_runner.py:250` | `_write_ledger` duplicates the `write_ledger_file` conftest fixture | cubic #32 | Confirmed | **Fix** (cleanup) |
| L | `engine.py:127` | An op-free `unsafe` entry is structurally unreportable | codex #2 | **Confirmed** | **Defer — needs a ruling** |
| M | `backup.py:60`, `runner.py:99` | Two runs in the same UTC second can lose the only prior backup | codex #6, cubic #12 | Confirmed (narrow) | **Defer** |
| N | `runner.py:31-32` | A symlinked config file is replaced by a regular file, breaking the link | codex #3, cubic #8 | **Confirmed** mechanically | **Defer — policy call** |
| O | `surfaces.py:286` | `telemetry.project.toml` is not a neutrality witness | cubic #11 | Confirmed (latent) | **Defer** |
| P | `fingerprint.py:390` | Union-member constraints merged into one dict | cubic #10 | Partly valid | **Defer** |
| Q | `narrowing.py:123`, `:75` | `gt=0` vs `ge=1` on ints; `list[int]` → `list[int \| str]` | cubic #25, #26 | **Confirmed** | **Defer** |
| R | `coverage.py:315` | A remap over a free-form domain suppresses the narrowing | cubic #7 | Not verified | **Defer — verify first** |
| S | `documents.py:40`, `walk.py:208`, `ledger_check.py:255`, `:518`, `transform_check.py:192`, `surfaces.py:247` | Six gate-semantics claims | cubic #9, #13, #23, #14, #19, #20 | Not verified | **Defer — verify first** |

## The confirmed fixes, with the evidence

### A. Per-file isolation is not actually per-file — the PR's own headline contract

`migrate_file` catches `FileNotFoundError`, `OSError` and `FixWriteConflictError`. It does **not** catch `FixTransactionError`, and that is not an `OSError` — measured: `FixTransactionError.__mro__` is `PipelexUnexpectedError → PipelexError → Exception`. `commit_file_updates` raises it in two places:

- `file_transaction.py:155` — commit failed *and* rollback was incomplete;
- `file_transaction.py:190` — **the targets were committed successfully** but temp-file cleanup failed.

Either escapes `_write_migrated_file` → escapes `migrate_file` → aborts the `for` loop in `migrate_directories`, so every sibling file after it is never processed. The second case is worse than a lost sibling: the file *was* rewritten and its plan is thrown away, so the user's file changed and the report says nothing. `prune_backups_except` (`runner.py:109`) sits outside any `try` and `candidate.unlink()` can raise `OSError` post-commit, with the same consequence.

This directly contradicts `runner.py:3-7`, `file_transaction.py:10-13`, the contract's "Per-file transactions", and the PR body.

**Fix.** Wrap the commit and the prune in the per-file boundary. The subtlety worth getting right: after a `FixTransactionError` the caller cannot tell *from the exception* whether the target was committed. Re-reading the target and comparing it against `new_content` decides it honestly and needs no new error class (a new class would drag `make gei` + `make gep` along). A pruning failure must never turn a written file into a blocked one — it is a warning on a committed plan.

**Tests:** a fake raising `FixTransactionError` from `commit_file_updates` for one file of three, asserting the other two are still migrated and that the failing file's plan reports the truth in both directions (committed / not committed); a prune failure leaving `was_written=True`.

### B. Pruning deletes the user's own files

`existing_backups_of` globs `f"{path.name}{BACKUP_INFIX}*"` — anything after `.bak.` matches — and `prune_backups_except` unlinks every match but the fresh one, on every successful migration. So a user's `pipelex.toml.bak.notes` or `pipelex.toml.bak.manual` is silently deleted. The docstring at `backup.py:44-47` even acknowledges "the backups are the user's files too".

Louis' own `~/.pipelex/` survives only by naming luck: `pipelex.toml.bak-before-claude-strip-20260623` uses a dash, and `pipelex.toml.pre-reshape.bak` ends with `.bak`. Neither matches — but neither would a rename away from that luck.

**Fix.** Match only names whose suffix is the stamp we write: `%Y%m%dT%H%M%SZ`, i.e. 8 digits, `T`, 6 digits, `Z`. **Test:** a neighbouring `*.bak.notes` survives a migration; a real stamped backup is still pruned.

### C. Staged backup copy leaks

`write_backup` (`backup.py:58-61`) stages a temp file then calls `staged_path.replace(destination)`. If the replace raises, the staged copy is left in the user's configuration directory. Every other staging site in `file_transaction.py` unlinks on failure (lines 86-88, 97-99); this one does not. **Fix:** the same `try/except OSError: unlink; raise`.

### D. A changed non-string literal loses its spellings silently

`_gather_enum_members` (`fingerprint.py:412`) records `Literal` args **only when they are `str`**, and `_render_type` renders every `Literal[...]` as the bare token `literal` regardless of its args. So:

- `Literal['a']` → `value_type="literal"`, `enum_members=['a']`
- `Literal[1]` → `value_type="literal"`, `enum_members=None`

`lost_enumerated_spellings` line 60 then reads `not after.enum_members and _is_type_widening('literal', 'literal')` → the widening test is trivially true (identical rendering), so the function returns `[]`. `describe_narrowing` sees no type change and no constraint change. **The gate says nothing at all** about a change that invalidates every file carrying `'a'`.

The exemption at line 60 exists for exactly one case — an enumerated type *relaxed into a free string* — and the current test is too weak to express it. **Fix:** exempt only when the destination actually admits `str`, i.e. `STRING_TYPE in _union_members(rendered=after.value_type)`. Two lines, and it makes the code say what its own docstring (lines 53-56) says.

Worth recording beside it: a non-string `Literal`'s domain is invisible to the fingerprint entirely. That belongs in the contract's blind-spot paragraph, next to validator-expressed narrowing.

### E. A broken template or golden crashes the gate instead of reddening it

- `surfaces.py:117` — `reference_documents()` reads `kit_template_path` live with no guard. `check_ledger_cmd` catches only `MigrationError`, so a missing or unreadable template produces a traceback rather than a red gate with a remedy.
- `transform_check.py:258` / `:272` — `path.read_text()` guarded only by `.exists()`. A permission error or a golden whose bytes are not UTF-8 escapes; `check_migration_schemas_cmd` wraps only `MigrationError`, so the gate dies without ever printing the issue list.

Both violate the commands' own "a red gate has to say what to do" contract, and the codebase already has the pattern: `read_fingerprint_golden` translates `OSError`/`ValueError` into `MigrationGoldenError`. **Fix:** the same translation at these three reads. No new error class needed, so no `gei`/`gep`.

### F. Float `multiple_of` reports a widening as a narrowing

`_describe_multiple_of` (`narrowing.py:165`) tests `before_step % after_step == 0` in binary float. `0.3 % 0.1` is `0.09999999999999998`, so relaxing `multiple_of=0.3` to `multiple_of=0.1` — a widening — is reported as a tightening and demands a breaking bump. **Latent today:** the R8 census found no `multiple_of` on any surface (the seven bounds are `gt`, `ge`, `le`). **Fix:** compare via `Fraction(str(x))` so divisibility is exact. Cheap, and it removes a crying-wolf failure before anyone meets it.

### G. A vacuous pre-history declaration

`check_pre_history_declares_what_it_removed` (`ledger.py:112`) tests only that the list is non-empty, so `declared_removed_paths = [""]` passes. **It is not exploitable** — `_reserved_at_or_above` looks up whole dotted prefixes, and `""` is never one of them, so no operation gains permission from it and the entry fails elsewhere. Still worth closing: the flag's whole justification is that the declaration replaces the diff. **Fix:** validate each entry as a non-empty dotted path with no empty segments.

### H. The "older shape" fixture does not produce an older shape

`_documents_at_an_older_shape` (`test_replay_properties.py:154-177`) draws a *current-valid* document and then adds the retired keys (`heading`, `chatty`) **without removing their new destinations** (`title`, `section.enabled`). The applier treats an occupied destination as a `CONFLICT`, so the rename and the move write nothing and route their entry to `blocked[]` — unless the sampler happened to drop the matching new key that draw. Idempotence and prefix coherence therefore mostly exercise a stable-conflict fixture rather than a real rename/move migration, and the vacuity meta-test does not catch it because `did_change_document` also counts a conflicting entry's partially applied ops.

**Fix:** when injecting `heading`, drop `title`; when injecting `chatty`, drop `section.enabled`. **Then mutation-test it** — the properties must go red under an engine that breaks rename idempotence, which is the whole claim.

### I / J / K. Tests and one docstring

- **#31** `test_a_report_never_echoes_a_value_read_from_the_users_file` asserts only that the dump omits the secret; it never asserts the unsafe entry was reported at all, so it passes if nothing was blocked. Add `assert len(replay.blocked) == 1`.
- **#33** the telemetry back-entry test pins `mode`/`api_key` and the absence of one root key; the four dropped settings and the other moved values ride only on `extra="forbid"`. Assert them explicitly — data fidelity is the entry's headline.
- **#30** the module docstring of `test_fix_applier_rename_dom_consistency.py` says tomlkit "deletes the key from the dict", while its own pinned assertion measures the opposite: `"retention" in raw_keys` and `"keep_days" not in raw_keys`. The stale state is *old key still present, new key never added*. **The same wording was copied into `applier.py`'s `_rename_key_in_place` docstring — fix both, and check `docs/migration-ledger.md` for the same sentence.**
- **#32** `_write_ledger` in `test_runner.py` duplicates the `write_ledger_file` conftest fixture; both resolve to `ledgers_dir(...)`. Use the fixture.

## The deferrals, and why

### L. An op-free `unsafe` entry can never reach the user — the one that needs a ruling

`MigrationEntry.ops` is documented as legitimately empty when `safety = "unsafe"` (`ledger.py:97-98`), and `check_an_op_free_entry_is_unsafe` enforces exactly that shape: it is *the* form for "a change only a human can make". But `_rehearse_unsafe_entry` (`engine.py:126-128`) decides whether to report by rehearsing the entry's operations — and an entry with no operations rehearses to nothing, so it returns early and **the entry is never reported to anyone, ever**.

That is precisely the remedy R8 names for a tightened numeric bound, and the PR body says so: *"or `unsafe`, which is the only remedy a tightened numeric bound has, since no structural operation can repair a value."* The accounting accepts such an entry as sufficient; the engine then guarantees the user never hears about it.

**Not reachable today** — no ledger in the tree carries an op-free entry, and the reshape entry is `safe`. It fires the first time someone writes the shape the contract invites.

**Why this is a ruling and not a fix.** The three candidate answers are all design decisions:

1. **Report it always.** Restores the guidance, and reintroduces exactly what the rehearsal rule exists to prevent — a warning at every boot, forever, for every user whose file is already fine.
2. **Give the entry a predicate.** The honest one: the entry declares the paths whose domain narrowed, and the engine reports it when the document carries one of them. Costs a new ledger field, a contract change, and a `check-ledger` rule — but it is the only option that reports to the users who need it and stays silent for the rest.
3. **Refuse the shape.** Make an op-free entry illegal and force every narrowing to be expressible. Cheapest, and it contradicts the contract's own sentence plus R8's stated remedy.

There is a fourth road worth naming because it is tempting and wrong: have the engine validate the document against the model. The engine is deliberately model-free and filesystem-free — that is what lets the gates and a user's migration run the same code — and threading a model into it would cost that.

**Recommendation: (2), in Phase 3**, where `pipelex migrate` and boot tolerance land and the reporting surface exists to carry it. **Louis' call.**

### M. Same-second backup collision

`write_backup` clobbers an existing backup of the same stamp, and `runner.py:101/104` unlinks that path on a failed commit as though this run had created it. Two migrations of the same file inside one UTC second, the second failing to commit, lose the only copy of the original. Narrow, but it is the one scenario backups exist for. The fix is small (report whether the destination pre-existed, unlink only what this run created) but it touches the backup naming the contract states, so it goes with M/N as one backup-semantics pass.

### N. Symlinked configuration files

Confirmed mechanically: `read_file_snapshot` reads *through* the link, `assert_snapshot_unchanged` compares device/inode of the resolved file, and `replacement_snapshot.path.replace(snapshot.path)` then replaces **the link itself** with a regular file, leaving the real target untouched. A user with a dotfile-managed `~/.pipelex/pipelex.toml → ~/dotfiles/pipelex.toml` silently loses the linkage.

Deferred because the answer is a policy choice, not a bug fix — refuse a symlinked target, resolve and transact the target, or keep today's behaviour and document it — and because `file_transaction.py` is **shared with the `.mthds` fix loop**, so whatever is decided changes that path too. That makes it a cross-cutting decision, not a migrator one.

### O. `telemetry.project.toml` is not a witness

`pipelex/kit/configs/telemetry.project.toml` exists and is a different, sparser shape than the global `telemetry.toml` that the telemetry surface uses as its kit witness. An operation could be neutral over the global template and misbehave on a fresh project file.

**Measured, so the note is honest: it is neutral today.** Replaying the real `telemetry-config` ledger (the eleven-op back-entry) over `telemetry.project.toml` returns `changed=False, steps=0, blocked=0`, and the returned text is *the same string object*. So this is a latent coverage gap, not a live failure. The fix — let a surface carry more than one kit witness — is small and strengthens the gate; it is deferred only because it is not a defect today and the session is pausing.

### P / Q. Refinements to the just-landed R8 relation

- **P (#10)** — constraints are gathered from the field's own metadata *and* from every union member, then folded into one dict taking the widest per kind. For a genuine union that is **correct**: a union accepts a value if any member does, so the widest bound *is* the domain. The real (narrow) hole is mixing the two sources — a binding top-level `Field(le=6)` merged with a union member's `le=100` yields `le=100` and loses the constraint that actually binds. Exotic; recording it costs another golden format change days after R8 fixed one. Defer.
- **Q (#25)** `gt=0` and `ge=1` accept the same integers, but `_strictest_bound` sorts `(1.0, False) > (0.0, True)` and calls the swap a tightening — a false breaking verdict on an equivalent schema. Real, and the fix needs the value type threaded into `_describe_tightenings`.
- **Q (#26)** `_union_members` treats `list[int | str]` as one opaque member, so `list[int]` → `list[int | str]` reads as a narrowing though every old list stays valid. The docstring at `narrowing.py:87-88` shows the bracket handling was deliberate — but it guards the opposite error, and this direction was not considered.

Both Q items are crying-wolf failures (a false red an author can only answer with a spurious bump), which is the failure mode `narrowing.py`'s own docstring names. Worth doing — as one deliberate pass over the relation, with fixtures per shape, rather than folded into a review round.

### R / S. Eight claims not yet verified

`coverage.py:315` (remap over a free-form domain), `documents.py:40` (a quoted key containing `.` flattens into ambiguous segments), `walk.py:208` (a wildcard-source `move_key` to a fixed destination), `ledger_check.py:255` (a pre-history entry cannot chain through a renamed declared path) and `:518` (a remapped spelling returning after its path is renamed in the same entry), `transform_check.py:192` (a valid destination beneath an open mapping rejected because it is absent from the reference document), `surfaces.py:247` (a project directory's `pipelex_service.toml` claimed though the artifact is global).

**These were read and clustered but not verified against the code.** Do not treat them as confirmed and do not reply to their threads until they are. Several look like genuine gate-semantics questions; #19 in particular would be a false red on ordinary content, which is the failure this project cares most about.

## How to resume

1. Re-read this file. The verdicts in §"The confirmed fixes" are measured and need no re-verification.
2. Verify §R/S (eight claims), then fold each into the fix/defer split.
3. Get Louis' ruling on **L** — it is the only one that blocks a design decision.
4. Fix A–K, TDD-first, then `make agent-check`, `make cmig`, `make cl`, `make agent-test` (expect the one pre-existing `test_customize_backends_config_with_default_selection` failure under load — it passes standalone and this branch does not touch it).
5. Reply on **every** thread and resolve only the ones actually addressed — deferrals stay open. Thread IDs are in the PR; re-fetch with the GraphQL query in the `review-pr-agents` skill rather than trusting a copied list.
6. ⚠ Every command in this worktree needs the isolated `HOME` — see `wip/migrator-3/sequencing.md` § "S5 Session 4" in the workspace repo.

**Nothing in this round changes the merge decision by itself.** CI is green and the PR is reviewable as it stands; A–K make it better, and L is the one thing worth settling before Phase 3 builds on top of it.
