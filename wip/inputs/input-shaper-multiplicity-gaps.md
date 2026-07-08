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

## Phase-5 triage (Smart Inputs, 2026-07-08) — Gap A unambiguous half CLOSED; auto-wrap + Gap B RE-DEFERRED

The Phase-5 finalize doc-accuracy review independently re-found **Gap A** and framed it as a silent behavior: a caller handing an explicit `ListContent` (or an envelope whose `content` is a list) to a singular-declared input had it *silently stored* into the singular slot, contradicting D2's unconditional list-where-singular error. That is exactly the reopen trigger this note recorded, so the **unambiguous half of Gap A is now fixed**:

- `InputShaper._shape_explicit` now calls `_reconcile_explicit_multiplicity` after the D6 compat check: an explicit form whose built content is a `ListContent` raises `ListWhereSingularError` against a singular slot, and `MultiplicityCountMismatchError` against a declared `[N]` of the wrong length — reusing the existing error factories, so the rendered-shape hints stay consistent. The multiplicity peel is shared with the bare-value path via a new `_peel_multiplicity` helper (no duplicated classification). Pinned by `test_explicit_forms.py` (`test_explicit_list_into_singular_raises`, `test_explicit_list_wrong_fixed_count_raises`, `test_explicit_list_into_list_slot_ok`).

**Still deferred (the genuine tradeoffs, not the bug):**

- **Gap A's auto-wrap sub-question.** An *explicit singular* under a declared `[]`/`[N]` is still taken literally (stored as given), not auto-wrapped into a one-item list the way the bare-value path does. Whether an explicit form should auto-wrap or be literal is the open design question the note flags — left to the holistic D2-multiplicity pass. `_reconcile_explicit_multiplicity` only fires on `ListContent` content, so this direction is untouched.
- **Gap B — the `DYNAMIC` arm skips multiplicity peeling.** `_shape_one`'s `InputKind.DYNAMIC` case still short-circuits to the bottom-up factory before `_shape_with_multiplicity`, so a declared `Dynamic[]`/`Anything[N]` doesn't peel multiplicity (empty-list diverges from D2's empty `ListContent`, no `[N]` check, no auto-wrap). D5 explicitly says Dynamic/Anything "fall back to today's bottom-up rules," and declaring Dynamic *with* a multiplicity is unusual; the empty-list case raises a clean error, not silent corruption. Re-deferred as a documented decision to the holistic D2-multiplicity pass (which must also settle the auto-wrap question above).

## PR #1033 follow-up (2026-07-08) — Dynamic explicit-list regression CLOSED; broader Gap B still deferred

The Phase-5 reconcile introduced a narrower regression: a singular `native.Dynamic` input still accepted a raw Python list through the bottom-up `InputKind.DYNAMIC` path, but rejected an already-built `ListContent` because `_shape_explicit` ran the new list-into-singular guard after the D6 compat check. That over-applied D2 to a slot where D5 says the signature cannot guide shape.

`InputShaper._shape_explicit` now returns immediately after compatibility when the declared concept is exactly `native.Dynamic`, matching the bare-value Dynamic fallback. Pinned by `test_explicit_list_content_into_dynamic_slot_ok`.

This does **not** resolve the broader Gap B above: declared `Dynamic[]`/`Anything[N]` still do not peel multiplicity, and the empty-list/count/auto-wrap semantics remain deferred to the holistic D2 pass.
