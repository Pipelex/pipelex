# S2 — Enrich: implementation tracker

Seeded from [`wip/enrich/design.md`](wip/enrich/design.md) §7 (the design stays authoritative for rationale; this file tracks live progress). Milestone branch: `feature/Enrich`.

## Decisions ratified (Phase 0, 2026-08-23, by Louis)

1. **E3 — reject the pair.** A structure field declaring both `required = true` and a `default_value` is a validation error (breaking; mthds spec sentence via inbox; the sole fixture instance moves to `rejected/`).
2. **E5/E9 — replace, not add.** Input contract `presence: "plain" | "optional" | "force"` **replaces** `optional`; `multiplicity` goes three-valued (`single`/`variable`/`fixed`) with `item_count` exactly when `fixed`, on input and output contracts. Output keeps its two-valued `optional`. Breaking protocol change, spec-first, rides the release cascade.
3. **Reflected defaults are authored facts.** A pydantic default on a reflected class field reports `required: false` + its `default_value` in the descriptor; `field_info.is_required()` is the single source of truth.

## Phase 0 — ratify and sweep

- [x] Decisions §6 confirmed by Louis (see above)
- [x] Sweep at head: hopeful extra keys in structure-field tables across fixtures, corpus entries, and cookbook-adjacent test data (E7 fallout list)
- [x] Sweep at head: `required = true` + `default_value` pairs across the same surfaces (E3 fallout list)
- [x] Inventory captures that pin emitted schema bytes (codegen/validate parity corpora, conformance captures, characterization tests) so Phase 2 re-baselines are deliberate
- [x] Record the fixture-fallout list for Phases 1–2 below

### Phase 0 findings

- **Structure-field sweep (2026-08-23, at head of `feature/Enrich`):** parsed every `.mthds`/concept-bearing `.toml` under this worktree, `pipelex-cookbook`, and `pipelex-starter-python`. The ONLY unknown-key carrier is the probe bundle's `constrained_count` (`tests/data/input_semantics/probe_bundle.mthds:61` — extras `minimum`, `maximum`, `examples`, `unit`), and the ONLY `required`+`default_value` pair is the probe bundle's `titled_default` (`probe_bundle.mthds:30`). No fallout anywhere else; both fields are handled by the design's own plan (extras: E7 flip keeps them as deliberate rejected-case material; `titled_default` moves to a `rejected/` fixture in Phase 4).
- **Schema-byte capture inventory (very thorough sweep):** NOTHING under `tests/` pins schema bytes — every schema assertion is key-presence or single-value, so Phase 2's render changes are test-green without re-baselining (no snapshot framework exists in the repo). The only committed full-schema payloads are the S1 audit captures under `wip/input-semantics/probe/` (hop3 raw schemas, hop4 renders, hop5 contracts), re-baselined by one command: `.venv/bin/pipelex-dev trace-input-semantics tests/data/input_semantics/probe_bundle.mthds -o wip/input-semantics/probe`. Hand edits Phase 2 owes: `docs/tools/cli/build/output.md:161-239` (its example `--format schema` output shows the class-name `title`, no top-level `description`, and a `MyType[5]` array with no `minItems`/`maxItems` — falsified by all three enrichments). Digest surfaces checked (migration fingerprints, crate fingerprints, codegen stamps): none hashes rendered schema. Conformance (sibling repo) pins nothing schema-byte-wise; it becomes relevant only at Phase 3. Natural home for new seam unit tests: `tests/unit/pipelex/core/concepts/test_concept_representation_generator.py`; for integration assertions: `tests/integration/pipelex/cli/test_trace_input_semantics_cmd.py`.

## Phase 1 — loudness (E7, E8)

- [x] E7: `extra="forbid"` on `ConceptStructureBlueprint` (`pipelex/core/concepts/concept_structure_blueprint.py`) — field-table *keys* strict; hint *content* stays lenient (unknown hint keys still warn + preserve)
- [x] E8: builder writes `default_value`, not `default` (`pipelex/builder/operations/concept_ops.py`)
- [x] E8: write-then-validate round-trip test for builder-authored defaults (`tests/unit/pipelex/builder/operations/test_concept_spec_to_toml.py` — two existing assertions had pinned the buggy `default` key and were fixed too)
- [x] Regenerate `mthds_schema.json` — `ConceptStructureBlueprint` now carries `additionalProperties: false` (schema is generated + gitignored; downstream copies sync at release per the filed inbox item)
- [x] Apply Phase 0 fixture fallout: probe bundle's `constrained_count` lost its hopeful extras (its description string kept byte-identical — it is hashed by the fingerprint pins); the extras live on in the new `tests/data/input_semantics/rejected/unknown_structure_field_key.mthds_invalid`
- [x] Unit tests: forbid rejection + hint leniency (`tests/unit/pipelex/core/concepts/concept_blueprint/test_concept_structure_blueprint_extra_keys.py`)
- [x] H2 fingerprint invariant check: `test_fingerprint_pins.py` green with UNCHANGED pins
- [x] Changelog (Unreleased): E7 breaking (Changed) + E8 fix (Fixed)
- [x] Deliver + remove inbox item `../wip/inbox/2026-08-21-pipelex-builder-default-key-dropped.md` (deleted; fix, round trip, and forbid all delivered)

