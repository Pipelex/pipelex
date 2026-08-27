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
