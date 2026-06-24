# Suspects — package `core`

Reviewed: 95 Section A + 66 primitive lone-subjects. Suspects: 3.

## High confidence

- `pipelex/core/stuffs/stuff_content.py:64` — `StuffContent.rendered_markdown` — `def rendered_markdown(self, level: int=1, *, is_pretty: bool=False) -> str` — `level` and `is_pretty` are both optional rendering options; neither is "the subject" (self is). All call sites already use `rendered_markdown(level=..., is_pretty=...)` keyword form or the no-arg default. `rendered_markdown(2)` is opaque. Suggested fix: move `*` before `level` so both params are keyword-only.

- `pipelex/core/stuffs/stuff_content.py:113` — `StuffContent.rendered_markdown_async` — `async def rendered_markdown_async(self, level: int=1, *, is_pretty: bool=False) -> str` — same issue as `rendered_markdown`; parallel async signature, all call sites use keyword form. Suggested fix: move `*` before `level`.

## Medium / low confidence

- `pipelex/core/concepts/concept.py:194` — `Concept.render_concept_representation` — `def render_concept_representation(self, output_format: ConceptRepresentationFormat, *, is_multiple: bool=False) -> tuple[dict[str, Any], set[str]]` — `self` (Concept) is the real subject; `output_format` and `is_multiple` are both rendering options of equal standing. All call sites use `render_concept_representation(output_format=..., is_multiple=...)` keyword form. Positional `output_format` adds no clarity. Suggested fix: move `*` before `output_format` (make fully keyword-only).
