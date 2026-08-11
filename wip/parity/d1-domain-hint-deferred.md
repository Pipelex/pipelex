# D-1 follow-up — the `domain_hint` conversation, deferred

**Status: CLOSED — subsumed, not implemented.** The `domain_hint` parameter will never be built, because the question it was going to answer stopped existing.

`domain_hint` was a way to make a *search* prefer the caller's domain when a bare code matched several. In-body pipe refs are now qualified to their owner domain at library build time and `PipeLibrary.get_optional_pipe` no longer searches at all, so a bare in-body code never reaches a lookup that could be ambiguous. The `TODO` quoted below is gone with the fall-through it described.

Note which row of the table settled it: the "both `A.foo` and `B.foo` exist" case now resolves to `A.foo` — the answer the `own-domain-first` column proposed and this note argued against. The argument was sound at the time and its conclusion has been overtaken: own-domain-first was wrong *while* the live library still searched, because it would have made the normalizer disagree with the runtime. Moving both readers together is what made it right. Ambiguity survives only in the entry affordance (`get_optional_entry_pipe`), where a human typed the code and guessing on their behalf would be the wrong favour — there it raises and names the candidates.

Everything below is the original note, preserved.

---

**Status (original):** deferred, deliberately. Raised at 1.1 (Phase 1), not taken.

## What 1.1 actually landed, and how it differs from the plan's recommendation

The plan's D-1 recommendation (a) reads: *"Qualify against the crate, the way the library resolves: **own domain first**, then a crate-wide unique match, raising `CrateNormalizationError` on ambiguity or absence."*

What landed drops the "own domain first" rung: `_qualify_pipe_ref` resolves a bare pipe ref by a **crate-wide** search only — unique match wins, ambiguity raises, absence raises.

The two differ in exactly one case, and in that case "own domain first" would have *created* a new disagreement rather than closing one:

| bare ref `foo` from domain `A` | live `PipeLibrary.get_optional_pipe` | own-domain-first | crate-wide (landed) |
| --- | --- | --- | --- |
| only `A.foo` exists | `A.foo` | `A.foo` | `A.foo` |
| only `B.foo` exists | `B.foo` | `B.foo` | `B.foo` |
| both `A.foo` and `B.foo` exist | **raises** `PipeLibraryError` (ambiguous) | `A.foo` ✗ | **raises** `CrateNormalizationError` |
| neither exists | `None` → `PipeNotFoundError` at run | raises | raises |

`get_optional_pipe`'s bare-code fallback (`pipelex/libraries/pipe/pipe_library.py`) searches every non-cross-package entry and raises on more than one match — it does **not** prefer the caller's domain. Its own `TODO` says so in as many words: *"add domain_hint parameter so controllers can prefer their own domain when bare code is ambiguous."* The preference is a thing the runtime is asked to grow, not a thing it has.

So preferring the owner domain in the normalizer would mean a library whose bare ref is ambiguous normalizes happily into a crate that resolves, while an interpreted run of that same library dies on the ambiguity. That is the shape of defect this whole track exists to remove. The plan's own standing rule — *"each fix lands with the test that pins the agreement"* — settles it: mirror the reader that ships.

## The conversation that is deferred

Whether `PipeLibrary.get_optional_pipe` should grow a `domain_hint` and prefer the caller's domain on an ambiguous bare code. This is a **language/runtime decision** (it changes which pipe a runnable bundle calls), not a normalization one, and it belongs with the same person who owns D-1 option (b).

If the answer is yes, the normalizer follows in the same change: `_qualify_pipe_ref` already has `owner_domain` in hand — it is the caller that most obviously knows the hint — and adding the preference rung there is a two-line change plus the ambiguity test flipping from "raises" to "picks own domain". Until then, the two readers agree, which is the property worth holding.

## Why the strictness costs nothing today

An ambiguous or dangling bare pipe ref cannot survive in a library that loads. `Library.validate_library` (`pipelex/libraries/library.py:128`) gates on `isinstance(pipe, PipeController)` — so **every** controller kind, Sequence, Condition, Parallel and Batch alike, not just the two that motivated the check — and puts each of its `pipe_dependencies()` through `get_required_pipe`. An unresolvable one surfaces as a structured `LibraryLoadingError(UNRESOLVED_PIPE_DEPENDENCY)` naming both the referencing controller and the missing ref.

Note the ordering, because it is the opposite of what "validation gates the crate" would suggest: the crate is **built first** (`LibraryCrateFactory.make_from_blueprints`, `library_manager.py:528`) and validated after, inside `load_from_crate` (`:492`). What runs after validation is *normalization* — `get_crate` → `normalize_crate` — and that is the step this fix guards. So the guarantee is not "validation runs first"; it is that no library reaching a normalized crate through the loader has an unresolvable controller dependency, because `validate_library` has already rejected it with a better error.

Raising in the normalizer therefore changes no behavior for any bundle that loads — it only turns a hand-built or transported crate's silent dangling ref into a diagnostic, on the path where nothing else would catch it.
