---
status: active
item: L-260902-10eb56
---

# Plan: `Anything` and `JSON` slots take what they declare, and the fallback refuses by name

Builds the rulings in `design.md` beside this file, except R9, which its own items carry. One `pipelex` pull request carries Phases 1 to 5, because the corpus generator's lapse rule fails the moment the shaper accepts the `Anything` template, so the fix and the retirement of its `EXPECTED_UNSHAPEABLE` entries cannot land apart. Phase 6 is the cross-repo half: the shared corpus re-committed in both mirrors together with their projections' `JSON` unwrap (R7), and `conformance`'s corpus census, all from the merged `dev`.

Branch `fix/Anything-slot-shaping`, worktree `_pipelex--anything-slot-shaping`. Work test-first: each phase writes its failing tests before the code.

## Phase 1 — every concept satisfies `native.Anything` (R2)

1. In `Concept.are_compatible_by_declaration` (`pipelex/core/concepts/concept.py`), after the two dynamic short-circuits, return `True` when `not concept_2.declares_a_structure_class`. Update the docstring's list of what the declaration tier decides.
2. Tests:
   - `tests/unit/pipelex/libraries/test_concept_library_compatibility.py::test_the_structureless_native_concept_is_answered_not_raised` pins `is_compatible(text, anything) is False`; rewrite it to pin the new rule both ways — `Text`, a user concept and `Dynamic` satisfy `Anything`, with and without `strict`, while `Anything` still does not satisfy `Text` — and keep its point that nothing is resolved from the registry.
   - A bundle-level test that a `PipeSequence` declaring `output = "Anything"` over a `Text`-producing last step validates. It fails today with `PipeSequence concept mismatch`. `tests/integration/pipelex/pipeline/test_protocol_validate.py` already holds the `Anything` input verdict test and is the natural home.
3. Sweep the `is_compatible` callers once more for a site whose wanted concept can be `Anything` and which relied on `False`. The design found only the shaper's two checks and `PipeSequence`'s output check.

## Phase 2 — the `ANYTHING` arm in the input shaper (R1, R3, R5)

All in `pipelex/core/memory/input_shaper.py` unless named otherwise.

