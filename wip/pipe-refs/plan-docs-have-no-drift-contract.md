# Plan and `wip/` docs go stale the way `docs/` used to, and nothing catches it

**Status: an observation with a concrete proposal, deliberately not acted on in this branch.** Recorded because the evidence for it was collected by accident and would be expensive to reconstruct.

## The evidence

Across three PR-review rounds on the pipe-refs branch, review found four documentation claims that were **true when written and went false when something downstream changed**. None was careless writing; each described a real thing accurately at the time.

| Claim | What made it false |
|---|---|
| "`qualify_crate` copies the envelope with `crate.model_copy(update=…)`" | The pass's return type changed from `LibraryCrate` to `QualifiedCrateContent` after a review push-back. The sentence described the first cut. **It was stale in three places; the bot found one.** |
| "No fix op writes a pipe ref" | Never true, but written from a partial read of the fix planner — `strip-namespace` plans a root `main_pipe` `SET_KEY`. |
| `crate_normalization.py:290` / `:135`, `sub_pipe.py:161`, `pipe_library.py:81` | Line-number pointers into code **this same branch was editing**. Two of them went stale between Phase 1 and Phase 2 — inside one branch, in one sitting. |
| "Deliberately left for Phase 2: …" | Survived Phase 2's completion, so the plan simultaneously declared a phase complete and assigned it unfinished work. |

Plus one structural version of the same failure: the Status block declared checkpoint C2 passed while C2's own checklist sat entirely unticked. Every item was in fact done — the two statements were written at different moments and never reconciled.

## Why this is a systems observation and not a scolding

`docs/` has a mechanism for exactly this: **drift contracts** (`drift.toml`, `docs/contribute/drift-contracts.md`). A contract binds a set of trigger files to a set of review targets; when the triggers change, the contract opens and the change cannot land until someone reviews the targets and records an honest rationale. It works — on this very branch it opened twice, and the `hub-layering` one caught a symbol table that really had gone stale.

**`TODOS.md` and `wip/` are not under any contract.** They are precisely the documents that describe code in motion, written while the code is still moving, and they are the only prose in the repo with no staleness gate at all. The failure rate above is what that predicts.

## The proposal

A `plan-docs` drift contract, roughly:

- **triggers:** the source files a plan names as its subject — for the pipe-refs work, `pipelex/libraries/crate_qualification.py`, `crate_normalization.py`, `pipe/pipe_library.py`, `library.py`.
- **targets:** `TODOS.md` and the feature's `wip/<feature>/` directory.

The rationale requirement is the useful part, not the mechanism: it forces someone to re-read the plan against the code it claims to describe, at the moment the code moves.

## Why it is NOT being done here

Three honest reasons, in order of weight:

1. **It is out of scope.** This branch changes reference resolution. Adding repo-wide review machinery to it would be exactly the over-engineering the maintainer asked to avoid, and it would arrive bundled with a breaking language change where it cannot be evaluated on its own merits.
2. **The trigger set is per-feature, and that is a design question.** A generic "any `pipelex/` change opens the plan contract" would fire on every commit and be acked reflexively, which is worse than nothing — a gate that is always open teaches people to close it without looking. Getting it right means deciding how a plan declares its own subject, and that deserves its own thinking.
3. **Two cheaper habits capture most of the value**, and both are already recorded in `TODOS.md`'s Phase 3 section:
   - **Do not write line numbers into prose about code you are editing.** Name the symbol. A line number is a fact with a half-life measured in commits; a function name survives a refactor and is what the reader greps for anyway.
   - **Tick a checklist in the same edit that updates the summary claiming it is done.** The two statements are only worth something when they cannot disagree, and they can only disagree if they are written at different times.

## If someone picks this up

Start with the second habit rather than the machinery — a `plan-docs` contract that fires on a plan whose checkboxes and Status block already agree is catching a much rarer bug.

### Already measured

Across `wip/**/*.md` plus `TODOS.md`, counting only pointers whose file exists in this repo:

- **123** in-repo `path.py:NNN` pointers.
- **4** point past the end of the file they name, so they are *provably* stale:
  - `wip/refactoring/modularity-refactors.md` → `pipelex/pipelex.py:500` (file has 352 lines)
  - `wip/inputs/yesno-implementation-plan.md` and `wip/inputs/datetime-implementation-plan.md` → `pipelex/core/registry_models.py:92` (57 lines)
  - `wip/inputs/smart-inputs-implementation-plan.md` → `pipelex/cli/commands/run/_inputs_path_resolver.py:75` (69 lines)

**4 is a floor, not the count.** Out-of-range is the only staleness a script can prove cheaply; a pointer that has drifted to the wrong line *within* the file looks perfectly healthy to this check and is the more common case — the pipe-refs pointers that a reviewer caught were all in range and all wrong. Read the number as "at least 4 of 123, and the real figure needs a human or a symbol-resolving check".

These four belong to other features and are left alone here; the point of measuring was to establish whether the pattern is local to one plan (it is not) before proposing repo-wide machinery for it.

A cheaper variant worth considering before the full contract: have the check resolve the *symbol* named next to the pointer rather than the line, which turns "is this line still there" into "is this still where that function lives" — the question the reader actually has.
