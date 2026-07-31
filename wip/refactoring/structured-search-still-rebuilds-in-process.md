# The in-process structured-search path still rebuilds the output class from its schema

Deferred out of PR #1076 (`refactor/Exec`). That PR fixed the same bug on the LLM object paths; this is the one instance it deliberately left.

## What it is

`ContentGenerator.make_search_structured` (`pipelex/cogt/content_generation/content_generator.py`) holds the caller's `output_structure_class` and never threads it down. `search_generate.search_gen_structured` and `dry_mock.dry_search_gen_structured` both still call `SchemaToModelFactory.make_from_json_schema` unconditionally.

So a `PipeSearch` with a structured (non-text) output still hands the provider a class rebuilt from JSON schema, which loses exactly what #1076 established the rebuild loses:

- custom `@field_validator` / `@model_validator` logic
- `json_schema_extra` format/pattern hints
- the output structure's own description (its class docstring)

It is the same defect, in the same shape, roughly four lines from being fixed.

## Why it was not done in #1076

Not because it is hard — because of what it drags with it. Threading the class down changes a *second* error-class surface the same way the object path's changed: the dry mock would then be built from the real class, so `test_dry_search_structured_fidelity_gap_raises_typed_error` stops producing `DryRunObjectFidelityError` and starts producing `DryRunMockBuildError`. That needs its own test re-scoping and its own review pass. #1076 was already at bot-clean state when this surfaced, and quietly widening it there would have landed an unreviewed behavior change on a second surface.

## What doing it looks like

Mirror the object path exactly — that is the point:

1. `search_gen_structured(search_object_assignment, *, output_class: type[BaseModel] | None = None)`, same keyword-only shape, `None` = boundary.
2. Same for `dry_search_gen_structured`.
3. Resolve through `object_class_resolution.resolve_object_class`'s sibling (it currently takes an `ObjectAssignment`; `SearchObjectAssignment` carries the same two fields under different names, so either generalize the helper over the two field names or add a thin second entry point — do **not** duplicate the `SchemaToModelFactory` call).
4. `make_search_structured` passes `output_class=output_structure_class`.
5. Re-scope `test_dry_search_structured_fidelity_gap_raises_typed_error` to the boundary composition, exactly as `test_dry_run_object_fidelity.py` was.

`SearchObjectAssignment`'s wire shape must not change, for the same reason `ObjectAssignment`'s did not.

## Related

- `wip/refactoring/boundary-revalidation-round-trip-is-unaudited.md` — the other deferral out of the same PR.