1. Add `InputKind.ANYTHING`, `is_structured` `False`. Rewrite the `InputKind` docstring and the module docstring, which name `Anything` as a bottom-up fallback.
2. `resolve_input_kind`: return `ANYTHING` for a concept that does not declare a structure class, right after the `Dynamic` check and before the ordered natives.
3. `_shape_one`: `ANYTHING` joins the typed group, so it goes through `_shape_with_multiplicity` and the stuff is stamped with the declared concept.
4. `_build_item_content`: an `ANYTHING` arm implementing the R1 table, checked in this order — boolean before number, since `bool` is an `int`; `datetime.time`; `datetime.date` (which covers `datetime`); string; object; then a refusal through `_wrong_kind` for a nested list, a null item, an item whose keys are exactly `concept` and `content` (R10, with an `expected_kind` saying that one envelope around the whole list is how to type it) or any non-JSON object, with an `expected_kind` that says what an `Anything` item may be. The R10 check applies to an item of a bare list only: it takes a flag that step 6 clears when the list arrived inside an `Anything` envelope, whose content is raw at every depth. Each accepted value goes through `_make_content` with the matching native concept from the provider, so the injected-provider rule holds and a build failure is a `StructureValidationError`. The object row goes through a helper that Phase 3's `JSON` arm reuses: it takes the object literally, `{"json_obj": {…}}` included.
5. `_make_content` catches `ValidationError` and `StuffContentFactoryError` only, but `JSONContent`'s validator raises a bare `TypeError` for a Python dict holding a value that is not JSON (`JSONContent(json_obj={"a": object()})` → `TypeError: json_obj is not valid JSON`). Make that a typed refusal, preferably by fixing the validator to raise `ValueError` so pydantic reports it as a `ValidationError`; that covers the `Anything` object row, the `JSON` arm and the `JSON` envelope at once.
6. `_shape_explicit` (R5): when the value is a `{"concept", "content"}` envelope, resolve its concept through `concept_provider.get_required_entry_concept(…, search_scope=…)` first. If that concept declares no structure class: at an `Anything` slot, shape `content` as a bare value with step 4's R10 flag cleared, since an `Anything` envelope's content is raw at every depth (a `None` content raises `NullInputError`); at any other slot, raise `ExplicitConceptIncompatibleError` before building. Every other explicit form keeps today's path, and the D6 compatibility check now passes for typed envelopes by Phase 1. When the envelope's concept does not resolve, catch the provider's not-found error and fall through to today's path, so the factory reports it exactly as it does now. Cover the nested-envelope escape of the design's R5 with a test: an `Anything` envelope whose content is itself an object keyed `concept` and `content` shapes into a `JSONContent` holding that object.
7. `pipelex/pipe_machinery/rendering/input_renderer.py`: `InputKind.ANYTHING` joins the `DYNAMIC` arm of `_delighten_entry`, so the engine's light template keeps the envelope (see "What deliberately does not change" in the design).
8. Tests, in `tests/unit/pipelex/core/memory/input_shaper/`:
   - `test_scalar_arms.py`: `anything-str-bottom-up` pins the old `native.Text` result; replace it with one row per R1 value — string, integer, float, boolean, `{}`, a nested object, `{"json_obj": {…}}` taken literally, a TOML date, datetime and time — each asserting concept `native.Anything` and the exact content.
   - `test_multiplicity.py`: `Anything[]` with a mixed list, `[]`, a single value auto-wrapped, and `Anything[2]` with a wrong count; a list at a single `Anything` slot raising `ListWhereSingularError`; `[{"concept": "Image", "content": {…}}, "caption"]` raising `WrongScalarKindError` whose message says to wrap the whole list (R10).
   - `test_explicit_forms.py`: the `native.Anything` envelope in both spellings of the concept (`Anything`, `native.Anything`) over `{}`, a string, a number and a list at a plural slot; typed envelopes (`Text`, `JSON`, a user concept, `Image`) at an `Anything` slot keeping their concept; an `Anything` envelope at a `Text` slot raising `ExplicitConceptIncompatibleError`; an `Anything` envelope around a list whose item is keyed `concept` and `content`, at `Anything[]`, shaping that item into a `JSONContent` holding it (R10's escape).
   - `test_errors.py`: null envelope content, a null item, a nested list item, a non-JSON Python object, and the non-serializable dict of step 5 — each a typed `InputShapingError`, never a raw exception.
   - `test_provider_injection.py`: `resolve_input_kind` answers `ANYTHING` without resolving any class, on the stub provider that fails on class resolution.
   - `tests/unit/pipelex/pipe_machinery/rendering/test_input_renderer_light.py`: the light template for an `Anything` slot keeps the envelope.
   - Mutation-test the new arm once: break the boolean-before-number order, the D9 check and the R10 check, and watch the matching rows go red.

## Phase 3 — the `JSON` arm and the fallback's typed refusal (R7, R8)

1. Add `InputKind.JSON`, `is_structured` `False`, and `(NativeConceptCode.JSON, InputKind.JSON)` to the ordered natives of `resolve_input_kind`, so `native.JSON` and every concept refining it leave the fallback.
2. `_shape_one`: `JSON` joins the typed group.
3. `_build_item_content`, the `JSON` arm: every object goes through Phase 2's object helper, taken literally — `{"json_obj": {…}}` included, since R7 has no collision rule — and built with the *declared* concept so a refining class is honoured; an item of a bare list keyed exactly `concept` and `content` is refused as in the `Anything` arm (R10); anything else is `_wrong_kind` with "a JSON object".
4. `input_renderer._delighten_entry`: `InputKind.JSON` joins the scalar arm, whose `_unwrap_scalar_content` already turns a single-field content into its value, so the light template for a `JSON` slot is the bare object and for `JSON[]` a list of bare objects. Update both functions' docstrings, which list the scalar fields and say an out-of-matrix value keeps its envelope.
5. R8, in `_shape_one`'s `DYNAMIC` arm: catch `StuffFactoryError` from the bottom-up factory and raise a `StructureValidationError` from it, with the input name, the declared concept ref, the expected shape, and a reason the shaper writes from `_describe_value(value)`: this concept's slot reads a bare value by its own shape and has no reading for this one. The user action's detail names the fix on the author's side — declare the input as `JSON` or `JSON[]` for plain JSON data, or as a concept with a structure — and suggests no envelope. `StructureValidationError.make` hard-codes its detail, so give it an optional one or add a sibling classmethod on the same class; either keeps the error identity. The factory's message stays on the chain only, so no `typing.Union[…]` reaches a caller. Widen `StructureValidationError`'s docstring (`pipelex/core/memory/exceptions.py`) to cover a value the fallback has no reading for. If the generated error page is built from that docstring, regenerate it with `pipelex-dev generate-error-pages` and review the diff; `generate-error-identity` should report no change, since no class is added or renamed.
6. Tests:
   - `test_scalar_arms.py`: `JSON` rows — `{"a": 1}`, `{}`, a nested object, and `{"json_obj": {"a": 1}}` taken literally into `JSONContent(json_obj={"json_obj": {"a": 1}})` — and a concept refining `JSON` built through its own class; a string, a number and a boolean raising `WrongScalarKindError`. The string row pins the behaviour change: it used to become `native.Text`.
   - `test_multiplicity.py`: `JSON[]` with the report's value `[{"a": 1}, {"b": 2}]`, a single object wrapped, `[]`, a list at a single `JSON` slot raising `ListWhereSingularError`, an array item refused, an envelope-shaped item refused (R10).
   - `test_explicit_forms.py`: the `JSON` envelope with `{"json_obj": …}` content unchanged; a `JSON` envelope around a list of content forms at `JSON[]`, one of them holding an object keyed `concept` and `content` (R10's escape). If the bottom-up factory cannot build a list inside a `JSON` envelope, record it here and decide at Checkpoint 1 whether R10's `JSON[]` escape needs the fix or a different spelling.
   - `test_errors.py`: R8 at `Dynamic`, `Dynamic[]`, `Composite[]`, `Html[]`, `TextAndImages[]`, `SearchResult[]` and `Page[]` — a `StructureValidationError` whose message names the input and its concept, whose `error_domain` is `input`, whose `__cause__` is the factory's `StuffFactoryError`, whose text holds no `typing.Union`, and whose user action names `JSON[]` and no envelope.
   - **The report's regression test**: one parametrized test sending `[{"a": 1}, {"b": 2}]` to every slot kind the design measured — accepted at `Anything[]`, `JSON[]` and a structured user concept's list, `ListWhereSingularError` at `Anything` and `JSON`, `StructureValidationError` everywhere else — so a `StuffFactoryError` can never again reach a caller from this path.
   - `test_input_renderer_light.py`: the light template for a `JSON` slot is the bare object, for `JSON[]` a list of bare objects, and each shapes back through the shaper into the same content as the explicit template.

**Checkpoint 1** — `make agent-check` clean, the shaper suite and the compatibility suite green, and both probe matrices of `design.md` — the `Anything` matrix and the list-of-objects one — re-run, with every row either accepted as the rulings say or refused with a typed error. Record here what was measured and anything decided on the way, then `/rev`.

*Reached, 2026-09-27.* `make agent-check` is clean and the unit suite is green but for the four projection-corpus tests, which fail on the `JSON` unwrap until Phase 5 changes the reference projection. Both matrices were re-run through `shape_inputs` against a probe bundle, and every row lands as ruled:

```
== carry (anything_in)
  bare {} / string / 3 / 4.2 / true / {"a": 1} / a TOML date   OK  native.Anything, JSONContent / TextContent / NumberContent / YesNoContent / JSONContent / DateContent
  bare list, envelope list                                      REFUSED ListWhereSingularError
  envelope {} / str / num                                       OK  native.Anything, the same contents as bare
  envelope Text / native.JSON / Question                        OK  each keeps its own concept
== carry_list (items)
  bare [{}] / ["a"] / [1, 2] / [] / envelope [{}]               OK  native.Anything, ListContent of the natural contents
== [{"a": 1}, {"b": 2}] per slot
  Anything, JSON                                                REFUSED ListWhereSingularError
  Anything[], JSON[], Record[]                                  OK
  Dynamic, Dynamic[], Composite[], Html[], TextAndImages[], SearchResult[], Page[]
                                                                REFUSED StructureValidationError "Input 'x' could not be built as 'native.<X>': you provided a list of 2 item(s), …"
== JSON slot
  "hi", 3                                                       REFUSED WrongScalarKindError "expects a JSON object"
  {"a": 1}, {"json_obj": {"a": 1}}                              OK  JSONContent holding the object literally
```

Decided on the way:

- **R5's "any other slot" is read through compatibility.** The shaper asks `is_compatible(Anything, declared)` rather than whether the slot is `Anything`, so an `Anything` envelope is also honoured at a `Dynamic` slot, which it satisfies by the dynamic short-circuit, and keeps its concept there (D6, explicit wins when compatible). Everywhere else it is `ExplicitConceptIncompatibleError`, as ruled. A `DictStuff` naming a structureless concept takes the same path as the plain envelope.
- **R10's check sits in `_shape_list`**, not in the item arm: only a list's items can be envelope-shaped bare values, since a top-level one is an envelope by D6. The flag that clears it inside an `Anything` envelope is `is_raw_data`, threaded through `_shape_with_multiplicity`.
- **R10's `JSON[]` escape needs no fix**: a `JSON` envelope around a list of content forms builds through the bottom-up factory's Case 2.6 unchanged, pinned by `test_json_envelope_around_a_list_of_content_forms_is_r10s_escape`.
- **`_make_content` reports the declared concept** in a `StructureValidationError`, since the `Anything` arm builds through a native concept's class. The `JSONContent` validator raises `ValueError` now, and the three `test_json_content_validation.py` tests that pinned the raw `TypeError` pin a `ValidationError`.
- **R8's refusal is `StructureValidationError.make_for_unreadable_bare_value`**, a sibling of `make`, so the error identity is unchanged.
- **Mutation-tested**: putting the number check before the boolean one, dropping the null-content check, dropping the R10 check and ignoring its escape flag each turn the matching rows red.

## Phase 4 — the published schema excludes array and null (R4)

1. `Concept.render_structureless_representation`, SCHEMA arm: add `"not": {"type": ["array", "null"]}` to the element schema. The multiplicity wrapper is unchanged, so `Anything[]` items carry it.
2. Tests: `tests/integration/pipelex/pipeline/test_pipe_io_contracts.py` pins the `Anything`, `Anything[]` and `Anything[2]` schemas; `tests/unit/pipelex/core/pipes/test_stuff_spec.py` pins the structureless render. Add a check that validates the design's accepted and refused values against the rendered schema with `jsonschema`, so the contract and the shaper are shown to agree rather than asserted to.

## Phase 5 — the corpus and the docs

1. `pipelex/cli/dev_cli/commands/generate_projection_corpus_cmd.py`: delete the two `L-260902-10eb56` entries from `EXPECTED_UNSHAPEABLE`, and rewrite the comment above it so it describes the one gap still declared, `L-260830-191719`.
2. `tests/data/input_semantics/scaffold_bundle.mthds`: fold `anything_in = "Anything"` back into `scaffold_open_natives` (inputs and template), delete `scaffold_anything_slot`, and rewrite the comments above both so they describe the four open natives as they now are (design, question 3).
3. `pipelex/cli/dev_cli/commands/projection_reference.py`: remove `JSON` from `OUT_OF_MATRIX_NATIVES` and give a `JSON` slot a compact unwrap of `json_obj`, keyed on the native's identity the way the set already is, since its descriptor node is an `object` and `keeps_envelope` answers `True` for every native object node. Reword the set's comment, which says an input shaper cannot build these natives top-down, to the reason in the design's "What deliberately does not change".
4. Regenerate into a scratch directory with the four-bundle command from `docs/contribute/generate-projection-corpus.md`, in the order it gives, and read the result: no `input_semantics_scaffold` template declared unshapeable, the divergence classes and their site counts unchanged, `json_in`'s compact template the bare object in both formats with the engine and the reference agreeing, and the `anything_in` contract carrying the Phase 4 schema. Record the summary line (pipes, divergences, templates shaping cleanly) here, because the Phase 6 items check their own regeneration against it.
5. Update the tests that read the scaffold: `tests/integration/pipelex/pipeline/test_input_form.py` where the scaffold's pipes changed, and `tests/unit/pipelex/cli/dev_cli/test_generate_projection_corpus.py`, which compares the manifest's unshapeable list with `EXPECTED_UNSHAPEABLE` and follows by itself.
6. Docs, each describing the current behaviour with no history:
   - `docs/under-the-hood/pipe-io-contracts.md`, the `native.Anything` section: drop the paragraph saying the shaper has to catch up, and state what the schema admits.
   - `docs/building-methods/pipes/provide-inputs.md`: the admonition that groups `Anything` and `JSON` with the natives read by their own shape. Give each its own sentences — `Anything` takes any JSON value into its natural content and keeps its concept, a typed envelope keeps its own; `JSON` takes a JSON object as it is, or, as `JSON[]`, a list of them, and its template shows the bare object — and say that an item shaped like an envelope is refused in a bare list, and that for the natives still read by their own shape, a value with no reading is refused naming the input and the declaration to change.
   - `docs/building-methods/concepts/native-concepts.md`: the choice among the untyped concepts, in R11's order, as its own section ahead of the per-concept structures — naming the JSON by refining `JSON` first, with a worked `refines = "JSON"` concept taking a plain object as input. The `Anything` section says it is "primarily used as semantic markers"; say what an `Anything` input takes and what an `Anything` output means. The `JSONContent` section says what a `JSON` input takes, and that `JSON` is a JSON object, not any JSON value.
   - `docs/building-methods/concepts/refining-concepts.md`: a pointer to that section, since refining `JSON` is the pattern it recommends for data a developer already has.
   - `docs/errors/structure-validation-error.md`: the case of a value the fallback has no reading for, with changing the input's declaration as the fix.
   - `docs/contribute/generate-projection-corpus.md`: the paragraph on `native.Anything` sitting alone in `scaffold_anything_slot`.
   - `CHANGELOG.md`, under the unreleased section. *Fixed*: the values and typed envelopes an `Anything` slot now accepts, its multiplicity, the `PipeSequence` output; objects and lists of objects at a `JSON` slot; the fallback's refusal now a typed input error naming the input. *Changed*: a bare string at an `Anything` slot now produces a `native.Anything` stuff; a bare string at a `JSON` slot is now refused instead of becoming `native.Text`; the compact inputs template for a `JSON` slot is the bare object; an envelope-shaped item of a bare `Anything[]` or `JSON[]` list is refused; the fallback's refusal carries a new `error_type` and names the declaration to change; and the schema, if Phase 4 ran.
7. `make agent-check`, including `make drift-check`; follow `docs/contribute/drift-contracts.md` for any contract it opens. Then `make agent-test`, and `make test-ts-gates` only if Phase 4 changed anything the TypeScript gates read.

**Checkpoint 2** — the full suite green, the corpus summary recorded, the docs and changelog written. `/rev`, then the pull request: title `fix/Anything-slot-shaping · L-260902-10eb56`, body ending `Closes L-260902-10eb56`. Tell the reviewers that the fold deletes one pipe's files from both mirrors on purpose, and that `conformance`'s census (`tests/mthds/fixtures/protocol_corpus_census.json`, which L-260902-e62273 added) is edited to match in Phase 6.

## Phase 6 — the mirrors' projections, the shared corpus and the census

When the pull request opens, file three items the way L-260902-543ad0 filed its two, each `--blocked-by L-260902-10eb56`:

- **`mthds-js`** and **`mthds-python`**, each carrying the Checkpoint 2 summary and the exact regeneration command. Each changes its projection before re-committing the corpus — `src/protocol/inputs_template.ts` and `mthds/protocol/inputs_template.py` respectively: `JSON` leaves `OUT_OF_MATRIX_NATIVES`, a `JSON` slot's compact value is its `json_obj` unwrapped (the phase 5 reference projection is the model), and the set's comment takes the reword. Without the projection change, each repo's own harness fails its byte parity with the new capture.
- **`conformance`**: remove `input_semantics_scaffold.scaffold_anything_slot` from `tests/mthds/fixtures/protocol_corpus_census.json`, since the census is checked as an equality and the fold removes that pipe.

After the merge, each mirror is regenerated from a merged `pipelex` `dev` with the `projection-corpus-update` skill, on a branch cut from the mirror's `dev`, and the three pull requests merge together, or `conformance`'s fixture-drift and census checks go red for everyone.

**Checkpoint 3** — both mirrors carry the new capture and projection, the census matches it, L-260902-10eb56 is landed with `/ledger-land`, and this document and `design.md` flip to `landed`.

## Handoff — design session, 2026-09-27

**Done.** The bug is verified and both documents are written; no code has changed. `design.md` carries the two measured matrices (the `Anything` slot on `dev` at `be796a0d8`, and the list-of-objects report plus the `JSON` slot on `dev` at `d93a24767`) and rulings R1 to R8. The scope widened once, on Louis's go-ahead, from the `Anything` slot alone to R7 (a `JSON` handler) and R8 (the fallback's typed refusal), after a report of a list of plain JSON objects hitting `input_shaper.py:188` → `stuff_factory.py:454` at an unnamed slot. The probe scripts that produced the matrices are not kept; the matrices in `design.md` are the record, and Checkpoint 1 re-runs them against the fix.

**Open at the time, and answered since (see the ratification below).** Open questions 1 and 3 at the end of `design.md`: R4 (narrow the `Anything` schema by D2 and D9) and folding `anything_in` back into `scaffold_open_natives`. Each carries a recommendation; the documents flip from `draft` to `active` when Louis ratifies them, in the same change that records his answers here. Question 4, whether `JSON` should hold any JSON value, belongs to the standard (L-260927-a8ec06) and blocks nothing here.

## Handoff — review of the rulings, 2026-09-27

A second session reviewed the design from two sides, what keeps the language clear to non-technical readers and agents, and what a developer holding plain JSON needs, and Louis agreed with every change it proposed. No code has changed. The changes are:

- **R7 has no collision rule** (open question 2, now decided). `JSON`'s compact template becomes the bare object in the engine, the reference projection and both mirrors, so no caller learns the `json_obj` wrapper, and every bare object is read literally. This grows Phase 3 (the light template), Phase 5 (the reference projection) and Phase 6, whose mirror items now change projection code rather than only re-committing the corpus.
- **R8's refusal names the declaration to change** (`JSON`, `JSON[]`, or a concept with a structure) and no longer suggests an envelope, because at a `Dynamic` slot the obvious one drops the object's content (L-260927-bea35e).
- **R10, new**: an envelope-shaped item of a bare `Anything[]` or `JSON[]` list is refused, which D6's top-level-only collision rule would otherwise have let through as JSON.
- **R11, new**: the docs teach one choice among `Anything`, `JSON` and `Dynamic`, leading with naming the JSON through a concept refining `JSON`.
- **R9, new and built elsewhere**: on the output side, an `Anything` stuff's content goes on the public wire as its plain JSON value. Measured, it goes out as its content class's fields today (`{"text": "hi"}`), so once R1 lands a value chained through `--with-memory` changes type. L-260927-da1b09 (`pipelex`) and L-260927-223013 (`mthds`) carry it.
- **A correction to the first review.** The published `json_schema` and codegen's `JSON` type describe the content form for every native (`Text`'s is `{"text": …}`), so neither is a `JSON`-specific defect and neither changes.
- **A stale claim in Checkpoint 2, fixed.** `conformance` pins a corpus census as an equality since L-260902-e62273 closed, so the fold of `scaffold_anything_slot` needs a census edit; Phase 6 now files a `conformance` item beside the two mirrors.

