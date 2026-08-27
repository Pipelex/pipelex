# S2 "Enrich" — deferred findings

Items surfaced by the pre-landing review of PR #1149 that are real but not clear-cut wins to fix on the branch. Each needs a ruling or a design choice; none blocks the merge.

## 1. Non-JSON-serializable reflected default can crash report serialization far from its cause

`pipelex/pipeline/input_form.py` (`_with_reflected_constraints`) stamps `field_info.default` raw into the descriptor's `default_value: Any` slot. A registered hand-written class whose field default holds a non-JSON-serializable value turns a valid bundle's report dump into a `PydanticSerializationError` at serialization time, far from the offending class. Exposure is limited by `reflect_structure_class`'s annotation gating (only mappable annotations reach reflection at all). The candidate remedy is to coerce via `pydantic_core.to_jsonable_python` and drop the fact on failure, per the faithful-or-absent rule — but silently dropping an authored fact versus failing loudly is a design choice that deserves a ruling, not a speculative guard.

## 2. `_peel_multiplicity` rules `[1]` the opposite way from the rest of the chain — RULED, fixed

`pipelex/core/memory/input_shaper.py` (`_peel_multiplicity`) treated a fixed count of 1 as a one-item **list**, while the S2 chain — `variable_multiplicity.py` helpers, the wire contract, the schema render, and `docs/under-the-hood/input-form-descriptor.md` — all ruled `[1]` **single** (no list framing). So a `[1]` slot's published schema said single object while the runtime shaper framed the payload as a list, and a consumer rendering a form on the descriptor would submit a value the shaper refused.

The ruling went the way the standard already states it (`mthds/docs/language/multiplicity.md`, "A count of one is not a list"): `[1]` is the single form, and the shaper was the side that was wrong. Rather than correct that one function, the count now collapses to `None` at the sites that *build* a multiplicity — `parse_concept_with_multiplicity`, `InputStuffSpecsFactory.make_from_string`, `make_variable_multiplicity` — so the value `1` is unrepresentable downstream and no consumer has to remember the rule. `_peel_multiplicity` delegates to the shared projection helpers instead of re-deriving them, which is what let it drift in the first place. Fixing it surfaced three more sites re-deriving the same semantics from raw text: the blueprint's input-side marker check (which refused `Concept[1]?` while the output half accepted it), the contract-match canonicalizer (which read a header's `Brief` and a definition's `Brief[1]` as a mismatch), and the run-time output-multiplicity override.

## 2b. The input-spec factory accepts `Concept[0]` where the io-ref parser refuses it — RULED at the validators

Surfaced while ruling §2, then ruled in PR #1157's review round: `PipeBlueprint.generic_validate_inputs` and its spec-layer mirror (`PipeSpec.validate_inputs`) now refuse a non-positive bracket count with a plain `ValueError` ("Multiplicity must be at least 1") before the marker check, which matches how the output half surfaces the same rule through `parse_concept_with_multiplicity`. That closes the authoring paths — a `[0]` input is rejected at blueprint construction instead of detonating later in reference collection as an uncaught `PipeVariableMultiplicityError`. `InputStuffSpecsFactory.make_from_string` itself still matches `(\d*)` without the range check, but every route into it passes a validated blueprint first, so the residue is defense-in-depth, not a reachable hole.

## 2c. The two input-side validators still hand-roll the ref grammar

`generic_validate_inputs` and `PipeSpec.validate_inputs` each do `re.match(MULTIPLICITY_PATTERN, ...)` plus three group reads where a single `parse_concept_with_multiplicity` call would parse before deciding — which is what the blueprint's own comment says it wants, and what let §2/§2b drift in the first place. Folding them onto the parser means reconciling the error surfaces (the tests match on the validators' "Invalid input syntax for ..." prefix and the typed `OPTIONAL_MARKER_INVALID`); mechanical but not free, so it was left out of the round-1 fixes.

## 3. `_with_reflected_constraints` name/content drift

The function now stamps presence and default facts as well as constraints; the docstring says so but the name and the `constraints` dict variable don't. Rename-only suggestion (e.g. `_with_reflected_facts`) — not worth churn on its own; fold into the next touch of the module.

## 4. Contract builder normalizes multiplicity twice per input

`pipelex/pipeline/pipe_io_contracts.py` — the schema-memo key hand-normalizes `(is_multiple, fixed_count)` with the `hash(True) == hash(1)` caveat comment, while `make_io_multiplicity` computes the same projection a few lines later. Keying the memo on the `(IOMultiplicity, item_count)` pair from a single up-front `make_io_multiplicity` call would drop both the duplication and the caveat. Current code is correct (all four arms verified; the collision trap is genuinely closed and now pinned by a test) — simplification only.

## 5. `rejected/` fixture corpus is mostly inert

Four of the pre-existing `tests/data/input_semantics/rejected/` fixtures (`default_on_concept_field`, `multiple_refines`, `non_string_choices`, `refines_plus_structure`) are loaded by no test — the directory grew as a documentation corpus with only `per_input_description` (and now the two S2 fixtures, wired on this branch) exercised through the parser. A parametrized parser-level harness sweeping the whole directory would keep fixtures from rotting, but each fixture must first be confirmed to actually fail today's parse (some may document aspirational rejections) — audit before wiring.

