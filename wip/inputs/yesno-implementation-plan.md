# YesNo track — implementation plan for the native `YesNo` concept

Status: **plan written 2026-07-07, implementation not started**. Design home: `smart-inputs-design.md` §D9 (**approved** — there is no separate YesNo design doc; naming, rationale, and rejected alternatives all live in D9). Branch `feature/Smart-inputs`, worktree `_smart`, based on main at v0.38.0. Track order (`README.md`): **YesNo (this plan)** → Datetime → Smart Inputs, one release wave. YesNo holds the train.

How to use this doc: work the phases in order, check boxes as you go, and at each CHECKPOINT update the "state" line under it (what landed, commit hashes, open questions) so the next session cold-starts from here.

## 0. Cold-start context — read this first

**What ships:** one new native concept `YesNo` — the answer to a yes/no question. Content = a single required `bool`. LLM pipelines constantly produce yes/no judgments ("does this contract contain a penalty clause?") and today authors hack them as `Text` answering "yes"/"no" or a single-field structure. The name is settled (chosen over Boolean/TrueFalse/Logical/Truth/Checkbox — Access's "Yes/No" field-type precedent; PascalCase compound follows `TextAndImages`) — do not relitigate; see D9.

**Core scope** (per `README.md`): enum entry, content class, structure-class mapping, schema regen (a verification, see below), MTHDS spec entry (drafted here, merged in the release wave). **Deliberately excluded:** the LLM-output ergonomics (a leaner scalar-native generation form — follow-up shared with the Date track, off the critical path) and bare-scalar input shaping (`"is_urgent": true` at the top level of an inputs file — that is the Smart Inputs D5 matrix row, which activates when Smart Inputs lands; this plan only makes the *envelope* form work).

**Key mechanism facts** (verified 2026-07-07 against the worktree; line numbers approximate):

- **Adding a native concept** = enum value `YES_NO = "YesNo"` in `NativeConceptCode` (`pipelex/core/concepts/native/concept_native.py:20`) + arms in its exhaustive matches — `structure_class` (`:74`), `is_composite` (`:39`, False group), `is_text_concept` (`:132`, False group), `is_dynamic_concept` (`:157`, False group) — + a `case` in `ConceptFactory.make_native_concept` (`pipelex/core/concepts/concept_factory.py:98`) + content-class registration in `CoreRegistryModels.STUFF` (`pipelex/core/registry_models.py:92`). The library auto-loads natives from the enum; reference validation and class-name lookups iterate the enum, so they pick the new value up automatically. Exhaustive `match/case` style (never `case _`) means pyright walks you to every remaining site.
- **`structure_class_name` is auto-derived** as `f"{enum_value}Content"` → the class MUST be named `YesNoContent`, and the concept ref is `native.YesNo`. The class-name→concept inference in `StuffFactory` cases 1.3/1.5 splits on `"Content"` and feeds the prefix back through the enum — `YesNoContent` → `native.YesNo` works with zero code change once the enum value exists.
- **The content-class precedent** is `NumberContent` (`pipelex/core/stuffs/number_content.py`): one file per class in `pipelex/core/stuffs/`, overriding `short_desc`, `rendered_plain`, `rendered_html`, `rendered_markdown`, `rendered_json`. Test precedent: `tests/unit/pipelex/core/stuffs/number_content/` (renders + smart_dump modules).
- **The accessor family precedent** (Number's convenience surface, to mirror): `Stuff.is_number` (`pipelex/core/stuffs/stuff.py:92`) and `Stuff.as_number` (`:218`), `WorkingMemory.get_stuff_as_number` (`pipelex/core/memory/working_memory.py:483`) and `main_stuff_as_number` (`:529`), `PipeOutput.main_stuff_as_number` (`pipelex/core/pipes/pipe_output.py:77`).
- **LLM output works day one, verify only:** PipeLLM dispatch (`pipe_llm.py:249`) sends Text-compatible single outputs down the text path and everything else down the object path with `model_json_schema()` of the structure class — `YesNo` is not Text-compatible, so `output = "YesNo"` takes the object path automatically, and the `Field(description=...)` on the bool field lands in the schema handed to the LLM (contract, not decoration). The structure-prompt machinery already handles `bool` fields (`concept_representation_generator.py:311`). Dry-run mocks use polyfactory, which synthesizes `bool` natively.
- **Serialization is trivially safe but gets one cheap test:** `bool` is JSON-native — no kajson encoder work, unlike Date. Still pin one transport round-trip (`dump_for_transport` → `hydrate_working_memory`, `tests/unit/pipelex/runtime_bridge/primitives/test_hydration.py`) because the distributed failure mode is a hang, not an error (a content class that fails payload decode inside a Temporal workflow retries forever).
- **Inputs today:** an envelope `{"concept": "YesNo", "content": true}` falls through `StuffFactory.make_stuff_from_stuff_content_or_data` case 2 to the terminal `Unexpected type for content value: <class 'bool'>` (`stuff_factory.py:603`) — no bool arm exists. `StuffContentFactory.make_content_from_value` (`stuff_content_factory.py:12`) is typed `value: dict[str, Any] | str` and special-cases str+`TextContent`; it widens for bool. The dict-content envelope `{"concept": "YesNo", "content": {"yes_no": true}}` works day one via `model_validate` (case 2.5). The case 2.1 str-content guard (`stuff_factory.py:470`) only admits Text-compatible concepts — a string `"yes"` for a YesNo concept errors there, and **stays** an error (no cross-kind coercion, same policy as Smart Inputs D5 and Datetime DT5).
- **Cross-repo gotcha:** `StuffContentOrData` / `PipelineInputs` live in the **mthds-python** package (`mthds/protocol/pipeline_inputs.py`, a pinned dependency — NOT in this repo). The union does NOT admit bare `bool` — top-level `true` in an inputs file stays impossible until the Smart Inputs D10 protocol widening (release wave). Envelope dicts are `dict[str, Any]`, so bool content *inside* an envelope passes typing today; bools nested in structured dicts already work. **Core-scope answer: don't touch the protocol.**
- **Schema regen is a verification, not a change:** `pipelex/language/mthds_schema_generator.py` does not enumerate native concept codes, so adding `YesNo` should produce a no-diff regen. Only the boolean-field-type-alias micro-decision (below), if taken, would alter the schema.
- **Python gotcha:** `bool` is a subclass of `int`. No int arms exist in the envelope dispatch today, but any bool arm must be written to hold if one ever appears (check bool BEFORE int) — this is also the guard Smart Inputs D9 mandates for its Number arm. And pydantic v2 lax mode accepts `"yes"`/`"true"`/`1` for a `bool` field via `model_validate` — that leniency applies only inside the dict-content path; we deliberately add no string arms of our own.

**House rules that bite here:** TDD (tests first, red→green); keyword-only args (bare `*` after the subject — `make cko` gates); error classes only in `exceptions.py` modules; no `case _` in enum matches; `make agent-check` after code changes; `make agent-test` before wrapping a session; `make tb` for a quick boot check; no hardcoded counts in docs/comments; changelog entries under `[Unreleased]`.

## Phase 1 — Concept core

Tests first, then make them green:

- [x] **Tests** in `tests/unit/pipelex/core/stuffs/yes_no_content/` (mirror the `number_content/` module split): construction from `yes_no=True`/`False`; the render matrix — `rendered_plain`/`rendered_markdown`/`rendered_html` give `yes`/`no` (per the rendering micro-decision below), `rendered_json` gives `{"yes_no": true}`; `short_desc` (e.g. "a yes/no answer (yes)"); `smart_dump`; `model_json_schema()` contains the field description (the LLM-facing contract); pydantic does NOT accept an `int` where the bool is expected in strict construction paths (pin the `bool`-vs-`int` boundary).
- [x] **Transport round-trip test:** extend `tests/unit/pipelex/runtime_bridge/primitives/test_hydration.py` with a `YesNo` stuff (and one inside a `ListContent`) through `dump_for_transport` → `hydrate_working_memory` — cheap insurance against the Temporal hang-not-fail decode failure mode.
- [x] **`YesNoContent`** in new `pipelex/core/stuffs/yes_no_content.py`: `yes_no: bool` with `Field(description=...)` (wording micro-decision — it is what the LLM reads in the generation schema), `rendered_*` overrides + `short_desc` following the `NumberContent` template.
- [x] **Enum + matches:** `YES_NO = "YesNo"` in `NativeConceptCode` + arms in `structure_class` (→ `YesNoContent`), `is_composite` (False group), `is_text_concept` (False group), `is_dynamic_concept` (False group). Let pyright surface any other exhaustive match over the enum.
- [x] **Factory arm** in `ConceptFactory.make_native_concept`: description per the micro-decision (proposed: "The answer to a yes/no question").
- [x] **Registry:** add `YesNoContent` to `CoreRegistryModels.STUFF`.
- [x] **Accessors** mirroring Number's: `Stuff.is_yes_no` + `Stuff.as_yes_no`, `WorkingMemory.get_stuff_as_yes_no` + `main_stuff_as_yes_no`, `PipeOutput.main_stuff_as_yes_no` — this is how a Python-API caller reads the verdict (`pipe_output.main_stuff_as_yes_no().yes_no`).
- [x] **Refinement sanity test:** a bundle declaring `[concept.IsUrgent]` with `refines = "YesNo"` validates, and the refining concept resolves `YesNoContent` as its structure class (the machinery is generic — this pins it).
- [x] `make tb` (boot + registry load), `make agent-check`, targeted pytest on the new test modules.

### CHECKPOINT 1 — concept exists and boots

State: **reached 2026-07-07.** All Phase 1 tasks landed and gates are green (`make tb`, `make agent-check` — ruff/plxt/pyright 0-errors/mypy Success/cko; targeted pytest on the new modules all pass). Schema regen ran inside `agent-check` (no unexpected diff — confirms §0: the generator doesn't enumerate native codes).

Files touched: new `pipelex/core/stuffs/yes_no_content.py`; enum+matches in `concept_native.py`; factory arm in `concept_factory.py`; registry in `registry_models.py`; accessors in `stuff.py` / `working_memory.py` / `pipe_output.py`. Tests: new `tests/unit/pipelex/core/stuffs/yes_no_content/` (renders + smart_dump + test_data), new `tests/unit/pipelex/core/concepts/concept_factory/test_yes_no_refinement.py`, extended `test_hydration.py`.

Settled micro-decisions: field name `yes_no: bool`; renders `yes`/`no` for plain/markdown/html, `rendered_json` → `{"yes_no": true}`; field description "Whether the answer is yes (true) or no (false)."; native concept description "The answer to a yes/no question"; `short_desc` = "a yes/no answer (yes)"/"(no)". Nothing fought back — the class-name→concept inference and refinement machinery are fully generic (no changes needed there). Boundary test pins `yes_no=2` → ValidationError (pydantic lax still accepts 0/1, which we don't over-assert).

## Phase 2 — Inputs: envelope viability

Scope guard: bare `true` at the top level of an inputs file (JSON or TOML) **stays an error** until Smart Inputs D5 — do not widen the mthds-python protocol here (that's D10, release wave). This phase only makes the explicit envelope usable so `YesNo` inputs exist at all pre-Smart-Inputs.

- [ ] **Tests first** (extend `tests/unit/pipelex/core/stuffs/test_stuff_content_factory.py` + the stuff-factory input tests): envelope `{"concept": "YesNo", "content": true}` → `YesNoContent(yes_no=True)` with concept `native.YesNo`; a refining concept (`{"concept": "x.IsUrgent", "content": false}`) keeps its own concept ref on the Stuff; bool content for a concept NOT YesNo-compatible → typed error naming both; the dict-content form still works; string content `"yes"` for a YesNo concept still errors (pin the no-coercion policy); direct `YesNoContent` instance at top level (case 1.3) infers `native.YesNo`.
- [ ] **`StuffContentFactory.make_content_from_value`:** widen `value` typing to admit `bool` and add the arm — bool + YesNo-family target class → construct directly (mirror the str+`TextContent` special case; keep the bool check ahead of any future int handling).
- [ ] **`StuffFactory` case 2 (envelope):** add a bool-content arm mirroring case 2.1's shape — YesNo-compatible concept (strict `is_compatible` check, like the Text arm) → content via the factory; otherwise a `StuffFactoryError` naming the concept and the provided type. Update the case-list docstring.
- [ ] **Dry-run check:** a pipe with a `YesNo` input and/or output passes dry run (polyfactory mock) — fix generator quirks only if they surface.
- [ ] **e2e:** a small `.mthds` + envelope-form inputs file with a `YesNo` input through `pipelex run` dry mode (reuse the e2e fixture pattern the TOML-inputs feature #1022 established — same fixtures the Date plan's Phase 2 extends).
- [ ] `make agent-check`.

### CHECKPOINT 2 — YesNo flows through inputs (envelope) and dry run

State: _not reached._ (Update with: commits, any dispatch-ordering surprises, whether the 2.1 error message needed updating.)

## Phase 3 — LLM output verification

- [ ] Locate how `output = "Number"` (or the Date plan's Phase 3 equivalent) is covered in PipeLLM tests and mirror for `YesNo`: assert the object path is selected (not the Text path) and the schema handed to content generation is `YesNoContent`'s with the field description present.
- [ ] Optional, non-gating: one live-gateway smoke of a judgment pipe (`output = "YesNo"`) — manual, not CI.

No new generation machinery: the leaner scalar-native generation form is explicitly deferred to the shared YesNo/Date LLM-output-ergonomics follow-up (D9, off the critical path).

## Phase 4 — Docs, schema, changelog, wrap

- [ ] **Settle the boolean-alias micro-decision** (D9 parked it here): does the lowercase `boolean` structure-field type gain a friendlier alias (`yes_no`)? **Leaning NO** — field types are lowercase programmer primitives (`text`, `number`, `boolean`) and an alias is a two-spellings drift magnet; the concept-level brand is `YesNo`. If NO: nothing to do. If YES: field-type enum value + generator arms + schema diff + docs, and the schema-regen step below stops being a no-op.
- [ ] `docs/building-methods/concepts/native-concepts.md`: table row for `YesNo` + a `YesNoContent` section (mirror `NumberContent`'s at `:101`).
- [ ] `docs/building-methods/pipes/pipe-output.md`: add a `main_stuff_as_yes_no` entry (the doc enumerates every other `main_stuff_as_*` accessor around `:151`; the new one would otherwise be silently missing).
- [ ] Schema regen: `.venv/bin/pipelex-dev generate-mthds-schema` — **verify no diff** (see §0; a diff means something unexpected leaked in).
- [ ] **MTHDS spec entry** (in-scope per `README.md`, cross-repo): draft the native-concepts additions in the `mthds/` sibling repo (`docs/language/concepts.md`, `docs/spec/mthds-format.md`) on a side branch — the merge vehicle is the release wave, same pattern as the other cross-repo commits.
- [ ] `CHANGELOG.md` under `[Unreleased]`: added native `YesNo` concept (one-line pitch: typed yes/no answers for LLM judgments, `output = "YesNo"`) + envelope input support; breaking — `YesNo` is now a reserved native code (a bundle declaring `[concept.YesNo]` errors).
- [ ] Track bookkeeping: update `wip/inputs/README.md` (YesNo step → done, next = Datetime plan or Smart Inputs plan) and this plan's checkpoint states.
- [ ] Full gates: `make agent-check` + `make agent-test`.

### CHECKPOINT 3 — track complete, hand off to the next train car

State: _not reached._ (Update with: final commits, gate results, the alias decision, anything deferred.)

## Deferred to the release-wave sweep / follow-ups (NOT this plan's scope — listed so nothing is lost)

Shared per-release wave with Datetime + Smart Inputs (see `README.md`): the Smart Inputs D5 matrix row (bare `true`/`false` against a YesNo-declared input) and D10 protocol widening (`mthds-python` `StuffContentOrData`); schema-copy sync via the `mthds-schema-sync` skill; MTHDS spec merge (drafted in Phase 4); `mthds-js` mirrors; conformance rows; `mthds-plugins` skills (`mthds-inputs`, `mthds-build`); vscode-pipelex completion lists.

Follow-up off the critical path (shared with Date): **LLM-output ergonomics for scalar natives** — how PipeLLM produces a `YesNo`/`Date` more leanly than the generic object path (cousin of the Optionals maybe-wrapper).

`pipelex-temporal` (private plugin repo): no code change expected — `bool` is JSON-native and the codec binds classes through the registry. At pin-bump time, add a `YesNo` case to its converter round-trip tests anyway (the failure mode over there is a hang, not an error; coverage is cheap insurance).

## Micro-decisions log

- Content field name: **SETTLED `yes_no: bool`** (the `NumberContent.number` pattern — field named after the enum value). Alternatives considered: `answer`, `value`, `is_yes`.
- Renderings: **SETTLED `yes`/`no`** for plain/markdown/html (reads naturally when injected into downstream prompts; D9's wording); `rendered_json` keeps the raw `{"yes_no": true}`.
- Field description wording (the LLM generation contract): **SETTLED** "Whether the answer is yes (true) or no (false)."
- Native concept description (factory arm): **SETTLED** "The answer to a yes/no question" (D9's own phrasing).
- `boolean` structure-field-type alias: **leaning NO alias** (one way to spell a thing). Settle in Phase 4 — flag to Louis if in doubt.
- Envelope string forms (`"content": "yes"`): **rejected** — no cross-kind coercion, consistent with Smart Inputs D5 and Datetime DT5. Not open; recorded so nobody reopens it casually.
