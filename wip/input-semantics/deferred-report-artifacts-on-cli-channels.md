# Deferred: report-only artifacts are absent from the CLI validate channels

Surfaced by the PR #1150 review triage (three bots independently flagged the same two claims on `docs/tools/cli/agent-cli.md`). The documentation was corrected in that PR — the claims now name the protocol validation report, which is the artifact that actually carries them. What follows is the runtime work those corrections make visible. Neither item is a defect; each needs a decision rather than a patch.

## 1. Hint lints reach only the protocol report

Already tracked at [`wip/engine-hints/deferred.md`](../engine-hints/deferred.md), first bullet — read that entry first; this is an addendum, not a duplicate.

What the review established beyond it: the wiring really is mechanically available at every site. `build_current_library_hint_warnings()` needs only a current library with a crate, and all three agent-CLI sites sit inside an open, current validation window — `acquire_library` leaves the library current, and `validate_bundle` deliberately leaves its validation library open and current on success. So the appends themselves are one-liners.

The prerequisite recorded in the engine-hints note still stands and should gate the work: authored hint content is interpolated raw and unbounded into `ValidationErrorItem.message`, one item per unknown key, so a hostile or merely sloppy bundle can inflate the warning payload. Cap the per-site findings and elide long tokens **before** the lint reaches a channel an author invokes casually. The same note's design preference also stands — build one shared "all advisory warnings" composition point rather than an eighth copy of the `build_optionality_warnings(...)` pattern.

Blast radius, for whoever picks this up: the bare human CLI (`pipelex/cli/commands/validate/_validate_core.py`), the agent CLI (`pipelex/cli/agent_cli/commands/validate/_validate_core.py`, three sites) and the builder ops (`pipelex/builder/operations/validate_ops.py`, three sites) are all equally hint-blind.

## 2. `pipe_io_contracts` / `input_form` on the agent CLI envelope — needs a design decision

**Do not wire this without deciding the shape first.** The mechanics are trivial and that is exactly the trap.

`build_pipe_io_contracts` and `build_input_form` both take a `Sequence[PipeAbstract]`, and every agent-CLI validate site already has the pipes in hand inside its open window. Appending both to the success envelope would take minutes.

The reason not to: it would put a full JSON Schema per input, per pipe, into **every** `validate` success envelope on a CLI whose whole point is cheap machine-readable output. The protocol report puts these behind an explicit opt-in for precisely that reason — `PipelexValidationReport.input_form`'s own docstring says the HTTP route decides whether the field travels on the wire, absent unless a caller opts in via `views`, and [`docs/under-the-hood/input-form-descriptor.md`](../../docs/under-the-hood/input-form-descriptor.md) repeats it.

So the open question is not "should the CLI expose the contracts" but "what is the CLI's equivalent of `views`". Candidates: a `--views` / `--include` flag mirroring the protocol parameter, or a separate `pipelex-agent contracts` command that returns them without pretending they are part of a validation verdict. Deciding that is what unblocks the work.

Until then, `docs/under-the-hood/pipe-io-contracts.md` states the boundary explicitly in its "Which surfaces carry it" section, so a reader is told which surface to reach for rather than discovering the absence.
