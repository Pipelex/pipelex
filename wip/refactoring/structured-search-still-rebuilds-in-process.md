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

## ⚠ "Mirror the object path exactly" is not quite enough — the dry arm has a double-validation trap

The search leaf is **dict-out by contract** (`search_gen_structured -> dict[str, Any]`; that is what keeps the dynamic class off the Temporal wire), and `make_search_structured`'s inline re-validation of that dict is the *single* validation on the live path. That difference from the object path matters when threading the class down:

- **Dry arm (confirmed in code):** `dry_search_gen_structured` builds the mock and *dumps it to a dict*; the submitter then re-validates the dict. Hand the real class to `build_mock_object` naively and the caller's validators run at mock build **and again** on the dumped data — a transforming validator produces `INV-INV-…` in dry mode, the exact defect class #1076 fixed on the object path with the `isinstance` short-circuit. That short-circuit cannot apply as-is to a dict. So the fix needs one extra decision: either the in-process dry arm returns the mock *instance* (the leaf's in-process return widens to instance-or-dict and the shared helper's model arm short-circuits), or the submitter skips re-validation when the class was in hand at the leaf.
- **Live arm (unverified):** the workers pass the schema class into the provider SDK (`linkup_search_worker` hands it to `async_search(structured_output_schema=…)`). Check whether the SDK internally instantiates that class before returning the dict — if it does, threading the real class in makes the caller's validators run inside the SDK and again in the submitter, the same double-run.

This interacts with the shared-helper design in `wip/refactoring/revalidate-against-object-class-is-duplicated-three-ways.md` (the helper needs a dict arm without the short-circuit), which is one more reason to do that consolidation first.

## What doing it looks like

Mirror the object path — adjusted for the dict-out contract above:

1. `search_gen_structured(search_object_assignment, *, output_class: type[BaseModel] | None = None)`, same keyword-only shape, `None` = boundary.
2. Same for `dry_search_gen_structured`.
3. Resolve through `object_class_resolution.resolve_object_class`'s sibling (it currently takes an `ObjectAssignment`; `SearchObjectAssignment` carries the same two fields under different names, so either generalize the helper over the two field names or add a thin second entry point — do **not** duplicate the `SchemaToModelFactory` call).
4. `make_search_structured` passes `output_class=output_structure_class`.
5. Re-scope `test_dry_search_structured_fidelity_gap_raises_typed_error` to the boundary composition, exactly as `test_dry_run_object_fidelity.py` was.

`SearchObjectAssignment`'s wire shape must not change, for the same reason `ObjectAssignment`'s did not.

## Related

- `wip/refactoring/boundary-revalidation-round-trip-is-unaudited.md` — the other deferral out of the same PR.
