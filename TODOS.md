# Engine intent hints (H2) — implementation tracker

Working tracker for `wip/engine-hints/design.md` on branch `feature/Engine-hints`. Read the design doc first — it holds the rationale, the contract, and the file/line anchors; this file only tracks execution. Checkpoint protocol: at each checkpoint, update the design doc with decisions taken and deviations, verify cold-start readiness, and tick the checkpoint box here.

## Resume state (for a cold start)

Phases 1 and 2 are landed and green through Checkpoint A (`make agent-check`, `make check`, `make test` all pass). Decisions taken so far that the design doc does not spell out:

- **Sorted-hints emission solved at the model, not the encoder:** the shared `normalize_empty_hints` validator on all three models sorts hints keys, so every dump (fingerprints, codegen crate encoding, wire) is canonical without any encoder walking.
- **Effective hints in normalization:** `_RefinementResolution.effective_hints` is position-specific — the cache write-back walks `reversed(path)` accumulating each visited ref's own hints over what lies below it (`merge_hints`), so a memoized mid-chain resolution carries ITS position's hints (guard test mutation-verified: the naive shared write-back reds exactly that test). `_flatten_refinement` stamps `merge_hints([base_resolution.effective_hints, value.hints])` on BOTH arms — flattened and refines-keeping — and also on chains whose base has no structure to materialize.
- Hinted fixtures: `tests/data/input_semantics/hinted_bundle.mthds` (all three sites, chain override + inheritance, unknown-key preservation, collapsing slot, marked slot); normalization fixtures in `tests/unit/pipelex/libraries/test_crate_normalization_hints.py`.

