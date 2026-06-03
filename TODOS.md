# WIP-Docs Tidy — Recap

A cleanup of the `_docs/wip/` documentation tree (branch `docs/Tidy`), aimed at making `wip/` hold only real work-in-progress and making the surviving docs read as current reality. What it did, in kind:

- **Reorganized the tree.** Grouped loose top-level docs into topic folders, separated finished material from active work, and deleted derived `.html` renders and dead duplicates.

- **Moved finished material out of the public repo.** Completed plans and design history went to the private workspace `docs/history/`; internal forward-looking plans (e.g. the Temporal enterprise-readiness roadmap) went to private `docs/plans/`. `wip/` now contains only things started or about to start — active plans, designs, and current-state trackers with open gaps.

- **Made the public docs self-contained and current.** Removed every pointer from the public repo into the private one, and scrubbed the history/PR noise that misled agents about present state — PR numbers, commit hashes, branch and ledger names, dated checkpoint narrative, "archived plans" lists. Docs now describe what the code does today, not how it got there.

- **Corrected stale claims** in the surviving current-state docs, each verified against the code in this worktree, and trimmed one landed-but-written-as-a-proposal doc down to an as-built reference.

- **Split out the remaining work.** The runtime code-fix follow-ups the tidy surfaced live in [`wip/runtime-code-fixes.md`](wip/runtime-code-fixes.md); everything else open is tracked per-feature inside the relevant `wip/` track or standalone doc (see [`wip/README.md`](wip/README.md)).

Result: `wip/` is active-only and link-clean; finished history and internal plans live in the private workspace; the public docs carry no cross-repo references.
