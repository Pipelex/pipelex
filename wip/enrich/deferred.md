# S2 "Enrich" — deferred findings

Items surfaced by the pre-landing review of PR #1149 that are real but not clear-cut wins to fix on the branch. Each needs a ruling or a design choice; none blocks the merge.

## 1. Non-JSON-serializable reflected default can crash report serialization far from its cause

`pipelex/pipeline/input_form.py` (`_with_reflected_constraints`) stamps `field_info.default` raw into the descriptor's `default_value: Any` slot. A registered hand-written class whose field default holds a non-JSON-serializable value turns a valid bundle's report dump into a `PydanticSerializationError` at serialization time, far from the offending class. Exposure is limited by `reflect_structure_class`'s annotation gating (only mappable annotations reach reflection at all). The candidate remedy is to coerce via `pydantic_core.to_jsonable_python` and drop the fact on failure, per the faithful-or-absent rule — but silently dropping an authored fact versus failing loudly is a design choice that deserves a ruling, not a speculative guard.

## 2. `_peel_multiplicity` rules `[1]` the opposite way from the rest of the chain

`pipelex/core/memory/input_shaper.py` (`_peel_multiplicity`) treats a fixed count of 1 as a one-item **list**, while the S2 chain — `variable_multiplicity.py` helpers, the wire contract, the schema render, and `docs/under-the-hood/input-form-descriptor.md` — all rule `[1]` **single** (no list framing). So a `[1]` slot's published schema says single object while the runtime shaper frames the payload as a list. Pre-existing (the file is untouched by the branch), made visible by the new ruling; each side's docstring claims its ruling as universal. Cross-surface semantic decision: either the shaper adopts the `[1]`-is-single ruling or the divergence is documented as intentional at the memory boundary.

## 3. `_with_reflected_constraints` name/content drift

The function now stamps presence and default facts as well as constraints; the docstring says so but the name and the `constraints` dict variable don't. Rename-only suggestion (e.g. `_with_reflected_facts`) — not worth churn on its own; fold into the next touch of the module.

## 4. Contract builder normalizes multiplicity twice per input

`pipelex/pipeline/pipe_io_contracts.py` — the schema-memo key hand-normalizes `(is_multiple, fixed_count)` with the `hash(True) == hash(1)` caveat comment, while `make_io_multiplicity` computes the same projection a few lines later. Keying the memo on the `(IOMultiplicity, item_count)` pair from a single up-front `make_io_multiplicity` call would drop both the duplication and the caveat. Current code is correct (all four arms verified; the collision trap is genuinely closed and now pinned by a test) — simplification only.

## 5. `rejected/` fixture corpus is mostly inert

Four of the pre-existing `tests/data/input_semantics/rejected/` fixtures (`default_on_concept_field`, `multiple_refines`, `non_string_choices`, `refines_plus_structure`) are loaded by no test — the directory grew as a documentation corpus with only `per_input_description` (and now the two S2 fixtures, wired on this branch) exercised through the parser. A parametrized parser-level harness sweeping the whole directory would keep fixtures from rotting, but each fixture must first be confirmed to actually fail today's parse (some may document aspirational rejections) — audit before wiring.