**Checkpoint 1** — authoring loop honest, nothing wire-visible changed yet.

- [x] Checkpoint 1: tracker updated, `make agent-check` green, targeted tests green (concepts + builder + fingerprint pins + input-form integration)

### Checkpoint 1 state (for cold start)

Decisions all ratified (§ above). Phase 1 delivered E7+E8 entirely inside: `concept_structure_blueprint.py` (forbid), `concept_ops.py` (key fix), probe bundle + new rejected fixture, three test modules touched. Note for Phase 4: removing `titled_default` from the probe bundle WILL move the pinned hint-free fingerprints in `tests/unit/pipelex/libraries/test_fingerprint_pins.py` — that is a legitimate fixture-content change, not a model leak; the pins must be recomputed then, against the test docstring's usual advice, or the pin test moved onto a stable fixture. The check-mthds PostToolUse hook flags the probe bundle with a stale bundled schema — `plxt lint` with the regenerated `derived/mthds_schema.json` is the authority and passes.

## Phase 2 — schema enrichment (E6, E1-title, E4)

- [x] E6: `_render_schema_representation` (`pipelex/core/concepts/concept.py`) injects the concept's authored description as top-level `description` (no-op for generated classes; authored fact for class-backed; pinned native blueprint description for native direct inputs)
- [x] E6: docstrings on native content classes lacking one (`TextContent`, `ImageContent`, `DocumentContent`, `PageContent`, `NumberContent`, `HtmlContent`, `YesNoContent`) — pinned description text verbatim; the pinned-consistency test (`tests/unit/pipelex/codegen/test_native_expansion.py`) compares factory descriptions, not docstrings, so no interference
- [x] E1: top-level `title` becomes the concept ref at the same render seam (nested identity stays descriptor-only; no `$defs` renames)
- [x] E4: `render_concept_representation` takes real multiplicity (not a boolean) — threaded through `render_stuff_spec`; new helpers `is_multiple_multiplicity` / `fixed_item_count` in `variable_multiplicity.py`; `StuffSpec.is_multiple()` delegates; `runner_code.py` local `_is_multiple` deleted in favor of the shared helper
- [x] E4: array wrap emits `minItems`/`maxItems` = N when fixed; variable `[]` gets neither bound; `[1]` stays single (no wrap, no bounds)
- [x] E4: contract memo key normalized to `(concept_ref, is_multiple, fixed_count)` (avoids the `hash(True) == hash(1)` collision between `Concept[]` and `Concept[1]`)
- [x] Guard: `DocumentContent.url` field-description wording untouched (class gained only a docstring)
- [x] Probe bundle + trace harness: no extension needed — the existing fixtures already exercise class-backed (`probe_refined.classbacked`), native-direct (`probe_native_inputs`), and fixed-count (`probe_markers.two = Gadget[2]`) inputs; all three enrichments verified present in the regenerated captures
- [x] Re-baseline the Phase 0-inventoried schema-byte captures: `wip/input-semantics/probe/` regenerated; `docs/tools/cli/build/output.md` schema examples hand-updated (concept-ref title, top-level description, `minItems`/`maxItems`)
- [x] Unit tests at the render seams: four new tests in `TestSchemaRepresentationWithMultiple` (title/description injection, array identity on items, fixed-count bounds, `[1]` stays single) + `tests/unit/pipelex/core/pipes/test_multiplicity_helpers.py` for the two helpers
- [x] Changelog (Unreleased): additive schema enrichments

**Checkpoint 2** — the "zero client changes" half complete and measurable.

- [x] Checkpoint 2: tracker updated, checks green

### Checkpoint 2 state (for cold start)

Phase 2 delivered entirely inside: `concept.py` (render seam: multiplicity param + title/description injection + array bounds), `variable_multiplicity.py` (two new helpers), `stuff_spec.py` (delegation + pass-through), `runner_code.py` (shared helper), `pipe_io_contracts.py` (normalized memo key), seven native content classes (docstrings), plus tests, probe re-baseline, and the docs example. Signature change is breaking for direct callers of `render_concept_representation` (`is_multiple` → `multiplicity`) — all in-repo callers and tests updated. Phase 3 recon (from the paused-note, still valid): `PresenceMarker` in `variable_multiplicity.py` is exactly the contract's `presence` vocabulary; contract models to replace are `pipe_io_contracts.py` (`IOMultiplicity`, `PipeInputContract`, `PipeOutputContract`). Note for Phase 4 (unchanged): removing `titled_default` from the probe bundle WILL move the pinned hint-free fingerprints in `test_fingerprint_pins.py` — recompute the pins then.

## Phase 3 — contract reshaping (E5, E9) — protocol change, spec-first

