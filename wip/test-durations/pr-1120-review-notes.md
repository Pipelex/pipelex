# PR #1120 — deferred review note

One observation from the review-agent triage on PR #1120 was recorded rather than acted on. Everything else the reviewers raised was fixed on the branch.

## `FULL_RUN_RATIO` and the argv budget

**Where:** `pipelex/cli/dev_cli/commands/duration_map.py`, the `FULL_RUN_RATIO = 0.4` constant.

**Reported by:** nobody — noticed while verifying the reviewers' findings.

**The observation.** `FULL_RUN_RATIO`'s comment gives two reasons for the threshold, and the second is that it "keeps the node-id argument vector to a sane size". That reason is holding, but with less margin than the comment implies. Measured on the current map: 10,633 entries whose node ids total about 1.55 MB of text, so the largest incremental run the threshold permits passes roughly 620 KB of arguments to `execve`. `ARG_MAX` on this machine is 1 MB, and the environment block and pointer array come out of the same budget. It works, with something like 30% headroom, and the headroom shrinks as the suite grows because the threshold is a *ratio* — a suite twice this size crosses the limit at the same 40%.

**Why it was deferred.** It is a latent limit, not a present bug: no run today gets near `execve`'s ceiling, and the failure it would eventually produce (`E2BIG`) is loud and unmistakable rather than silent. Fixing it speculatively means either batching the node-id runs or writing them to a file for `@argfile`-style consumption, and both add moving parts to a command whose whole appeal is that it is simple. The right trigger is the suite roughly doubling, or the first `Argument list too long` from `make store-test-durations`.

**If it does need addressing.** The cheapest fix is to bound the incremental run by the *byte size* of the assembled node-id list rather than only by the missing-to-collected ratio, falling back to the full re-measure when the vector would get large. That keeps the existing escape hatch and adds no new execution mode.

Thread: https://github.com/Pipelex/pipelex/pull/1120