**Ratified, 2026-09-27.** Louis answered every open question of `design.md` and the choices this review had made on its own, each as recommended: R4 narrows the `Anything` schema, so Phase 4 is built unconditionally; `anything_in` folds back into `scaffold_open_natives`; `JSON` stays an object, recorded and closed on L-260927-a8ec06; `Anything`'s compact template keeps its envelope; the content of an `Anything` envelope is raw data at every depth, list items included, which is R10's escape; and R11 advises against `Dynamic` for inputs while L-260927-bea35e is open. Both documents are `active` from this change. One point is left to measurement rather than decision: R10's escape for `JSON[]`, a `JSON` envelope around a list, which Phase 3 tests and Checkpoint 1 decides if the factory cannot build it.

**Next, done since.** `dev` was merged into the branch after the ratification, bringing it to the v0.67.1 release and the `mthds` 0.17.0 pin, and the build session below claimed the item and started Phase 1.

## Handoff — build session, 2026-09-27

**Done.** Phases 1 to 3 are built, tested and committed as "Shape Anything and JSON slots top-down, and refuse the fallback by name", and Checkpoint 1's probe is recorded above. The four tests of `tests/unit/pipelex/cli/dev_cli/test_generate_projection_corpus.py` are expected to fail until Phase 5, with `Undeclared divergence class(es) ['engine-only-field']`, because the engine's `JSON` template is unwrapped while the reference projection is not yet.

