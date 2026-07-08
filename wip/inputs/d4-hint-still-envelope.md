# D4 shaping-error hint still renders the envelope shape (not the light shape)

Status: **deferred tradeoff, surfaced during Smart Inputs Phase 4 (2026-07-07).** Not a bug; a consistency question for Phase 5 triage.

## What

Phase 4 flipped the generated inputs template (`build inputs` / `pipelex-agent inputs`) to the **light** signature-driven shape by default (bare values), with the `{concept, content}` envelope behind `--explicit`.

But the D4 shaping-error hint — the "Expected shape:" line every `InputShapingError` renders via `InputShaper._render_expected_shape` → `stuff_spec.render_stuff_spec(ConceptRepresentationFormat.JSON)` — still emits the **envelope** form. So a caller who provides a bare (light) value that fails to shape sees an *envelope*-shaped hint, while the template they generated was light. Mild inconsistency: "you gave me a bare string but here's a `{concept, content}` object" reads slightly off now that bare is the blessed default.

## Why it wasn't fixed in Phase 4

Making the hint light would mean the **shaper** producing the light form. The light transform lives in `input_renderer` (`pipelex/core/pipes/inputs/`), which imports `InputShaper` (`pipelex/core/memory/`). Having the shaper call back into `input_renderer` to render a light hint would be a layer inversion / import cycle (input_renderer → input_shaper today; the reverse would close the loop). The delighten transform would have to move to a neutral home the shaper can import, or be duplicated — both bigger than the Phase-4 surface warranted, and none of the Phase 1–3 e2e error tests pin the exact hint shape (they assert only `"Expected shape:" in message`), so nothing forces the change.

## Options for Phase 5 triage

1. **Leave it.** The envelope hint is unambiguous and always valid input; arguably it's the *most* explicit thing to show someone who just failed to provide a value. Cheapest.
2. **Make the hint light.** Move the delighten transform (`_delighten_entry` + `_unwrap_scalar_content`) to a home both `input_shaper` and `input_renderer` import (e.g. alongside `resolve_input_kind`), then have `_render_expected_shape` render the light form. Consistent with the template, but a real refactor + a layer decision.
3. **Show both.** Hint renders the light form as the primary "provide this" and mentions the envelope escape hatch. More words, most helpful.

Recommendation: **option 1 (leave it) unless a Phase-5 doc pass or user feedback shows the envelope hint actively confuses.** The light template is the teaching surface; the error hint is a fallback and being explicit there is defensible.

## Phase-5 triage (Smart Inputs, 2026-07-08) — DECIDED: leave it (option 1)

Settled on **option 1**. The envelope form the hint shows is always valid input and unambiguous — the most explicit "here is a shape that will work" you can hand someone who just failed to provide a value; it is a fallback surface, not the teaching surface (the light template is). Option 2 (make the hint light) still carries the layer/cycle cost described above — the delighten transform lives in `input_renderer`, which imports `input_shaper`, so having the shaper render a light hint means moving that transform to a shared home or duplicating it, a real refactor unjustified by a fallback string. Nothing in the shipped docs pass leans on the hint being light, and no evidence it confuses. Reopen only if user feedback shows the envelope hint actively misleads now that bare is the blessed default.
