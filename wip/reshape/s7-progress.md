# S7 — landing the pair: progress in `_reshape/`

The `_reshape/` half of [S7](../../../wip/migrator-3/sequencing.md#s7--land-the-pair-louis-go-twice-merge-and-release), tracked as it is built. The release half runs in `pipelex/` on `dev` and is not this document's subject. Everything below is committed and pushed; what is left of S7 is the merge, and that is Louis' go.

## Where it stands

| # | Item | State |
|---|---|---|
| 1 | The final join — re-check, not a join | ✅ `dev` has not moved |
| 2 | The out-of-walk warning text (#1114 review §1) | ✅ built, tested, documented |
| 3 | `add-migration` re-derive, compared op for op | ✅ done — the two agree |
| 4 | The two Phase-3 end-to-end tests on **old-shape** fixtures | ✅ built, mutation-tested |
| 5 | The two #1111 review items | ✅ both built |
| 6 | `make check` + `make agent-test` | ✅ both green |
| 7 | Mark #1111 ready, retitle, **(Louis go)**, merge | ✅ ready + retitled — ⏳ **the merge is Louis'** |

## 1 — the final join is a re-check

Verified 2026-08-17: `git rev-list --left-right --count origin/dev...HEAD` reads `0 11` against `origin/dev` = `6264de0fd`, the tree is clean, and #1111 reads `MERGEABLE` / `CLEAN` at head `a93c5caad`, still a draft. So the fourth join was the final one. Every S7 precondition re-verified: both `migrate_cmd.py` modules and `.claude/skills/add-migration/SKILL.md` resolve on `dev`, `/release` carries step 3b, and the only remote `release/` branch is the merged `origin/release/v0.45.0`. **Re-run the fetch before merging** — `dev` cuts a release every one to three days, and if it has moved the verb is `git merge origin/dev`, never `rebase`.

## 2 — the warning names `pipelex migrate` only where it would write

`stale_configuration_warning` now takes `walked_dirs` and splits its stale files into the ones `pipelex migrate` would reach and the ones it would not, closing #1114 review §1. A file outside the walk gets "…is yours to update where it lives" instead of a command that would report nothing to do; a load spanning both gets both sentences, each naming its own files; the blocked-material sentence drops the command name when nothing is in reach. Same rule as part 3's ruling on the validation error — *a remedy is named only where it would write*. `--config-dir` was deliberately **not** added, per the review's own reasoning.

**The one design decision worth knowing.** The walk had to become readable from the loader, and it could not be imported: `config_loader → migration.run → config_loader` is a two-node cycle, and pyright's `reportImportCycles` counts a function-level edge exactly like a module-level one, so a deferred import is not a way out. The derivation therefore moved **down** onto `ConfigLoader.existing_config_dirs`, and `migration.run.config_directories_to_migrate()` now reads it and does nothing else. One derivation, read from both ends — which is the property that keeps a boot from promising a remedy the command declines. The three loaders each pass `config_manager.existing_config_dirs`.

Tests are in `tests/unit/pipelex/system/configuration/test_boot_tolerance.py::TestWhatTheWarningSays` (out-of-walk, the mixed case, the walk-is-not-recursive specimen, and the symlinked file below) and each was mutation-tested. `tests/unit/pipelex/migration/test_migration_run.py::TestWhichDirectoriesAreWalked` was rewritten to patch the loader's two directory *properties* rather than replace the `config_manager` singleton — with the singleton mocked out, the delegation and the derivation would both go untested. `docs/migration-ledger.md` → "Boot tolerance" carries the rule; the changelog's boot-tolerance bullet was amended rather than given a new one, the feature being unreleased.

**Both ends of "one derivation" are now pinned by a sentinel, and the first attempt was not.** The review caught it: `assert config_directories_to_migrate() == config_manager.existing_config_dirs` is a tautology, since the function *is* that expression and both sides came from the same patched properties — it would have passed just as well over a second derivation, which is the only thing it was there to forbid. Each end now patches `ConfigLoader.existing_config_dirs` to a value neither end could compute and asserts the answer is that value: the migrate side must return the sentinel directory, and the loader side, walking nothing, must decline to name the command for the very file it just carried forward. Both mutation-tested by re-deriving the walk locally at each end.

**One real bug came out of the same review, and it is a common setup rather than a corner.** `_is_within` resolved the whole path before taking its parent, so a `pipelex.toml` **symlinked out to a dotfiles repository** — chezmoi, stow and yadm all do this — landed on the target's directory and was told `pipelex migrate` could not reach it. The walk enumerates the link by `iterdir` and writes straight through it, so the command reaches it perfectly well; the warning was sending the user to hand-edit a file the tool would have fixed. The fix is to resolve the *parent* and not the file (`path.parent.resolve()`), which keeps the reason the resolve was there — a `config_dir=` reaching the same directory by another spelling — and drops the question it was accidentally answering, namely where the file points.

## 3 — the re-derive, and what it proved

The entry was re-derived **blind to the ledger** and compared to the hand-authored one. Method: roll `pipelex-config.toml` back to `current_schema_version = 1` with the entry removed, delete the `@2` goldens, run `make cmig` to see the gate refuse — it does, with `removal_needs_a_bump` naming every removed path — then reconstruct the old→new path mapping from `fingerprint@1` versus the live fingerprint by subtree-shape matching plus a parent/child affinity fixpoint, and compare that mapping against the one `walk_entry` induces from the entry. The script is `derive.py` under the job scratch directory; it is a one-off, not a checked-in gate. The ledger and goldens were restored **by file copy, never `git checkout`**, and `cl` + `cmig` are green again with both files unmodified.

**Result: no disagreement.** 192 of the 200 moves were derived independently and every one is identical to the entry's. Deletions match exactly: `[migration]` and its three descendants, `plugins.boot_orchestrator`, `session_id` — precisely the three things the entry's `guidance` says go away, and the R4/R5 rulings. No dead ops, no occupied destinations, and no removed path left in place.

**The eight the derivation could not decide are not decisions the entry makes**, which is the finding worth keeping. A fingerprint is a *type* projection, so two `bool` leaves under one table, or a `list[str]` in two places, are indistinguishable in it — that is why `plugins.disabled` and five booleans came back undecidable. But the entry's 37 operations name **only tables**, with exactly two exceptions, both `delete_key` on the two retired scalars (`plugins.boot_orchestrator`, `session_id`). Every leaf travels with its parent table, name intact, so the entry contains no per-leaf assignment that could be got wrong. The ambiguity is a property of reconstructing a rename map from a type projection, not a gap in the entry — and it is one more instance of the rule this project has met before: *a type projection cannot decide schema membership*.

## 4 — the end-to-end tests on a pre-reshape machine

`tests/e2e/pipelex/cli/test_migrate_commands.py` gains `TestAPreReshapeMachine`, and the entry that the reshape adds now has an end-to-end proof it never had: it was proved by the engine's own goldens and by nothing else. The rest of the chain is what the class adds — the walk, the filesystem, the backup, the binary a person types.

**The fixture is `goldens/pipelex-config/defaults@1.toml`, read live from the package.** ⏸ C's correction retired the recipe the charter carried (`git show 052b9df06:.pipelex/pipelex_override.toml` cannot work — the file is gitignored), and neither remaining candidate is as good as this one: `defaults@1` *is* the packaged `pipelex.toml` as it stood at schema 1, the very document the entry was authored against, so it names every path the entry touches and nothing it does not. Read live rather than transcribed, for the same reason the telemetry fixture is: a transcribed one would eventually describe a shape the ledger no longer migrates and would go on passing. The project tier beside it is hand-written from the table headers of this machine's `~/.pipelex/pipelex_override.toml.pre-reshape.bak` with **every value invented** — that file is personal, and a checked-in fixture carries none of a person's values.

Five tests, both loops:

- **the human loop** — boots stale, `pipelex migrate --yes`, both files named in the report, one backup each holding the original, boots clean. Its strong assertion is that the migrated global file says *exactly what the package's own `pipelex.toml` says today*, compared semantically because the entry's guidance says layout moves; `cmig` proves the engine does that, and this proves the command does.
- **the agent loop** — the JSON plan names the entry per file rather than once for the run, writes nothing and leaves no backup, then the apply writes both.
- **two surfaces in one run** — the only place two ledgers meet, which is where a misclaimed file would either be reported clean or handed a ledger with nothing to say about it. Four files written, then clean.
- **no user value rendered** — a bucket name planted in the tier, across the human CLI, the JSON plan, the Markdown plan and the apply. A bucket name rather than a credential because the main configuration holds none, secrets arriving through the environment; it is still private infrastructure in the file a person pastes into an issue.
- **old *and* wrong** — a pre-reshape file carrying a key no entry explains. The boot fails, in one envelope, and the block reports both halves: the reshape is pending on this file, and one path is a person's.

**Mutation-tested.** Pointing the fixture at `defaults@2` (a machine already migrated) reddens four of the five; the fifth is the value test, whose subject is the tier, correctly unaffected. Adding one key to "today's document" reddens the semantic comparison, so it is not comparing something to itself.

**Why a new class rather than a rewrite of the two telemetry tests.** The charter says "point the two end-to-end tests at old-shape fixtures", and the two it means are the human and agent loops — both are covered here. Rewriting them in place would have cost the coverage they already carry: `telemetry-config@2` is a *pre-history* entry against a hand-authored flat document, a different shape of change from a root rename, and it is the only entry of that kind in the tree.

## 5 — the two #1111 review items

**`pipe_func_execution_transport.py`** no longer names `pipe_func_config.timeout_seconds`. Verified 2026-08-16 that our Daytona plugin owns its own root (`daytona.toml` → `pipe_func_timeout_seconds`) and does not extend `[interpreter.pipe_func]`, which holds `execution_mode` and nothing else — so the honest sentence is that the timeout is plugin-configured, and the docstring now says that rather than asserting a core address no reader could ever find.

**`RuntimeHub.reset_boot_state` now releases the isolated-execution probe**, and the docstring says why. Of the three options in the note, "leave the asymmetry unexplained" was the weakest and the other two were a real choice; releasing it wins because the probe *is* process-global state a boot established, and it is the one of the three written **conditionally** — only a plugin claiming `HubSlot.ISOLATED_EXECUTION_PROBE` installs one — so a boot that claims nothing inherits rather than overwrites. The note's argument against rested on the probe having no module-level accessor; it does (`is_in_isolated_execution`, read by `ReportingManager`), so that half did not survive checking. Pinned by a second test in `tests/unit/pipelex/test_runtime_boot_releases_boot_scoped_state.py`, mutation-tested.

## 6 — the gates, and the one doc a drift review turned up

`make check` is green end to end, `check-migration-schemas` included, and `make agent-check` is green with both drift contracts re-acked. Two contracts opened on this session's changes and each was reviewed rather than waved through:

- **`hub-layering-convention`**, on `runtime_hub.py`. The partition table was re-derived rather than read — every public module-level function enumerated from the module by AST and checked against the page — and it is still complete; the probe release adds no accessor and the page says nothing about what a teardown releases, so no sentence in it moved.
- **`config-docs`**, on `config_loader.py` and `config_surface.py`. The contract's own question is whether anything narrowed a value domain the fingerprint cannot record, and the answer is no by construction: neither trigger touches a config model, and no ledger moved.

That second review did turn up one genuinely stale page, in the direction the contract exists to catch. **`docs/configuration/index.md` documents the merge order and the new four-section layout and said nothing about a file written against the old one** — and this branch is what makes that a user's problem, because `pipelex-config@2` is the surface's first entry ever, so from this release every existing installation's own `pipelex.toml` is the file that goes out of date. The page now carries a short note on the tolerant boot, the doctor row, `pipelex migrate` and its timestamped backup, and the out-of-walk rule for a `config_dir` load, linking the Migration Ledger page — which lives in the contributor nav and had no path from the configuration section at all.

## 7 — where the pull request stands, and what is left

The branch is pushed as one commit on top of the fourth join, `make check` and `make agent-test` both green before it. **#1111 is out of draft and retitled** — the `MERGE AFTER Migrator Phase 3 —` prefix is gone, because the condition it named holds: parts 1, 2 and 3 are all merged on `dev` as #1113, #1114 and #1115. Its description no longer opens with the embargo; it opens with the embargo being lifted, and carries a short section on what the final pass added. `dev` was re-fetched immediately before the push and has not moved from `6264de0fd`, so the branch is still 0 behind and the final join stayed a re-check.

**The review round on that push is triaged and answered.** Every check is green, cubic's included, and it left four findings, all of them acted on: the symlink bug in `_is_within` (P2, a real one — §2 above), the tautological delegation assertion (§2 above), an unqualified module path in `pr-1111-review-notes.md`, converted to name the field rather than a line number so it cannot go stale again, and this document's own sections being out of numeric order.

**What is left in S7 is not this venue's.** The merge is Louis' go. Then `/release` runs in `pipelex/` on `dev` — a minor bump, with step 3b firing on the `pipelex-config@2` entry — and then the first machine, whose first line is restoring this laptop's two `*.pre-reshape.bak` files under their live names, or the run finds nothing to migrate and proves nothing.

## Related

- The runbook: [`wip/migrator-3/sequencing.md`](../../../wip/migrator-3/sequencing.md) § S7, and ⏸ C above it for the four corrections it folded in.
- The #1111 review deferrals: [`pr-1111-review-notes.md`](./pr-1111-review-notes.md) — items 1 and 2 are the ones S7 owns and both are now done; 3, 4, 5, 6 and 7 have their own homes.
- The #1114 review deferrals: `wip/migrator-pr-1114-review-followups.md` on `dev` — §1 is the one S7 owns, and it is done.