- [x] Spec: `../docs/specs/pipelex-mthds-protocol.md` — `pipe_io_contracts` row, "Optional IO contracts and liftable pipes" section, Verified-by line, and the abridged `ValidReport` example all updated to `presence` / three-valued `multiplicity` + `item_count`
- [x] Spec: one sentence documenting `json_schema` as pydantic-canonical, single-choice enums as `const` (E10's documentation half) — appended to the `pipe_io_contracts` row
- [x] Conformance: assertions reshaped in `conformance/tests/pipelex_api/test_validate_optionals.py` — the gate is shape-detected (`presence` absent → skip), so it arms automatically when `pipelex-api` re-pins at the cascade; the fixed-count arm stays pinned in pipelex's own suite (the shared optionals fixture has no `[N]` slot, deliberately not extended)
- [x] `make check-spec-links` in `conformance/` — green (note: `make agent-check` there also surfaced PRE-EXISTING vendored-corpus drift on `vocabulary.toml` from H2, covered by the filed release-time sync inbox item — not this branch's to fix)
- [x] Engine: `PipeInputContract.presence` replaces `optional` (reuses `PresenceMarker` — same wire values as the descriptor); input + output gain three-valued `IOMultiplicity` (+`FIXED`) and `item_count` via the new `make_io_multiplicity` projection; output `optional` unchanged
- [x] Emission threads real multiplicity (retired `IOMultiplicity`'s fixed-reports-as-variable ruling)
- [x] Tests on the contract fields: `tests/integration/pipelex/pipeline/test_pipe_io_contracts.py` reshaped + new `make_two` fixed-count pipe pinning `fixed`/`item_count=2` on input and output plus the bounded array schema
- [x] Changelog (Unreleased): breaking protocol reshape
- [x] Probe hop5 capture re-baselined (same regen command); verified `opt/many/two/forced` report exactly (`optional`,`single`) / (`plain`,`variable`) / (`plain`,`fixed`,2) / (`force`,`single`)

**Checkpoint 3** — the protocol change contained in one reviewable unit.

- [x] Checkpoint 3: tracker updated, checks green (`make check` exit 0; the full suite surfaced ONE stale assertion — `test_trace_input_semantics_cmd.py` still pinned the pre-reshape `inputs.hint.optional` — fixed to `presence`/`multiplicity`; full-suite green rides Phase 4's final gate)

## Phase 4 — semantics and close (E3, reflected defaults)

- [x] E3: model validator on `ConceptStructureBlueprint` rejecting `required = true` + `default_value` (message names both remedies) + unit seam `test_concept_structure_blueprint_required_default.py`
- [x] E3: generator's accidental branch replaced by an explicit raising invariant (`ConceptStructureGeneratorError`) + unit seam `test_structure_generator_required_default_invariant.py`
- [x] E3: probe bundle's `titled_default` moved to `rejected/required_with_default.mthds_invalid`; pair-sweep fallout applied (builder fixture `test_data.py` had authored the pair — `age` keeps `required`, drops the default); `test_input_form.py` now pins `motto` (`required: false` beside its default); fingerprint pins legitimately recomputed (fixture-content change, recorded in the pin module's docstring)
- [x] Reflected defaults: `_with_reflected_constraints` reads `field_info.is_required()` + `field_info.default` (a `None` default is the optionality artifact, never reported); kind-table row via the new `retries` field on `InputFormConstrainedPayload`
- [x] Descriptor spec touch-up: the "may carry both" sentence retired (`default_value` row now states the rejection), the "Facts over emission accidents" bullet notes the founding case resolved, the Verified-by line follows; the D2 conformance skeleton's fixture + assertions moved with it (`required = true` dropped from its `title` field) — `make check-spec-links` green
- [x] Survival table updated with before/after closure rows (E3, E4, E5, E6/E1, E7, E9) against regenerated `wip/input-semantics/probe/` captures (`titled_default` gone from all hops)
- [x] Findings addendum §F: per-entry closure evidence table
- [x] Roadmap Track S closure bullet: in-engine close now, hosted-wire half at the cascade
- [x] Changelog (Unreleased): E3 breaking + reflected-defaults ruling (Changed)
- [x] Cross-repo inbox filings (§8): `2026-08-23-mthds-structure-field-validation-sentences.md`, `2026-08-23-pipelex-js-mirror-schema-enrichments-and-contract-reshape.md`, `2026-08-23-mthds-js-protocol-types-contract-reshape.md`
- [x] In-repo docs swept: `inline-structures.md` gains the `required` bullet + the pair rule; `under-the-hood/input-form-descriptor.md` constraint paragraph updated (E7 made the "parser drops unknown constraint keys" claim false) + reflected-defaults sentence
- [x] Final: `make agent-check` + full `make agent-test` green (suite exit 0)

## Out of scope (per design §9)

Language ceiling (S1 §B) syntax, app-side fixes (M1), corpus widening, `const`→`enum` render rewrite, descriptor wire-model round-trip alias (D4).
