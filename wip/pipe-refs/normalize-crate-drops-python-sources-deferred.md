# Deferred: `normalize_crate` drops `python_sources`

**Status.** Noticed 2026-08-11 during Phase 1 of [implementation-plan.md](implementation-plan.md), while auditing the crate copy path for dropped fields (the plan asks for that audit precisely so a new pass does not reproduce the bug). Pre-existing, unrelated to the pipe-refs change, and deliberately **not** fixed on `fix/Pipe-refs` — the fix is a one-line addition whose *consequences* need a decision this branch is not the place to take.

## What happens

`normalize_crate` builds its result with an explicit `LibraryCrate(...)` constructor listing the fields it carries over. `python_sources` is not among them, so a crate that arrived carrying customer Python source returns without it. Every other envelope field (`domains`, `source_map`) is carried explicitly; `python_sources` is the one omission, which reads like an oversight rather than a decision — there is no comment claiming the drop is intended.

It is reachable, not theoretical: all three `normalize_crate` call sites take their crate from `LibraryManager.get_crate`, which populates `python_sources` from `_library_sources`. Whenever a library was loaded in sandbox-hosted mode, the input crate has the field and the output does not.

## Why the obvious fix is not a drive-by

Adding `python_sources=crate.python_sources` changes what three surfaces emit:

- `pipelex resolve` prints the encoded crate to stdout. Today the customer's `.py` source is not in that output; after the fix it would be.
- The `/resolve` API route returns the normalized crate in its response body.
- `emit_types` reads it (harmless — it only projects concepts), but the stamped `codegen.lock` records `crate_fingerprint`, which is unaffected either way: `python_sources` is deliberately excluded from both digest schemes.

So the fix moves customer Python source into a CLI stdout stream and an HTTP response body. That may well be correct — the field exists precisely so source can travel with the method — but it is a disclosure-surface decision, not a typo correction, and it belongs with whoever owns the sandbox-hosted transport contract.

## Why Phase 1 could leave it alone safely

The extracted qualification pass does **not** reproduce the bug, and for a stronger reason than the one first written here: `qualify_crate` returns a `QualifiedCrateContent` — just the rewritten `concepts` and `pipes` — never a `LibraryCrate`. There is no envelope for it to rebuild, so there is no field for it to drop. The class of bug is unrepresentable in the pass rather than merely avoided by it, which is why this note is a deferral and not a blocker.

*(An earlier draft of this paragraph credited `crate.model_copy(update=…)` for preserving the envelope. That described the pass's first cut, which returned a crate; review pushed back on that return type and it changed. The claim is recorded here as corrected rather than silently swapped, because "why the pass is safe" is exactly the sentence a future reader will lean on.)*

## What a fix would need

1. Rule on whether the normalized crate is allowed to carry customer source, per surface (CLI stdout, `/resolve` response, in-process consumers). The answer may differ by surface, in which case the field is dropped at the *presentation* boundary rather than in `normalize_crate`.
2. Whichever way it goes, state it in `normalize_crate`'s docstring, so the next reader finds a decision instead of an omission.
