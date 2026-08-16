# PR #1112 — round 3 (`/code-review high` of the staged round-2 changes), progress tracker

Working file so the session can pause and resume. Branch `feature/Migrator-2`, worktree `_migrator/`. The round-2 fixes were STAGED but uncommitted when this round started; round-3 edits go on top of them. Full findings are in the review report; the triage below is what was decided.

## Fix-now set (in order)

| # | Item | Status |
|---|---|---|
| 1 | `applier.py` — replace the split-descendant CONFLICT guard by the tomlkit root-cause fix: clear every Table's stale `display_name` in the renamed/moved subtree so all chunks re-render under the new name. Covers the nested-proxy miss (`:411`), the interleaved-dotted false positive (`:423`), and drops the documented "limit" from CHANGELOG + `docs/migration-ledger.md`. Tests: turn the three CONFLICT fixtures into APPLIED-and-whole assertions, add nested-proxy + interleaved-dotted cases. | DONE — `_first_split_descendant` + `_split_table_detail` removed, `_refresh_table_headers` added and called from `_replace_key_in_container` and the move; tests rewritten (5 shapes × rename+move, root proxy, nested proxy); CHANGELOG entry rewritten, contract "Limits" bullet dropped |
| 2 | `coverage.py:351` — a `safe` remap must exempt only the string members it can rewrite; a lost non-string member of a union still counts as a narrowing (`describe_narrowing` type half must still run for remapped origins). Test: `int \| Literal` → `Literal` under a remap must be red in `check_surface`. | DONE — `describe_narrowing(remapped=...)` exempts only `str`/`enum`/`literal` members; `describe_tightenings` removed; gate test + unit test added; contract table row reworded |
| 3 | `transform_check.py:38` — drop the hardcoded count "Three things". | DONE |
| 4 | Deferrals written into `wip/pr-1112-review-notes.md` § Round 3 (see list below). | DONE — § Round 3 appended to `wip/pr-1112-review-notes.md` |
| 5 | `make agent-check` + targeted tests + `make agent-test`. | DONE — agent-check green, agent-test all passed |

## Deferred (to be written into `wip/pr-1112-review-notes.md`, not fixed now)

- `applier.py:374` pre-existing: renaming a dotted-form table (`k.x = 1` then sibling `m = 3`) swallows the siblings under `[a.kk]` — decision needed: refuse on `is_dotted`, or preserve dotted-ness in `_replace_key_in_container`.
- `runner.py:119` UNWRITABLE wording: for a single-file commit the only reachable `FixTransactionError` is post-commit cleanup, i.e. the write LANDED; the "rollback it could not complete" text in code and `docs/migration-ledger.md` describes an unreachable path.
- `runner.py:127` the backup kept after an uncertain-state failure is pruned by the next successful run of the same file.
- `coverage.py:176` over-deletion loop no longer fires on a rename onto a path the new schema keeps; caught by `check_ledger`, but no test pins it.
- `coverage.py:196` `_over_deleted_landings` mirrors `PathState.trace_to_origin` — a `landing_of_origin` helper would collapse it.
- Minor confirmed items from the reviewer: `reserved.py:85` remap reservation keyed by op-time spelling (remap-then-rename escapes RESERVED_VALUE_REUSED); AoT treated as terminal in the split walk; `str(chunk_key)` rendering of quoted keys in a detail; small duplications in `describe_narrowing` / proxy branch.

## Log

- (start) tracker written; nothing edited yet.
- item 1 done; fixes + migration unit suites green (390 passed).
- items 2 and 3 done; migration unit suite green.
- item 4 done (deferrals written). Next: make agent-check, then make agent-test.
- item 5 done: `make agent-check` green, `make agent-test` all passed. Round 3 fix-now set COMPLETE; everything staged, not committed.