**Checkpoint 1's `/rev` ran but is not triaged** (the triage is recorded in the next section). Profile 4, round 1, bar `open`, fix mode `ask`, on the branch against `origin/dev` at the commit named above. All four reviewers returned (cubic, Codex's review and adversarial runs, and the bundled `code-review` at `medium`, whose provenance matched the worktree, the commit and the diff's files). The session stopped at its context threshold before verifying anything, so no finding below has been verified, fixed or rejected, and no `ledger review-pass` is recorded. The merged findings, with the reviewers who raised each:

1. **Transport round-trip of a single `Anything` value** (Codex adversarial, high, `input_shaper.py` `_build_anything_content`). An `Anything` stuff holding a `TextContent`, sent through `dump_for_transport()` then `hydrate_working_memory()`, is reported to raise `PipeJobError: Class 'AnythingContent' not found in registry`, because the singular dump does not keep the concrete content class and hydration resolves the class from the declared concept. Verify with that exact round trip first. If real, it is a critical at every bar (a distributed run loses the input), and it touches R6 (no `AnythingContent` class ever) and R9 (L-260927-da1b09), so the fix is hydration reading the concrete class rather than a new class.
2. **An envelope can escape the declared multiplicity** (three reviewers, three cases, `input_shaper.py` `_try_shape_structureless_envelope` and `_reconcile_explicit_multiplicity`):
   - `code-review`: an `Anything` envelope whose content is a prebuilt `ListContent` becomes `ListContent(items=[ListContent(...)])` at `Anything[]`, and a bare `ListContent` at a single `Anything` slot, because `_shape_list` treats a non-`list` value as one item. Reproduced by the reviewer's probe.
   - Codex adversarial: a typed envelope `{"concept": "native.Text", "content": "hello"}` at `Anything[]` stores a scalar `TextContent`, since reconciliation returns early when the content is not a `ListContent`, and `Anything[N]` counts are not checked. Check whether a `Text` envelope at `Text[]` does the same on `dev`; if so the hole predates this branch but is widened by it.
   - cubic: at a singular `Dynamic` slot, `{"concept": "native.Anything", "content": [1, 2]}` raises `ListWhereSingularError` while `{"concept": "Text", "content": ["a", "b"]}` is accepted, because the structureless path peels multiplicity where `_shape_explicit` deliberately skips it for `Dynamic`. Decide one behaviour for both.
