# D2 — Input-form descriptor: reference derivation + report carriage

Implements `/Users/lchoquel/repos/Pipelex/wip/inbox/2026-08-22-pipelex-d2-input-form-descriptor-derivation.md` on the stacked branch `feature/Input-semantics-D2` (program branch `feature/Input-semantics`; no PR to `dev`, per the program's branch ruling).

**Contract:** `docs/specs/mthds-input-form-descriptor.md` (workspace root) — every section. **Gate:** the skip-gated skeletons in `conformance/tests/pipelex_api/test_validate_input_form.py` de-gated and green against the booted sibling `pipelex-api`, plus the per-kind assignment coverage. The two live absent-by-default tests must keep passing untouched. The de-gating itself rides the `pipelex-api` inbox item (Phase 6) because the sibling boots a **pinned PyPI runtime** — this repo's deliverable is the derivation, the report carriage, the pinned assignment table, and the follow-up filings.

## Settled design decisions (read before implementing)

- **Derivation input = loaded pipes + the qualified (NOT normalized) crate.** The slot key space and slot list come from the loaded pipes (`result.pipes` → `pipe.inputs.root` `StuffSpec`s), guaranteeing key-set equality with `pipe_io_contracts` by construction (same iteration, including `PipeSignature` placeholders and controller-inferred inputs). Concept facts (description, `refines`, structure fields) come from a crate built as `qualify_crate(LibraryCrateFactory.make_from_blueprints(result.blueprints))` — **not** `normalize_crate`, because normalization flattens in-crate refinement and drops the `refines` links the descriptor must report as a chain (`crate_normalization.py` step 3 vs spec's `refines` slot). Never read the emitted JSON Schema (the whole point — the E1/E2/E3/E4 losses live downstream of the blueprint).
- **Fact sources per node:** authored concepts → their `ConceptBlueprint.structure` (`ConceptStructureBlueprint` retains `default_value`, `choices`, `required`, descriptions, `concept_ref`/`item_concept_ref` — everything the schema loses); natives → `materialize_native_concept` pinned blueprints; class-backed concepts (`structure = "ClassName"`) → class-registry reflection (generalize the faithful-or-absent approach of `codegen/native_expansion.reflect_native_structure`), falling back to `kind: "unknown"` when unmappable. A pipe slot whose concept is absent from the crate (e.g. loaded from `library_dirs`) still gets a descriptor: slot facts from the loaded `StuffSpec`, concept payload via natives/reflection/`unknown`.
- **Slot facts from `StuffSpec`:** `presence: PresenceMarker` is already the spec's exact three-valued wire vocabulary (`plain`/`optional`/`force`) — reuse it. `multiplicity: VariableMultiplicity | None` keeps the fixed `[N]` int (E4's fact) — `None` → single node, `True` → `list` (no `item_count`), int → `list` with `item_count`.
- **Derived booleans (in the deriver, per spec):** top-level `required = presence != optional`; `gating = required and not (kind == "list" and item_count is None)`. Fixed-count lists gate. Nested fields carry neither `presence` nor `gating`.
- **E3 honesty:** a field authored `required = true` **and** `default_value` reports both — read from the blueprint, so the hop-2 accident never enters. `default_value` emitted only when authored (never the emission's `null`-for-optional artifact).
- **E10:** `choices` always a list on the wire, even one member.
- **Report carriage:** `PipelexValidationReport.input_form: dict[str, PipeInputFormDescriptor]` as a **required** field, `build_validation_report(..., input_form=...)` as a **required** kwarg. No default — the pipelex-server worker path must fail loudly at its next pipelex bump (shared-assembly rule: populated everywhere or nowhere), fixed by its own inbox item. The report always carries it; absence-by-default on the HTTP wire is the route's pop (the `rendered_markdown` precedent), which is `pipelex-api`'s item.
- **Wire absence of inapplicable slots:** the valid arm is dumped **without** `exclude_none`, so a flat model with `None`s would leak `"presence": null` everywhere. Give the field model a None-dropping `@model_serializer` (no slot legitimately carries JSON `null`: TOML cannot author a null default). Flat recursive model + per-kind validators, not a discriminated union — simpler, and D4 owns the TS types.
- **`title`: omitted in D2** (slot exists on the model; renderer falls back to `name` — never the mangled class name). H2 refines.
- **`description` for a flattened scalar:** the concept's authored description, else the payload field's. This is the E6 fix on the descriptor side: class-backed and native concepts get their blueprint/pinned description.
- **Cycle guard:** track the concept-ref path while recursing objects/lists; on revisit emit `unknown` (json_schema's `$ref`s keep the payload contract; the descriptor stays finite).
- **`refines` chain:** walk authored links immediate-parent-first to the end, qualified. A string-described / description-only concept reports `kind: "prose"` with `refines: ["native.Text"]` — this engine's stated fact (it generates a `TextContent` subclass and its `json_schema` is `{text}`), not shape invention.
- **Kind assignment table** (pinned by tests in Phase 3; chain-membership decides, never shape sniffing):
  - chain bottoms at / is `native.Text` (incl. string-promoted concepts) → `prose`; `native.Html` → `prose`; `native.Number` → `number` (`integer: false`); `native.YesNo` → `boolean`; `native.Date` → `date` (`datetime: false`); `native.Time` → `text` + `format: "time"`; `native.Document` → `document`; `native.Image` → `image`; `native.Page`, `native.TextAndImages`, `native.SearchResult` → `object` (pinned-blueprint fields); `native.Dynamic`, `native.Anything`, `native.JSON`, `native.Composite` → `unknown`.
  - structured concept → `object` (fields in declared order, recursing); nested field types: `text`→`text`, `integer`→`number`(`integer: true`), `number`→`number`, `boolean`→`boolean`, `date`→`date`(`datetime: false`), `datetime`→`date`(`datetime: true`), `time`→`text`+`format:"time"`, `choices` present → `enum` (choices win over `type`, matching the generator), `concept`→ recurse (with `concept_ref` — the E1 fact), `list`→`list` (item from `item_type`/`item_concept_ref`; inner `list` item → `unknown`), `dict`→`unknown`.
  - multi-field custom concept never flattens; flattening applies only via the native-chain rules above.
- **No new error class** — the derivation is total (`unknown` is the escape hatch); no `gei`/`gep` needed.
- **Keyword-only rule:** new functions keyword-only; if `build_input_form(pipes, ...)` keeps a positional subject, record the grant (`make sgr`) BEFORE running `make agent-check` (the auto-fixer silently keyword-onlys ungranted subjects).
- Rich ready-made fixture for tests: `tests/data/input_semantics/probe_bundle.mthds` (chains, class-backed, natives, defaults, single choice, `[N]`, `!`, `?`).

## Session state (updated 2026-08-22 — resume here after /compact or cold start)

**Done:** the plan below; the Phase 1 red tests are WRITTEN and deliberately failing (module `pipelex/pipeline/input_form.py` does not exist yet):

- `tests/integration/pipelex/pipeline/test_input_form.py` — derivation behavior against `tests/data/input_semantics/probe_bundle.mthds` + inline bundles, using the `load_empty_library` fixture / `_teardown_validation_library` pattern copied from `test_pipe_io_contracts.py`.
- `tests/unit/pipelex/pipeline/test_input_form_models.py` — per-kind validators + null-free serialization.

**Next action:** write `pipelex/pipeline/input_form.py` (models + `build_input_form(pipes, *, blueprints)`) per the decisions above, then run those two modules. Late-discovered facts a fresh session needs:

- Expected API (the tests pin it): `FieldKind` StrEnum, recursive `InputFormField`, `PipeInputFormDescriptor(fields=[...])`, `build_input_form(pipes, *, blueprints)` returning `dict[str, PipeInputFormDescriptor]`. The `datetime` wire slot is the Python attr `datetime_flag`; a custom `@model_serializer(mode="wrap")` drops `None` slots AND renames `datetime_flag` → `datetime` (an alias alone is NOT enough — the route dumps without `by_alias`).
- Crate plumbing: `LibraryCrateFactory.make_from_blueprints(list(blueprints))` then `qualify_crate(crate)` → `QualifiedCrateContent(concepts, pipes)` (NamedTuple, `pipelex/libraries/crate_qualification.py:57`). Walk `refines` chains over `qualified.concepts` (qualify_crate qualifies in-body refines); stop after a `native.*` link; cycle-guard with a seen-set.
- Natives: `materialize_native_concept(NativeConceptCode(...))` (`pipelex/codegen/native_expansion.py:41`) returns the pinned `ConceptBlueprint` (description + structure). `NativeConceptCode.structure_class_name` / `.concept_ref` / `.is_native_concept_ref_or_code(...)` exist (`pipelex/core/concepts/native/concept_native.py`).
- Class registry for class-backed reflection: `from pipelex.system.registries.class_registry_access import get_class_registry` (the import `concept_factory.py:23` uses; do NOT import `runtime_hub` from pipeline code).
- Multiplicity semantics (`variable_multiplicity.py:121`): `[]` → `True`, `[N]` → int N, none → `None`; presence `PresenceMarker` values are already the wire vocabulary. Mirror `is_multiple()` (`int > 1`) for list-ness so the descriptor never disagrees with the contract's array wrapping; `[1]` therefore renders as a single node — pin that in Phase 3.
- `StuffSpec` (`pipelex/core/pipes/stuff_spec/stuff_spec.py`): `.concept.concept_ref` (qualified), `.presence`, `.multiplicity`. Loaded `Concept` has `description`/`refines`/`structure_class_name` but NO structure fields — field facts come from blueprints/pinned natives/reflection only.
- Grant `build_input_form`'s positional `pipes` subject (`make sgr FUNC="pipelex/pipeline/input_form.py::build_input_form" RATIONALE=…`) BEFORE the first `make agent-check` (precedent: `build_pipe_io_contracts` at `subject_grants.toml:4587`; the auto-fixer silently rewrites ungranted subjects).
- Unverified assumption in the tests: a `PipeLLM` with no `inputs` key validates green (`_NO_INPUTS_MTHDS`); if not, swap that bundle for a `PipeSignature` + `allow_signatures=True`.

## Phase 1 — Wire models + derivation (`pipelex/pipeline/input_form.py`)

- [x] TDD red: derivation + model tests written (see Session state above; paths differ slightly from the original sketch — integration tests live in `tests/integration/pipelex/pipeline/test_input_form.py`, model tests in `tests/unit/pipelex/pipeline/test_input_form_models.py`): key set equals `build_pipe_io_contracts`'s; authored slot order preserved; presence three-valued (`!` ≠ plain — E5); `required`/`gating` incl. the divergence (plain scalar `gating: true` vs plain `Concept[]` `required: true, gating: false`) and `?` (`required: false, gating: false`); `[N]` → `item_count` + `gating: true` (E4); empty-inputs pipe → `{ "fields": [] }`; namespaced `concept_ref` on every concept node incl. nested (E1); `refines` chain walked to the end, absent when nothing refined (E2); E3 both-facts; single-member `choices` list (E10); serialization drops inapplicable slots (no `null`s in `model_dump(mode="json")`).
- [ ] Models: `FieldKind` StrEnum (closed union), recursive `InputFormField` (common slots + per-kind slots + reserved `examples`/`hints`), `PipeInputFormDescriptor` (`fields: list[InputFormField]`), all snake_case wire names per the spec's common-slots table (MTHDS-owned artifact — no `pipelex_` prefixes), None-dropping serializer, per-kind validators (`datetime` required on `date`, `choices` on `enum`, `fields` on `object`, `item` on `list`, `integer` on `number`).
- [ ] Deriver: `build_input_form(pipes, *, crate) -> dict[str, PipeInputFormDescriptor]` — one public function per the spec's shared-assembly rule; internals per the decisions above.
- [ ] Green + `make agent-check`.

## Phase 2 — Report carriage (both in-repo assembly points)

- [ ] `PipelexValidationReport.input_form` (required field, docstringed per house style) + required `input_form` kwarg on `build_validation_report`.
- [ ] `validate_in_process.py`: build the qualified crate and call `build_input_form` inside the library window, right beside `build_pipe_io_contracts` (the descriptor must be assembled before teardown for the same class-registry reason).
- [ ] Sweep other report producers/consumers in-repo: `tests/unit/pipelex/pipeline/test_validation_report.py`, `test_runner_validate_plumbing.py`, `test_direct_bundle_validator.py`, `test_protocol_validate.py`, the agent-CLI validate envelope, `format_validate_markdown` — update constructions; nothing renders the descriptor in Markdown (it is a structured view, not text).
- [ ] Integration assertion in `test_protocol_validate.py` (or a sibling): the in-process report carries `input_form` keyed like `pipe_io_contracts`.

**CP1 — commit:** models + derivation + carriage, suite green (`make agent-check`, targeted pytest). Update this file: status of Phases 1–2, decisions taken, open questions.

## Phase 3 — Pin the full kind-assignment table (pipelex tests)

- [ ] Extend the unit tests with the complete per-native ruling (every `NativeConceptCode` as a direct input → its kind above), string-promoted concept → `prose` + `refines: ["native.Text"]`, class-backed reflection (e.g. `structure = "TextContent"` → flattened `prose` carrying the concept description — E6) and the unmappable → `unknown` fallback, nested `dict`/inner-list → `unknown`, `datetime`/`time` formats, cycle guard.
- [ ] Pin whatever the parser does for `[1]` (an `is_multiple()` edge) in one test, reporting it as authored.
- [ ] Constraint slots: populate from reflected `FieldInfo` metadata where the engine states them (`Gt`/`Ge`/`Lt`/`Le`/`MinLen`/`MaxLen`/pattern → `exclusive_minimum` etc.); test on a registered class with a constrained field (the `ImageContent.width` precedent).

**CP2 — commit:** assignment table pinned; `make agent-check` + full `make agent-test` green. Update this file.

## Phase 4 — Conformance: per-kind coverage (sibling repo `conformance/`, own commit there)

- [ ] Add per-kind skeleton tests to `conformance/tests/pipelex_api/test_validate_input_form.py`, skip-gated with the same `SKELETON_REASON` (the sibling boots a pinned PyPI runtime that predates the derivation): one bundle exercising the assignment table end to end (prose/document/image/number/boolean/single-member-enum/object-with-nested-concept_ref/list-with-`[N]`-item_count/date/unknown-dict), asserting kinds, `refines` membership, `presence`, E3 both-facts, and no-`null` inapplicable slots.
- [ ] Do NOT touch the two live absent-by-default tests.
- [ ] `make check-spec-links` in `conformance/` (new tests join the already-linked module; verify nothing drifted). Follow that repo's branch/PR convention for the commit.

**CP3 — commit (in `conformance/`):** per-kind skeletons added, spec links green. Update this file.

## Phase 5 — Docs + changelog (this repo)

- [ ] New docs page documenting the descriptor derivation: where it lives, the fact sources, the kind-assignment table, the gating rule, pointer to the workspace spec as the contract. Link it from the docs nav where natural (MkDocs conventions: blank line before lists).
- [ ] `docs/contribute/trace-input-semantics.md` + harness: add the descriptor as a trace artifact (a hop beside `hop5_pipe_io_contracts.json`) so a mangled authored fact localizes into the new projection too — small, per the keep-useful-harnesses rule.
- [ ] `CHANGELOG.md` under `## [Unreleased]`: bold-label condensed entry (breaking: `build_validation_report` requires `input_form`; the report gains the field).

## Phase 6 — File the two cross-repo follow-ups (workspace `wip/inbox/`, from here `../wip/inbox/`)

- [ ] `YYYY-MM-DD-pipelex-api-validate-views-input-form.md` (use `_TEMPLATE.md`): add `views: list[str]` beside `render` with identical lenient mechanics (`validate.py:31/:59` precedent), resolve-then-attach-or-pop `input_form` on the valid arm only, regenerate the committed OpenAPI, bump the `pipelex` pin once released, then **de-gate the whole conformance module** (this closes D2's gate). Carry the evidence pointers (spec section, skeleton file/lines, this branch's derivation site).
- [ ] `YYYY-MM-DD-pipelex-server-worker-input-form-carriage.md`: carry `input_form` on `DryValidateResult` inside the library window (`act_dry_validate.py:52`) and hand it to `build_validation_report` (`temporal_bundle_validator.py:107`); state plainly that the next pipelex bump fails loudly on the missing kwarg by design (shared-assembly rule) — rides D3's cascade. Name the member (`temporal/`) in the body.

## Phase 7 — Close out

- [ ] Full `make agent-check` + `make agent-test` (the full suite — new test modules only get seen there).
- [ ] Commit remaining work on `feature/Input-semantics-D2` with the CP structure above; no PR to `dev` (program ruling).
- [ ] Final checkpoint note in this file: what landed where, decisions taken, what the two inbox items are waiting on.

## Deliberately out of scope (do not widen the diff)

- The `pipelex-api` route change (`views`) — Phase 6 item 1.
- The `pipelex-server/temporal/` worker carriage — Phase 6 item 2.
- Any S2 emission fix (E1–E10 in the schema chain): the descriptor reports authored intent from the blueprint, so none are prerequisites.
- The kernel swap (M1), SDK types (D4), hints (H1/H2), `@pipelex/runtime` parity (E1-track).
