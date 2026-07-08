# Deferred: scalar-envelope arm asymmetry (bool preserves subclass, str flattens to Text)

**Status:** deferred design note — no code change. Surfaced during the Phase 2 (YesNo envelope inputs) code review, 2026-07-07.

## What

`StuffFactory.make_stuff_from_stuff_content_or_data` handles the envelope form `{"concept": ..., "content": <scalar>}` with two adjacent scalar arms that treat a *refining* concept differently:

- **Case 2.1d (bool → YesNo)** routes through `StuffContentFactory.make_stuff_content_from_concept_required`, which resolves the concept's `structure_class_name`. For a concept refining `YesNo` (e.g. a generated `urgency__IsUrgent` subclass of `YesNoContent`), this **preserves the refining subclass** — the produced content is an instance of that subclass, not the base `YesNoContent`.
- **Case 2.1 (str → Text)** constructs a base `TextContent` directly, **flattening to base** regardless of the concept's own `structure_class_name`.

So the same "scalar under a refining concept" pattern yields a subclass for bool and a base class for str.

## Why it is deliberate (not a bug)

The asymmetry is intentional and tested (see Checkpoint 2 note in `yesno-implementation-plan.md`):

- `YesNo` refinements **do** generate a registered `StuffContent` subclass, and `subclass.model_validate(True)` fails while `subclass(yes_no=value)` works — so routing bool via the concept resolver is the only construction path that honors the refinement.
- `Text`'s historical behavior flattens string content to base `TextContent`; changing that is out of scope for the YesNo track and would be a behavior change to an unrelated, long-standing path.
- The no-coercion pin holds either way: a `"yes"`/`"no"` string under a YesNo concept still takes the str arm and errors as not-Text-compatible.

## Follow-up to consider (Smart Inputs generalization)

When Smart Inputs (D5/D10) generalizes these scalar-envelope arms into the shared `input_shaper.py`, revisit whether the str arm should also preserve a refining concept's `structure_class_name` instead of flattening to base `TextContent`. If the two scalar arms are unified under one interpretation matrix, this asymmetry should be resolved by design rather than left as two hand-written arms with divergent behavior.

No action needed inside the YesNo track.

## Phase-5 triage (Smart Inputs, 2026-07-08) — RE-DEFERRED, narrowed

The shaper landed, and it **half-closes** this: the **bare** path — now the blessed default (a plain `"my question"` under a `legal.Question` input) — builds the refining subclass, because `InputShaper._build_item_content`'s TEXT arm wraps the value into the structure class's canonical dict and routes through `StuffContentFactory.make_stuff_content_from_concept_required`, which honors `Question`. So the everyday case is correct.

The asymmetry now survives **only on the envelope escape hatch**: `{"concept": "legal.Question", "content": "text"}` still routes through `InputShaper._shape_explicit` → `StuffFactory.make_stuff_from_stuff_content_or_data` Case 2.1, which builds a base `TextContent` (concept kept, content not the subclass). Re-deferred rather than fixed because:

- **Blast radius.** Closing it means changing `StuffFactory` Case 2.1's str→Text arm (a long-standing bottom-up path used well outside the shaper) or bolting a shaper-local post-build rewrite onto `_shape_explicit` — neither is the clean "unify under one matrix" the note imagined; both are surgery on the escape hatch for a case the blessed path already gets right.
- **Near-zero practical impact.** A pure Text *refinement* adds no fields over `TextContent` (both carry `text`), so a base `TextContent` with concept `legal.Question` renders and validates identically to `Question(text=...)` for the common refinement; the subclass identity only matters to downstream code doing `isinstance`/subclass-field access on a Text refinement, which is rare.

Real fix, when the bottom-up scalar-envelope arms are next revisited: make `StuffFactory` Case 2.1 resolve the concept's `structure_class_name` like the bool (2.1d) arm does, so both scalar-envelope arms preserve the refining subclass. Not worth pulling into the Smart Inputs finalize.