3. **R8's refusal is too broad and its advice too narrow** (`code-review`, cubic; `input_shaper.py` `DYNAMIC` arm, `exceptions.py` `make_for_unreadable_bare_value`). It rewrites every `StuffFactoryError` from the fallback, so a list of an unregistered `StructuredContent` (`[Zork(), Zork()]` at a `Dynamic` slot) reports "no reading for this one" and hides that no concept `Zork` is registered, as does a mixed list of prebuilt contents or `[]` at `Html[]`. And it always advises `JSON` or `JSON[]`, which refuses a scalar too (`3` at a `Dynamic` slot). Reword only the no-reading cases, keep the factory's reason otherwise, and advise by the value's shape: a scalar towards `Anything` or its native, an object or a list of objects towards `JSON` or `JSON[]`.
4. **The published `Anything` schema admits array and null** (both Codex runs). This is Phase 4, planned; the adversarial run adds that `Anything[]` items must carry the exclusion too, which Phase 4's step 1 already says.
5. **The corpus gate, the stale docs and the missing changelog entry** (Codex review twice, cubic). This is Phase 5, planned.
6. **Test layout** (cubic, P3): `test_explicit_forms.py` now holds three test classes and `test_errors.py` two, and the new classes carry docstrings, against the repo's testing rules. Move `TestInputShaperAnythingEnvelopes`, `TestInputShaperJSONEnvelopes` and `TestInputShaperFallbackRefusal` into their own modules, as `test_list_of_objects_report.py` already is, and drop the class docstrings.

