# `Date` / `Time` natives — live-run fix

Tracks the work behind [PR #1089](https://github.com/Pipelex/pipelex/pull/1089) (`fix/Native-date-time`): the temporal natives could not be produced by a live `PipeLLM`, because instructor validates structured output in strict mode and a `mode="before"` validator forfeits pydantic's strict-JSON acceptance of ISO strings.

**Status:** shipped in the PR, open against `dev`. All CI green, all review threads resolved.

| File | What it is |
| --- | --- |
| `what-we-built.html` | The write-up for co-developers — root cause, the fix, what the review uncovered, and what breaks for authors. Start here. |
| `bug-report.md` | The original report, filed from `mthds-ui` while adding native-concept fixture coverage. |
| `plan-and-review-log.md` | The working plan (was `TODOS.md` at the repo root) plus the decision record: every accept and decline across six bot rounds and the final independent review, with the reasoning. |
| `doc-sweep-deferred.md` | The cross-repo doc item deliberately left out of the PR, release-gated. (A second item from the same review concerns another repo and is tracked at workspace level.) |
| `compose-time-matrix-plan.md` | The follow-up branch `fix/Time-native` (also once the root `TODOS.md`): `Time` was the one native missing from `PipeCompose`'s whole-stuff conversion matrix. Phases 1–3 shipped in this worktree; Phase 4 is an open `mthds-plugins/` doc edit. |

## Still open

- `mthds-ui` (`feature/Native-concepts_stories`): `make fixtures-live ONLY=pipeline_32` replaces the placeholder LIVE fixture with real data — the end-to-end regression check. Gated on a released pipelex carrying the fix.
- Optional pre-release sanity check: run a gateway `PipeLLM` with `output = "Time"` / `Date[]` against the production path.
- The item in `doc-sweep-deferred.md`.
- Phase 4 of `compose-time-matrix-plan.md`: the `mthds-plugins/` reference template still lists the convertible natives without `Time`.