- **`PipeBlueprint.inputs` is `Mapping[str, str | InputSlotBlueprint] | None`, not `dict`** — value-covariant, so the many `dict[str, str]` construction sites (specs, tests) stay legal without casts. Rationale is a docstring on the field.
- **Two access paths for consumers:** grammar-only consumers read the projection `PipeBlueprint.inputs_concept_specs` (or `slot_concept_spec(value)` per value); hints-aware consumers read `inputs` itself. Sites swept to the projection: `contract_match` (hints don't affect contract identity), `crate_normalization._collect_referenced_natives`, `pipe_factory` (both the concept-existence loop and the `InputStuffSpecsFactory` call — the design's "factory accepts the union" became a call-site projection, same invariant: runtime `StuffSpec` never sees hints), `pipe_llm_factory` + `pipe_img_gen_factory` template analyzers, `pipe_structure_blueprint`, `pipelex_bundle_blueprint._collect_local_refs_from_pipe`, `trace_input_semantics_cmd` (framing manifest carries the concept string; hints surface at hop 5), and all builder `*_spec.from_blueprint` sites (spec layer stays `dict[str, str]`; hints dropped there — builder emission is the known out-of-scope follow-up).
- **Hints travel untouched through:** `crate_qualification` (new `_qualify_slot_value` qualifies the table arm's `concept`, hints pass through) and `bundle_elaborator` (copies `inputs` as-is, so PipeLLM→sequence elaboration keeps slot hints on the draft step and the wrapping sequence).
- **Subject grants recorded** for `merge_hints`, `applicable_intent`, `is_intent_word_known`, `intent_word_applies`, `slot_concept_spec`, `_qualify_slot_value` (in `subject_grants.toml`).
- The pinned fingerprints live in `tests/unit/pipelex/libraries/test_fingerprint_pins.py`, computed on the probe bundle BEFORE the fields landed — keep `tests/data/input_semantics/probe_bundle.mthds` hint-free forever; hinted fixtures go in sibling files.

Next actions, in order: finish Phase 1's remaining fixtures/tests (unchecked boxes below), then Phase 2's effective-hints merge in normalization.

## Phase 1 — Language surface

### Shared hints module

- [x] Create `pipelex/language/intent_hints.py`: `INTENT_HINT_KEY = "intent"`, the closed vocabulary (`prose`, `label`, `rating`, `quantity`), pinned per standard version like the native concept definitions.
- [x] Implement `merge_hints(layers)` — key-by-key, later (nearer) layer wins, empty result is `None`. This is the ONE precedence implementation; normalizer and deriver both call it.
- [x] Implement the applicability predicates (text-valued / number-valued site judgment per the spec's Applicability section; description-only concepts are text-valued; plural sites judged per item) and `applicable_intent(hints, *, site) -> str | None`.
- [x] Unit tests for the module: merge precedence, empty-merge → `None`, applicability over each site shape, `applicable_intent` returns only known-and-applicable words.

### Pinned-fingerprint regression (land BEFORE the model changes)

- [x] Compute the normalized fingerprint of a committed hint-free fixture bundle against the unchanged models, hardcode the hex in a regression test, and commit it first — the suite must prove existing digests do not move when the fields land.

### The three parse sites

- [x] `ConceptBlueprint` (`pipelex/core/concepts/concept_blueprint.py`): add `hints: dict[str, str] | None = None` (`extra="forbid"` already in force — strict shape for free).
- [x] `ConceptStructureBlueprint` (`pipelex/core/concepts/concept_structure_blueprint.py`): add the same field. Do NOT change the extras policy — the E7 `extra="forbid"` fix stays in S2's strictness sweep (design Part 1b).
- [x] New `InputSlotBlueprint(BaseModel)` with `extra="forbid"` and exactly two fields: `concept: str` (full existing slot grammar) and `hints: dict[str, str] | None = None`.
- [x] Widen `PipeBlueprint.inputs` to `dict[str, str | InputSlotBlueprint] | None` (`pipelex/pipe_machinery/pipe_blueprint.py`); check the union assembly in `pipelex/mthds_parsing/pipelex_bundle_blueprint.py` propagates to every `Pipe*Blueprint` subclass.
- [x] Extend `generic_validate_inputs` (`pipe_blueprint.py`) to validate the table arm's `concept` with the same ref+multiplicity+presence grammar as the string arm — one grammar, two spellings.
- [x] Implement the parse-time collapse rule at model validation: a slot table with absent or empty `hints` collapses to its plain string, so hint-free bundles produce byte-identical blueprints by construction.
- [x] Empty-table removal on concept/field models too (validator normalizing `hints = {}` to `None`) so the crate never holds an empty hints table.

### Serialization — fingerprint neutrality

- [x] Add a `@model_serializer(mode="wrap")` to `ConceptBlueprint`, `ConceptStructureBlueprint`, and `InputSlotBlueprint` that drops only the `hints` key when `None` (pattern: `InputFormField.serialize_without_inapplicable_slots`, `pipelex/pipeline/input_form.py`). Deliberately NOT a blanket `exclude_none` — see design Part 2.
- [x] Check `pipelex/codegen/crate_encoding.py`'s TOML emission orders hints entries sorted by key; fix if not (JSON side is covered by `sort_keys=True` in both fingerprint functions). RESOLVED at the model instead: the shared `normalize_empty_hints` validator sorts hints keys on all three models, so every dump (fingerprints, codegen, wire) is canonical with no encoder walking.

### Fixtures and tests

- [x] Update `tests/data/input_semantics/rejected/per_input_description.mthds_invalid` commentary: it remains a valid rejection, but the rationale shifts to "unknown slot-table key"; verify the failure now surfaces as the slot-table extras error.
- [x] Add accepted-fixture siblings: `{ concept = "…" }` (collapses to string form) and `{ concept = "…", hints = { intent = "prose" } }`.
- [x] Parse unit tests (homes: `tests/unit/pipelex/core/concepts/concept_blueprint/`, `tests/unit/pipelex/mthds_parsing/`): each site accepts a valid flat table; non-table `hints`, non-string values, and nested tables fail as structural errors at all three sites; unknown slot-table keys fail; the collapse rule; grammar preserved through the table arm (multiplicity + markers on `concept`).
- [x] Serialization unit test: the serialized JSON of a hint-free concept/field/pipe contains no `hints` key at any depth.
- [x] Re-run unchanged: `test_fingerprint_determinism`, `test_normalization_is_idempotent`, the round-trip integration suite, and the pinned-fingerprint regression — all green with the fields in place.

## Phase 2 — Crate travel

- [x] `crate_qualification._qualify_io_ref` (`pipelex/libraries/crate_qualification.py`): handle the table arm — qualify the table's `concept` through `_render_ref_with_markers`, pass `hints` through untouched.
- [x] `crate_normalization._collect_referenced_natives` (`pipelex/libraries/crate_normalization.py`): read the table arm's `concept`.
- [x] `InputStuffSpecsFactory.make_from_blueprint` (`pipelex/core/pipes/inputs/input_stuff_specs_factory.py`): accept the union, extract the `concept` string ONLY. `StuffSpec` must NOT grow a hints field — runtime models stay hint-free (structural non-normativity).
- [x] Effective hints in normalization: extend `_RefinementResolution` with `effective_hints: dict[str, str] | None`; accumulate along the child→base walk in `_resolve_refinement` via the shared `merge_hints` (nearer declaration wins). Applies to both the flattened arm and the `refines`-keeping (native-backed) arm; pinned natives contribute nothing. Empty merge leaves no member.
- [x] Memoization guard: a cached mid-chain resolution must carry the hints of ITS position in the chain, not the querying concept's — add a test that exposes this.
- [x] Structure-field and slot hints carried as authored through qualification and normalization (no merge at crate level — the site-over-concept merge is the deriver's).
- [x] Normalization unit tests (`tests/unit/pipelex/libraries/test_crate_normalization.py`): chain merge on both arms, memoized mid-chain hints, empty merge, idempotency extended to a hinted fixture (re-normalizing is a no-op).
- [x] Integration: round-trip suite green with a hinted fixture; a hinted crate's fingerprint differs from its hint-free twin.

## Checkpoint A — crate layer done

- [x] Hints parse at three sites, travel qualified and normalized, hint-free crates provably keep their digests. Update `wip/engine-hints/design.md` with decisions and deviations; verify cold-start readiness; commit.

## Phase 3 — Advisory lint

- [x] New `pipelex/pipeline/hint_warnings.py` with `build_hint_warnings(...)`: sweep the qualified crate's three sites, emit one advisory `ValidationErrorItem` per finding (unknown hint key, unknown `intent` word, applicable word on inapplicable site), each naming its site (concept code / field name / pipe code + slot name). Warn only — never reject; well-formed unknown content is preserved.
- [x] Advisory enum: new `HintLintErrorType` (`hint_unknown_key`, `hint_unknown_intent`, `hint_inapplicable_intent`) joined into the `ValidationErrorType` alias (`pipelex/validation_error_types.py`). Open question 1: if the render layer's required properties make a shared enum cheaper, decide here with the code in view — the wire strings are the contract, the enum layout is not. RESOLVED open question 1: separate enum, no render-layer properties needed.
- [x] Wire into `pipelex/pipeline/validate_in_process.py` beside `build_optionality_warnings`. Done via `build_current_library_hint_warnings()` (empty sweep when no library/crate — the mocked-plumbing and fallback paths). The bare-CLI / agent-CLI / builder-ops warning channels are a deferred follow-up (see `wip/engine-hints/deferred.md`).
- [x] Regenerate the two gates: error-identity snapshot (`make gei`) and error-reference docs pages (`make gep`). Outcome: no diff from either — `HintLintErrorType` members are enum values, not `PipelexError` subclasses; the corpus vocabulary DID regenerate (three excluded `error.hint_*` tags).
- [x] Lint unit tests (beside `test_validation_errors.py`): each warning fires with site attribution; a warned bundle is still valid; warned content survives into crate and descriptor. Home: `tests/unit/pipelex/pipeline/test_hint_warnings.py` + a warned-bundle-still-valid integration test in `test_protocol_validate.py`. Descriptor-survival half lands with Phase 4.

## Phase 4 — Descriptor population

- [ ] Narrow `InputFormField.hints` from `dict[str, Any]` to `dict[str, str]` (`pipelex/pipeline/input_form.py`) — flatness is contract.
- [ ] Plumb slot hints from the qualified crate: `build_input_form` keeps the qualified crate's `pipes` too; per slot name, the blueprint's `inputs` value is a string (no hints) or a slot table (hints). Open question 3: per-call `derive_slot` argument vs pipe-ref-keyed lookup — taste call, decide here; the invariant is that `StuffSpec` stays hint-free. Fallback path (no crate) derives with no hints.
- [ ] Concept nodes (`_blueprint_node`, `derive_concept`): stamp the concept's effective hints — deriver computes the chain merge via its existing `_refines_chain` walk calling the shared `merge_hints`. String-shorthand, natives, and class-backed concepts stamp nothing.
- [ ] Structure fields (`_structure_field`): `merge_hints([referenced concept's effective hints (concept-typed and concept-item fields only), field.hints])`, stamped via `model_copy(update=…)`.
- [ ] Input slots (`derive_slot`): `merge_hints([slot concept's effective hints, slot hints])`, stamped in the final `model_copy(update=…)` beside `presence`/`required`/`gating`.
- [ ] Plural slots and list fields: merged hints stamped on the `list` node AND its `item` descriptor (the `concept_ref` duplication precedent).
- [ ] Intent feeds kind — never competes: via `applicable_intent(...)`, on text-valued nodes `intent = "prose"` → `kind: "prose"`, `intent = "label"` → `kind: "text"`; absent/inapplicable/unknown intent leaves the no-hint default; `rating`/`quantity` never change `kind` and ride the slot; inapplicable words change nothing in `kind` but still ride the slot as preserved content.
- [ ] Extend the probe bundle under `tests/data/input_semantics/` with hinted fixtures.
- [ ] Deriver unit + integration tests (`tests/integration/pipelex/pipeline/test_input_form.py` kind table): site-over-concept and chain precedence visible on the wire; `prose`/`label` flip `kind` on text-valued nodes only; `rating`/`quantity` untouched-kind + slot ride; list/item duplication; hint-free descriptor output byte-identical to today.

## Checkpoint B — round trip end to end

- [ ] Authored hints visible in `hop5_input_form.json` via the trace harness (`pipelex-dev trace-input-semantics`) on the hinted corpus method. Same checkpoint protocol as A: update the design doc, verify cold-start readiness, commit.

## Phase 5 — Schema, corpus, docs, close

- [ ] Regenerate `derived/mthds_schema.json` (`make gms`), verify with `make cms`; if Taplo's `anyOf` disambiguation misbehaves on the slot union, hand-patch via the `_patch_construct_schema` precedent in `pipelex/language/mthds_schema_generator.py`.
- [ ] Corpus entry authoring hints at all three sites (`pipelex/test_extras/mthds_corpus/`); re-run `make generate-corpus-vocabulary`. This entry is the "one real method" the gate's round-trip proof runs on.
- [ ] Check the builder writer (`pipelex/builder/operations/concept_ops.py`): if preserving hints on rewrite is a one-liner, do it; otherwise file the follow-up (it sits beside the known E8 spelling bug in the same writer).
- [ ] Docs: `docs/under-the-hood/input-form-descriptor.md` — the stated no-hint kind rules (promote heuristics to specified rules), hints slot no longer reserved-only, drop the now-false "parser drops unknown keys" framing where it touches hints; document the three authoring sites and the lint in the language-facing blueprint docs.
- [ ] Changelog: record the feature under `## [Unreleased]`.
- [ ] Full gates: `make agent-check` + `make agent-test` green.
- [ ] Milestone close per workspace protocol:
  - [ ] Roadmap checkpoint in `../wip/devx/input-form-roadmap.md` with SHAs, including the gate-wording reconciliation (open question 2: engine-provable gate = wire-descriptor visibility; rendered-control half completes with M1/H3).
  - [ ] Workspace descriptor spec (`../docs/specs/mthds-input-form-descriptor.md`): reserved-hint-slot section from "reserved" to "populated"; kind-assignment section reflects the stated no-hint rules.
  - [ ] Conformance repo: hint-slot arm as a skip-gated skeleton (D2's de-gating pattern, arming at the release that ships H2); `make check-spec-links` in `conformance/`.
  - [ ] Inbox items (`../wip/inbox/`): the `mthds`-site "Specification Status" conformance-assertion update, and the `mthds-corpus-sync` / `mthds-schema-sync` runs that ride the next release.
  - [ ] H3 handoff note.

## Out of scope (do not do here)

E7 `extra="forbid"` on `ConceptStructureBlueprint` (S2); per-slot semantic keys (`description`, defaults, examples); hints on class-backed structures and natives; the crate spec's general absent-members-not-null canonicalization and step-5 materialization; kernel rendering (H3) and consumer wire-descriptor swap (M1).