**Next, done since.** The triage below verified findings 1 to 3, fixed what survived and recorded the pass before Phase 4 started.

Read for Phases 4 and 5 while the reviewers ran, so none of it needs re-deriving:

- **Phase 4** also moves `test_anything_input_produces_a_verdict` in `tests/integration/pipelex/pipeline/test_protocol_validate.py`, which pins `set(anything_schema) == {"title", "description"}`, and `tests/integration/pipelex/cli/test_trace_input_semantics_cmd.py`, besides the two files step 2 names.
- **Phase 5, the reference projection**: in `projection_reference.py`, `keeps_envelope` answers `code in OUT_OF_MATRIX_NATIVES or node.kind is FieldKind.OBJECT`, so the `JSON` code has to answer `False` ahead of the object test, and `_light_value` has to unwrap `json_obj` for a node whose native code is `JSON`.
- **Phase 5, the divergence collector**: `_engine_dict_placeholder(path)` in `generate_projection_corpus_cmd.py` keys its placeholder by `path[-1]`, which at a compact `JSON` position is the slot name or a list index rather than `json_obj`. Give the collector the exact `JSON` positions from the descriptor, the way `register_fixed_counts` receives the fixed counts, use them in the `unknown-empty-object` arm, and update `tests/unit/pipelex/cli/dev_cli/test_projection_divergence_gate.py` to match. The site counts should not move; the example paths will.
- **Phase 5, the error page**: `docs/errors/structure-validation-error.md` is generated, so the new case means converting it to an authored page (`<!-- pipelex:authored -->`, modelled on `docs/errors/model-not-found-error.md`) and running `generate-error-pages` and `generate-error-identity`, which should show no identity change.

