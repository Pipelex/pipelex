# Refactoring working notes

This folder holds working notes for refactors that outlived a single PR. Two tracks currently share it — read the section that matches what you are picking up.

## Modularity refactors after the hub split

The three modularity refactors (**M3** split the boot manifest by layer, **M1** made core's layer split physical, **M2** separated the plugin mechanism from the vendor adapters) plus the **F1** img-gen follow-up. They build on the `pipelex.hub` → `runtime_hub` + `interpreter_hub` split recorded in [`../hub/`](../hub/README.md).

**Track parked, not archived** — all four pieces are complete, reviewed and on `dev`; what remains is the cross-repo sweep, which was release-gated and is **no longer blocked** now that v0.41.0 and v0.42.0 have shipped. The executable tracker was moved out of the repo-root `TODOS.md` slot into this folder on 2026-07-29 so that slot is free for whatever is actively being built.

| Document | What it is |
| --- | --- |
| [`modularity-refactors-tracker.md`](modularity-refactors-tracker.md) | **The executable tracker** (formerly the repo-root `TODOS.md`) — ordered work, checkboxes, checkpoint records, decisions, measurements, review findings, cold-start brief. Authoritative for *what to do*, and the only place the Phase 5 sweep's consumer table is written down. Start at its [Cold-start brief](modularity-refactors-tracker.md#cold-start-brief). ⚠ Its branch/PR header is a historical record — the work shipped under different numbers; the note at the top of the file says which. |
| [`modularity-refactors.md`](modularity-refactors.md) | The design doc — the *why*, the rulings, the measurement snippets. Superseded in part by the tracker after the 2026-07-27 engineering review; kept as the record of the original reasoning. |
| [`modularity-review-follow-ups.md`](modularity-review-follow-ups.md) | The review items recorded but not fixed, assessed and ready to implement — **FU-1** (an error-class rename is a silent wire break), **FU-2** (the img-gen neutrality guard is weaker than its comment), **FU-3** (the bookkeeping files a bulk rewrite breaks are ungated). Cite the ids. |
| [`deferred-placement-follow-ups.md`](deferred-placement-follow-ups.md) | Placement and naming accuracy findings from the M1 checkpoint review — no silent bug, no boundary breach, deliberately deferred because the churn is not justified by the defect. |

## Exec-track follow-ups (PR #1076 and `refactor/Follow-ups`)

Unrelated to the modularity track — these are the residue of the execution refactor, kept here because they are refactor notes with no home of their own.

| Document | What it is |
| --- | --- |
| [`leaf-conversion-and-search-follow-ups.md`](leaf-conversion-and-search-follow-ups.md) | What a full pre-landing `/review` of `refactor/Follow-ups` surfaced and did not fix. Every claim re-verified against the tree on 2026-07-31, with the command that produced each measurement inline. |
| [`boundary-revalidation-round-trip-audit.md`](boundary-revalidation-round-trip-audit.md) | The audit of `revalidate_leaf_object`'s boundary conversion — what it established, the one real loss it found and fixed, and the two things still not established. |
| [`func-registry-entries-outlive-their-library.md`](func-registry-entries-outlive-their-library.md) | PipeFunc registrations survive the teardown of the library that registered them. A genuine narrowing introduced by #1076, recorded rather than fixed because the only correct fix is a design change. |