## 6. The `[1]` collapse is enforced at the build sites, not at the type

Surfaced by PR #1157's review round. The count collapses wherever a multiplicity is *built* from authored syntax, which is enough for every path that goes through a parser — but the invariant the changelog states ("the value `1` no longer exists downstream") is not structural, and three sites falsify it today:

- `pipelex/pipe_operators/img_gen/pipe_img_gen_factory.py` sets `final_multiplicity = ... else 1`, so **every** bare `Image` output carries a literal `1` in `PipeImgGen.output_multiplicity`. Harmless — `output_multiplicity_to_apply` normalizes it at run time — but the comment beside it ("default to 1 if no brackets") now reads backwards, since no brackets is the single form.
- `SubPipeFactory` assigns `blueprint.nb_output` verbatim, so an authored `nb_output = 1` lives as a raw `1` on `SubPipe.output_multiplicity`. Every consumer that resolves it through `output_multiplicity_to_apply` gets the right answer; the two that did not were fixed in `a61a9163d`.
- `StuffSpec.multiplicity` is a plain pydantic field with no validator, and `format_concept_with_multiplicity(multiplicity=1)` renders `Text[1]`, which the parser reads back as `None`. So the documented parse/format inverse does not hold in one direction, and a `1` arriving by direct construction or `model_validate` is never collapsed.

Making it structural is a `@field_validator` on `StuffSpec.multiplicity` plus a `normalize_variable_multiplicity` inside `format_concept_with_multiplicity`, after which the build-site calls become belt-and-braces rather than the whole enforcement. Deferred because `tests/unit/pipelex/core/pipes/test_concept_multiplicity_formatting.py` deliberately pins `("Image", 1, "Image[1]")`, so the emitter is currently an intentional non-collapsing site — changing it is a ruling, not a cleanup.

## 7. The zero-count rule is enforced on the bracket spelling only

`Concept[0]` is now refused at both authoring layers (§2b), but the same count spelled as a step field is not: `SubPipeBlueprint.nb_output` carries no `ge=1`, and `SubPipeFactory` tests it for truthiness, so `nb_output = 0` silently means "no override" and `nb_output = -2` validates green and reaches `PipeLLM` as `fixed_nb_output = -2`. One language rule, two answers depending on which surface the author used. A `Field(ge=1)` on `nb_output` closes it.

Relatedly, there is no *upper* bound anywhere: `Text[100000000000]` is accepted by every validator this branch touched, and `WorkingMemoryFactory.make_mock_stuff` materializes the count (`native.Text[50000]` builds fifty thousand items in about five seconds) on the mock-inputs dry-run path, reachable from bundle text alone. The branch that established "the count is validated where it is written" added the floor and no ceiling.

## 8. `make_mock_stuff` is the sibling of the bug §2 fixed

`pipelex/core/memory/working_memory_factory.py` decides plurality by truthiness (`if not typed_named_stuff_spec.multiplicity:`) and then takes the count verbatim, so a multiplicity of `1` still builds a one-item `ListContent` — the exact framing §2 set out to eliminate, in the one builder that was not converted onto `is_multiple_multiplicity` / `fixed_item_count`. Latent only: reachable through the `1`-carrying sites in §6. The fix is the same two-line delegation `_peel_multiplicity` received.

## 9. The `[0]` input errors are untyped, unlike every rule beside them

`PipeBlueprint.generic_validate_inputs` and `PipeSpec.validate_inputs` raise a bare `ValueError` for a non-positive count, while the presence-marker rule nine lines below raises a typed `PipeValidationError(error_type=OPTIONAL_MARKER_INVALID, ...)` and the output side raises `PipeVariableMultiplicityError`. So `Text[0]` is the one input-grammar violation the categorizer and the fix planner cannot act on, and the identical rule is worded two ways depending on the side it was written. Per this workspace's rule that structured fields are the contract and prose is presentation, one rule should produce one structured verdict. Folds naturally into §2c, which has to reconcile the same error surfaces.

## 10. `PipeRunParams.output_multiplicity` coerces a string count of one to `True`

`VariableMultiplicity = bool | int`, and pydantic resolves the union bool-first, so `output_multiplicity="1"` and `output_multiplicity=1.0` both become `True` — "let the model decide" — while `"2"` correctly becomes `2`. Only the count of one inverts, and it inverts into the opposite meaning. The union order predates PR #1157, but that branch is what makes `output_multiplicity=1` a documented public knob, so the string form an HTTP or SDK caller sends is newly worth getting right. `StrictBool | int` on the field, or a validator, settles it. `output_multiplicity=0` is a second gap: it resolves to `(0, is_multiple=True, count=0)` and reaches `PipeImgGen` as `nb_images = 0`, which generates one image anyway.

## 11. A top-level `output_multiplicity=1` still splits the static pass from the run path

`PipeSequence` copies the caller's run params to every step, so a top-level `output_multiplicity=1` reaches steps that declare their own plural output. `is_plural_step_result` reads only the step's *own* override (`None` there), so it answers plural from the declaration, while the run path resolves the inherited `1` to the single form. A lifted step then records an absence where the taint pass promised an empty list. Narrow trigger and the fix is a design question — whether an inherited override should participate in the static promise at all — so it was not folded into `a61a9163d`, which fixed only the sites reading a step's own override.