## Checkpoint 1's review, triaged — 2026-09-27

The same session resumed after a compaction and triaged the findings above, with one verifier subagent reproducing findings 1 to 3 on the branch and, through `git archive origin/dev`, on `dev`. Every fix below was mutation-tested: removing it turns its test red.

- **1, transport: confirmed and fixed.** The defect predates the branch (a hand-built `native.Anything` stuff fails the same way on `dev`), but R1 made every single `Anything` input reach it. `WorkingMemory.dump_for_transport` now stamps the class markers on the single content of a structureless concept, as it does on list items, and `hydrate_content` rebuilds that content from them. R9's premise, that internal serialization keeps content classes, holds again.
- **2a, a prebuilt list in an `Anything` envelope: confirmed and fixed.** The envelope's `ListContent` is read as the list of its items, and a `ListContent` as an item is refused as a wrong kind, which also closes the same nesting at `Text[]` that predates the branch.
- **2b, a typed singular envelope at a plural slot: predates the branch.** The `[N]` half is fixed, since a single value is never N items: `_reconcile_explicit_multiplicity` raises `MultiplicityCountMismatchError`. Whether a singular under `[]` is wrapped stays with Gap A in `wip/inputs/input-shaper-multiplicity-gaps.md`.
- **2c, an `Anything` envelope at a `Dynamic` slot: confirmed and fixed.** It takes list or single from its content, as `_shape_explicit` does for every other envelope there.
- **3, the fallback's refusal: confirmed and fixed.** An empty list, or a list holding prebuilt contents, keeps the factory's own reason through `StructureValidationError.make`; every other value gets `make_for_unreadable_bare_value`, whose advice now names the declaration that reads it: `JSON` for an object, `JSON[]` for a list of objects, `Anything` or `Anything[]` otherwise.
- **4 and 5** were Phases 4 and 5, built next. **6, the test layout**, is fixed: each new test class has its own module, with no class or module docstring.

## Checkpoint 2 — reached, 2026-09-27

Phases 4 and 5 are built. The corpus regenerated with the four-bundle command reads: 16 pipes and 32 templates, 28 shaping cleanly and 4 declared unshapeable, all under L-260830-191719; divergences `file-leaf-not-expanded` 6, `fixed-count-honoured` 4, `object-native-keeps-envelope` 1, `optional-field-included` 167, `text-named-url` 6, `unknown-empty-object` 2, the same site counts as the committed capture. The compact `unknown-empty-object` example moved from `json_in.content.json_obj` to `json_in`, `json_in`'s compact template is `{}` in both formats, `anything_in` keeps its envelope and round-trips, and its contract carries the Phase 4 schema.

Decided on the way:

- **The divergence collector learns where a compact `JSON` slot unwraps** from the descriptor, through `register_json_unwraps`, as it learns fixed counts, because the engine's dict placeholder is keyed by the field holding the dict (`json_obj`) and the walk's path no longer names it there. An unregistered slot-level placeholder is refused, which a test pins.
- **The schema and the shaper are shown to agree** by `test_anything_schema_agreement.py`, which validates every JSON type at `Anything`, `Anything[]` and `Anything[2]` against both, rather than asserting the schema's keys.
- **`docs/errors/structure-validation-error.md` is an authored page now**, and the error identity did not change.
- **The docs' `Order` example** (a concept refining `JSON`, singly and as `Order[]`) was probed through `validate_bundle` and `shape_inputs` before it was written down.

