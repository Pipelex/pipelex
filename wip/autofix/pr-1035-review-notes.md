# PR #1035 — deferred review note

Triage of the SWE-agent review comments on PR #1035 (`feature/Autofix-step4-Agnt-Apply`) fixed two confirmed bugs (logical-source mangling in `validate_bundle`; missing `~` expansion in the shared bundle-path resolver) and dismissed three false positives. One finding is real-but-inert and is captured here rather than fixed, per the "defer design-tradeoff findings" convention.

## Intra-round cross-file collision in `fix_loop._split_cross_file_collisions`

**Reporter:** cubic-dev-ai (P2, confidence 7) — thread on `pipelex/pipeline/fixes/fix_loop.py`.

**The observation (correct):** `_split_cross_file_collisions` decides whether a queued fix would collide with a bare pipe code by comparing only against the *already-loaded* `codes_by_file`. It does not account for bare codes that *other queued fixes in the same round* are about to write. So, read in isolation, two fixes that rename a pipe in two different files to the same new bare code in the same iteration would both be kept — writing a duplicate bare code across files.

**Why it is inert today:** the scenario cannot currently arise.

- The only fix rule that writes a bare pipe code is `strip-namespace` (`pipelex/pipeline/fixes/planner.py`), which fires on `INVALID_PIPE_CODE_SYNTAX`.
- `INVALID_PIPE_CODE_SYNTAX` is a per-file blueprint-parse error. `_load_mthds_files_into_library` (`pipelex/libraries/library_manager.py:777`) raises on the **first** file that fails to parse, and the entry file is parsed only after libraries load cleanly. So a single `validate_bundle` pass surfaces `strip-namespace` fixes for **exactly one file**.
- The cross-*iteration* case (file X stripped to `process` in round 1, entry file's `beta.process` surfacing in round 2) is already caught: `codes_by_file` is rebuilt fresh every iteration, so X's now-bare `process` is visible and the entry fix is dropped — the loop bails with the "cross-file collision" reason.

The safety is real but **emergent and non-local**: it depends on the per-file short-circuit in blueprint loading, which is not documented at the collision gate.

**When it becomes a live bug:**

1. `_load_mthds_files_into_library` is changed to **accumulate** blueprint-parse errors across all files (a plausible "show me all my errors at once" UX improvement) — two files' `strip-namespace` fixes could then co-occur in one pass; or
2. a **new** fix rule is added that writes a bare pipe code from a **merge-stage** error (merge processes all blueprints together), rather than from a per-file parse error.

**Remediation options (pick when/if the above changes land):**

- *Low-churn, do-now-if-desired:* add an invariant comment at `_split_cross_file_collisions` noting it is safe against intra-round duplicates only because bare-code-writing fixes come from per-file parse errors that short-circuit (one file per pass), and that a change to that short-circuit must revisit this gate.
- *Full fix (~10 lines):* thread a running `claimed_this_round: set[str]` through `_split_cross_file_collisions`. Check each fix against `other_codes ∪ claimed_this_round`; after keeping a fix, add its written bare codes (rename `new_key`s / `main_pipe` values, excluding the same target) to `claimed_this_round`. Order-independent, closes the window regardless of how many files surface per pass.
- *Test (pure function):* feed two fixes targeting different paths, both with a `RENAME_TABLE_KEY` `new_key="process"`, and a `codes_by_file` where neither path yet declares `process`. Current code keeps both; the hardened version keeps the first and drops the second.

**Status:** deferred, thread left open on the PR for follow-up.
