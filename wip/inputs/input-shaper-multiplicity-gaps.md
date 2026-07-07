# Deferred: `InputShaper` multiplicity gaps in the explicit and Dynamic arms

**Status:** deferred design note — no code change. Surfaced during the PR #1028 adversarial review (cubic), 2026-07-07. The `InputShaper` is **Phase-1 dormant** — landed with its full unit-test suite but not yet wired into any run (commit `d72101174`, "not yet wired"); wiring is the D7/Phase-2 job of the upcoming `smart-inputs-implementation-plan`. Both gaps below are therefore latent (no runtime impact today) and belong to that phase, which reworks exactly this multiplicity handling.

## Gap A — `_shape_explicit` bypasses declared multiplicity (D2)

`InputShaper._shape_explicit` (`pipelex/core/memory/input_shaper.py`) builds the explicit form bottom-up and does exactly one check — concept compatibility (`get_concept_library().is_compatible(...)`). It never consults `stuff_spec.multiplicity`. Because `_is_explicit` treats any `StuffContent` — and `ListContent` **is** a `StuffContent` — as explicit, three shape mismatches slip through unchecked, contradicting the D2 invariants the *non-explicit* path enforces in `_shape_with_multiplicity`:

- **singular declared + explicit `ListContent`** (or an envelope whose `content` is a list) → a list is stored into a singular slot, though D2 makes "list where singular is declared" a hard error;
- **`[N]` declared + explicit `ListContent` of the wrong length** → the count is never validated;
- **`[]` declared + explicit singular object** → stored as singular, where the non-explicit arm would auto-wrap.

D6 (`smart-inputs-design.md`) governs only *concept* compatibility ("explicit wins when compatible"); it says nothing about multiplicity, and D2 states the list-vs-singular hard error unconditionally. So this is a genuine gap, not a D6 carve-out. **No test asserts either behavior** — `test_explicit_forms.py`'s "multiple" cases pass a bare Python `list` (which is *not* explicit and takes the `_shape_list` path), so the explicit-arm × multiplicity interaction is untested.

**Proposed fix (from the review):** after the compat check in `_shape_explicit`, reconcile the built content's shape against `stuff_spec.multiplicity` using the same rules `_shape_with_multiplicity` applies — reject a `ListContent` against a singular spec (`ListWhereSingularError`), enforce the `[N]` count on a `ListContent` (`MultiplicityCountMismatchError`), reusing the existing error factories so the rendered-shape hint stays consistent.

**Open design question:** the single-vs-`[]` auto-wrap policy for explicit forms — should an explicit singular object under a declared-multiple `[]` input auto-wrap into a one-item `ListContent` (as the bare-value arm does), or is an explicit form taken literally? Decide this when wiring, not by bolting a rule onto the current arm.

## Gap B — the `DYNAMIC` arm skips multiplicity peeling

In `_shape_one`, the `InputKind.DYNAMIC` case returns `StuffFactory.make_stuff_from_stuff_content_or_data(value)` and short-circuits **before** `_shape_with_multiplicity`. `resolve_input_kind` maps `Dynamic`/`Anything`, the out-of-matrix natives, and unregistered structures to `DYNAMIC` keyed on the *concept* only; `stuff_spec.multiplicity` is never consulted for them. So for a declared `native.Dynamic[]` / `native.Anything[N]`:

- **empty list** → the bottom-up factory raises "Cannot create Stuff from empty list" instead of D2's legal empty `ListContent` — a concrete divergence from the Smart Inputs contract;
- **fixed `[N]`** → no count check;
- **single → list auto-wrap** → not applied.

This is **partly by design**: D5 says Dynamic/Anything "fall back to today's bottom-up rules (the signature genuinely doesn't know)," and the code comment frames handing the whole raw value (including its own list handling) to the factory as deliberate for *item building*. But D2 frames multiplicity as a *prior* peeling step orthogonal to concept nature ("after D2's multiplicity peeling, dispatch on the declared concept's nature"). Under that reading the DYNAMIC arm should still peel multiplicity (honor `[]`, `[N]`, auto-wrap) and defer only *per-item building* to bottom-up. Practical severity is low — declaring Dynamic/Anything *with* an explicit multiplicity is an unusual signature — but the empty-list case is an observable contradiction with D2.

**Proposed resolution:** either (1) move the multiplicity peel ahead of the kind dispatch so the DYNAMIC arm routes lists through `_shape_list` with per-item bottom-up building (empty→empty `ListContent`, `[N]` count-checked, single auto-wrapped), deferring only per-item concept inference to `StuffFactory`; or (2) if the full fallback is intended, add a one-line design note + a pinning test so "Dynamic ignores declared multiplicity" is a documented decision rather than an accident.

## Follow-up

Resolve both when the `smart-inputs-implementation-plan` wires `InputShaper` (D7) — that phase must decide the D2 multiplicity semantics holistically, and these two arms are exactly where it lands. Add pinning tests for whichever contract is chosen (today `Dynamic[]` + `[]` reproduces the bottom-up "Cannot create Stuff from empty list" error, demonstrating Gap B). Related notes: `scalar-envelope-arm-asymmetry.md`, `case1-bare-date-arm-gap.md`.

No action needed on the PR #1028 merge — the shaper is dormant.
