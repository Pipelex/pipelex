# D-1 follow-up — the `domain_hint` conversation, deferred

**Status:** deferred, deliberately. Raised at 1.1 (Phase 1), not taken.

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

An ambiguous bare pipe ref cannot exist in a library that loads: `PipeCondition` and `PipeSequence` resolve every dependency at validation time, so `get_optional_pipe` raises before the crate is ever built. Raising in the normalizer therefore changes no behavior for any bundle that works — it only turns a hand-built crate's silent dangling ref into a diagnostic.
