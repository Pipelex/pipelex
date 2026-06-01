# Archive — the abandoned `fix/dry-run` implementation

These two docs describe the dry-run consolidation **as it was actually built on the standalone `fix/dry-run` branch** (commit `7a01854f`). That branch forked from `main` at v0.29.1 and was **never merged**.

Meanwhile the live branch — `feature/Validate-with-signatures-4-fix-dry-run` — moved ~55 commits past that fork point on its own, landing (among other things) the **signature-validation** feature, which re-wired the very dry-run code paths this refactor wanted to delete. So the implementation recorded here no longer matches reality:

- The four files it "deletes" (`dry_run.py`, `dry_run_pipeline.py`, `dry_run_with_graph.py`, `dry_pipe_router.py`) all still exist in the live tree.
- `allowed_to_fail_pipes` is still in config.
- `convert_to_working_memory_format` is still in `dry_run.py` (it claims the helper moved to `WorkingMemoryFactory`).
- `keep_library_loaded` / `_resolve_pipe_run` do not exist in the live `runner.py`.

| File | Was | What it is |
|---|---|---|
| [`fix-dry-run-implementation.md`](./fix-dry-run-implementation.md) | `F-implementation.md` | File-by-file map of the abandoned diff. Useful as a *starting menu* for the re-attempt, not a record of current state. |
| [`fix-dry-run-validation.md`](./fix-dry-run-validation.md) | `G-validation.md` | The lint/type/test results for that abandoned diff. |

**Why keep them?** The new plan ([`../D-plan.md`](../D-plan.md)) re-attempts the same consolidation, now on top of signature-validation. The mechanical moves recorded here (which callsites migrate, the `keep_library_loaded` ownership problem, the behavioral-change list) are still a good shopping list — they just have to be re-grounded on the current, signature-aware code.