## Checkpoint 2's review, triaged — 2026-09-27

`/rev` at profile 4, round 2, bar `defects`, on the branch against `origin/dev` at the commit "Fix the Checkpoint 1 review findings, narrow the Anything schema, and land the corpus and docs". All four reviewers returned: cubic, Codex's review and adversarial runs, and the bundled `code-review` at `medium`, whose provenance matched the worktree, the commit and the diff's files. Every fix below was mutation-tested.

- **A composite under `Anything` loses its components across transport** (`code-review`): fixed. `_hydrate_list_item` rebuilds a composite's components from their own markers at any depth, which also closes the nested-composite gap `wip/nested-composite-hydration-not-recursive.md` recorded, so that note is gone.
- **The delivery cannot hydrate an `Anything` main stuff** (cubic, outside the diff but made visible by it): fixed. `try_local_hydrate_stuff` looked the concept's class up in the registry first, which a structureless concept never has, so the result files fell back to a raw dump that now showed the class markers.
- **The fallback advises `Anything[]` for lists it refuses** (cubic, Codex review): fixed. A list holding nulls or nested lists gets no suggested declaration and keeps the factory's reason.
- **A prebuilt `ListContent` mixing kinds is refused at `Anything[]`** (cubic): fixed. It is read as the bare list of its items, as inside an `Anything` envelope.
- **NaN and the infinities** (Codex review): fixed at `Number` and `Anything` inputs, which refuse them as numbers JSON cannot hold.
- **The changelog and the error page** (cubic): the chaining change through `--with-memory` is now a Breaking entry and a caveat in `provide-inputs.md`, the `JSONContent` entry names the case that actually changed (a value JSON cannot encode), and the error page no longer calls the container natives structureless.
- **This plan's stale "Next" blocks and a local path** (cubic): the handoffs' next steps are marked done and the paths are gone.
- **Chaining an `Anything` value through `--with-memory` changes its type** (Codex adversarial, high): deferred as ruled. It is R9, which `design.md` keeps out of this branch because it changes the run result and what every consumer displays; L-260927-da1b09 carries it with its round-trip test, blocked by this item.
- **A typed singular envelope at `Anything[]` is stored unwrapped** (Codex adversarial, medium): deferred to Gap A's auto-wrap question, recorded in `wip/inputs/input-shaper-multiplicity-gaps.md`.
- **A TOML date inside an object at a `JSON` or `Anything` input is refused** (cubic): deferred below. The refusal is typed and names the input; whether a date inside an object should become its ISO string is a reading of its own.

**Next.** Record the round, open the pull request, file Phase 6's three items, then land with `/ledger-land`.

## Ledger

- L-260902-10eb56 is claimed from the worktree; `ledger claim L-260902-10eb56 --renew` at the start of each session.
- Ruled on here but not built: L-260902-9546ef, L-260926-f7bb28 (now linked to it) and L-260902-db6d1e keep their own fix directions under the design's R6.
- Filed from this design: L-260927-bea35e (`pipelex`, the `Dynamic` envelope data loss, now also carrying the list half of the report) and L-260927-afaf62 (`mthds`, the runtime guide's compatibility pseudo-code).
- Filed from the review: L-260927-da1b09 (`pipelex`, R9's runtime half, blocked by this item) and L-260927-223013 (`mthds`, R9's wording in the standard); L-260927-a8ec06 (`mthds`, question 4, decided and closed: `JSON` stays an object); L-260927-702c56 (`pipelex`, a JSON file reference into `JSON[]`, blocked by this item).
- Not touched: L-260831-1e1a71 owns the explicit arm's untyped escapes, which R8 deliberately leaves alone.

## Deferred

- **What a `Dynamic` slot holds.** Gap B of `wip/inputs/input-shaper-multiplicity-gaps.md` stays open for `native.Dynamic`, and a bare object or a list of objects there is refused, typed but refused. Both belong to L-260927-bea35e, which has to rule on what a `Dynamic` slot holds anyway.
- **Top-down handlers for `Composite`, `Html`, `Page`, `TextAndImages` and `SearchResult`.** They stay on the fallback, refusing by name under R8 and taking an envelope. None has been reported, and each needs its own reading of a bare value.
- **Codegen's `unknown` for an `Anything` slot** admits an array and a null that R4 excludes. A structureless concept is a declared imprecision in codegen, so it is left as is unless a consumer asks.
- **The output side of an `Anything` value (R9)** is L-260927-da1b09 and L-260927-223013, with the round-trip test.
- **A JSON file reference into `JSON[]`**, the way D11 reads a CSV into a structured list, is L-260927-702c56.
- **Per-item envelopes in a list**, for every kind, would be a feature of their own; R10 refuses the spelling rather than read it for two kinds only.
- **A TOML date inside an object** at a `JSON` or `Anything` input is refused as a value JSON cannot hold, though the same date at the top of an `Anything` input is read. Converting it to its ISO string would be a reading of its own, left until a caller asks.
