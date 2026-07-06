# Datetime track — implementation plan for the native `Date` concept

Status: **plan written 2026-07-07, implementation not started**. Design: `datetime-design.md` (**approved**, decisions DT1–DT8). Branch `feature/Smart-inputs`, worktree `_smart`, based on main at v0.38.0. Track order (`README.md`): YesNo → **Datetime (this plan)** → Smart Inputs, one release wave.

How to use this doc: work the phases in order, check boxes as you go, and at each CHECKPOINT update the "state" line under it (what landed, commit hashes, open questions) so the next session cold-starts from here.

## 0. Cold-start context — read this first

**What ships:** one new native concept `Date` — "A calendar date, optionally with a time of day — as precise as its source states." Content = required `datetime.date` + optional `datetime.time` (UTC offset rides on the time's `tzinfo`). Rationale, rejected alternatives (one-vs-three), timezone policy, rendering, and non-goals are all in `datetime-design.md` — do not relitigate them here.

**Key mechanism facts** (verified 2026-07-07, line numbers approximate):

- **Adding a native concept** = enum value in `NativeConceptCode` (`pipelex/core/concepts/native/concept_native.py:20`) + arms in its exhaustive matches (`structure_class`, `is_composite`, `is_text_concept`, `is_dynamic_concept`) + a `case` in `ConceptFactory.make_native_concept` (`pipelex/core/concepts/concept_factory.py:98`) + content-class registration in `CoreRegistryModels.STUFF` (`pipelex/core/registry_models.py:92`). The library auto-loads natives from the enum (`concept_library.py:63`); reference validation and class-name lookups iterate the enum, so they pick the new value up automatically. Exhaustive `match/case` style means pyright walks you to every remaining site — no `case _` anywhere.
- **The content-class precedent** is `NumberContent` (`pipelex/core/stuffs/number_content.py`): one file per class in `pipelex/core/stuffs/`, overriding `short_desc`, `rendered_plain`, `rendered_html`, `rendered_markdown`, `rendered_json`. `structure_class_name` is auto-derived as `f"{enum_value}Content"` → the class MUST be named `DateContent`.
- **Bottom-up input dispatch** lives in `StuffFactory.make_stuff_from_stuff_content_or_data` (`pipelex/core/stuffs/stuff_factory.py:229`). Case 1.3 (bare `StuffContent` instance) infers the concept generically from the class name (`DateContent` → `native.Date`) — **works with zero code change** once the enum value exists. Case 2 (envelope): 2.1 str-content currently *requires* Text-compatibility (`stuff_factory.py:470`) — must learn the Date-compatible arm; content being a bare `datetime.date`/`datetime.datetime` object (TOML envelope) has no arm today and lands in the fallthrough.
- **`StuffContentFactory.make_content_from_value`** (`pipelex/core/stuffs/stuff_content_factory.py:12`) is where value→content conversion happens (special case: str + `TextContent`). Signature is typed `value: dict[str, Any] | str` — widens for temporal values.
- **Cross-repo gotcha:** `StuffContentOrData` / `PipelineInputs` live in the **mthds-python** package (`mthds/protocol/pipeline_inputs.py`, a pinned dependency — NOT in this repo). The union admits `str | Sequence[str] | StuffContentAbstract | Sequence[StuffContentAbstract] | dict[str, Any]` — bare `datetime` objects are NOT admitted. **Core-scope answer: don't touch the protocol.** The CLI loader converts TOML temporal literals into `DateContent` instances (admitted via case 1.3) before they hit the seam; datetime objects *nested inside* envelope/structured dicts pass fine (`dict[str, Any]`). Protocol widening to bare scalars rides Smart Inputs D10 with the rest of the downstream wave.
- **The error being retired:** `InputsDatetimeNotSupportedError` (`pipelex/cli/commands/run/exceptions.py:7`), raised by the recursive walk `_assert_no_datetime_values` (`pipelex/cli/commands/run/_inputs_file_loader.py:111`), caught at `_run_core.py:180` and `agent_cli/commands/run/stdin_resolver.py:200`. Tests: `tests/unit/pipelex/cli/commands/run/test_inputs_file_loader.py:99` (parametrized over the TOML temporal literal flavors) and `tests/unit/pipelex/cli/test_stdin_resolver.py:345`.
- **Already free, verify only:** LLM structured output ships `model_json_schema()` of the content class (`pipe_llm.py:249` dispatch, object path via `assignment_models.py:95`) — `output = "Date"` works day one, and DT2's field descriptions carry the anti-fabrication instruction into the schema. Dry-run mocks use polyfactory (`WorkingMemoryFactory.make_mock_content`, `working_memory_factory.py:174`), which synthesizes `date`/`time` natively. JSON cleaning already ISO-serializes all temporal types (`tools/misc/json_utils.py:58`). Structured-content HTML rendering ISO-renders `datetime`/`date` (`core/stuffs/html_rendering.py:53`) — check whether a `datetime.time` arm is missing.
- **Internal JSON serialization (kajson) — verified equipped, must be round-trip-tested.** Two different "JSON"s coexist and must not be confused. (a) The *inputs file* surface (`inputs.json`) is plain stdlib JSON — no kajson, no class metadata; bare ISO strings stay Text there until Smart Inputs (DT5's no-sniffing rule stands). (b) The *internal wire* is kajson (`../kajson` repo): `kajson/kajson.py` registers stock encoder/decoder pairs for the whole temporal family — `datetime.date`, `datetime.datetime`, `datetime.time`, fixed-offset `datetime.timezone`, `ZoneInfo`, `timedelta` — with offset-hardened wire handling for exactly DT2's subtle case (a bare `time` carrying a fixed-offset tzinfo; kajson's own comments note a ZoneInfo on a bare time destroys the offset, reinforcing DT3's offsets-only policy). So `DateContent` needs **no kajson changes** — but the round-trip must be pinned by tests because of the distributed stakes: per the Temporal work, a content class that fails payload *decode* inside a workflow does not fail loudly, it **hangs** (converter exceptions retry forever). The cross-process path: `WorkingMemory.dump_for_transport()` (`working_memory.py:551`) dumps in pydantic *python mode* — real `date`/`time` objects sit in the transport dict (its "JSON-safe" docstring is only true for kajson-or-pydantic-aware wires, not stdlib `json.dumps`) — then hydration goes `hydrate_working_memory` → `hydrate_content` → `model_validate` (`runtime_bridge/primitives/hydration.py:141`), which accepts both real temporal objects (kajson road) and ISO strings (pydantic json-mode road). Existing test module to extend: `tests/unit/pipelex/runtime_bridge/primitives/test_hydration.py`.
- **DT8 sites** (severable field-type fix): `ConceptStructureBlueprintFieldType.DATE` (`concept_structure_blueprint.py:44`) maps to Python `datetime.datetime` in the structure generator (`structure_generation/generator.py:375` and `:569`); default-value validator checks `isinstance(..., datetime)` (`concept_structure_blueprint.py:180`); stale TODO at `:64`. Docs using `type = "date"`: `docs/building-methods/concepts/inline-structures.md`, `define_your_concepts.md` (+ cookbook pages, cross-repo).

**House rules that bite here:** TDD (tests first, red→green); keyword-only args (bare `*` after the subject — `make cko` gates); error classes only in `exceptions.py` modules; no `case _` in enum matches; `make agent-check` after code changes; `make agent-test` before wrapping a session; `make tb` for a quick boot check; `make gep` regenerates error pages; no hardcoded counts in docs/comments; changelog entries under `[Unreleased]`.

## Phase 1 — Concept core (DT1–DT4)

Tests first, then make them green:

- [ ] **Tests** in `tests/unit/pipelex/core/stuffs/test_date_content.py` (mirror the neighboring content-class test style): construction (date-only; date + naive time; date + offset time); the render matrix — `rendered_plain`/`rendered_markdown`/`rendered_html` give truncated ISO 8601 (`2026-07-07`, `2026-07-07T15:40:00`, `2026-07-07T15:40:00+02:00`), `rendered_json` gives the two-field form; `short_desc` distinguishes "a date (...)" vs "a date and time (...)"; `to_datetime()` on the with-time case, and its no-time behavior; `model_json_schema()` contains both field descriptions (the anti-fabrication instruction — this is contract, not decoration).
- [ ] **Serialization round-trip tests** (the distributed-execution safety net — a decode failure at the Temporal boundary hangs, it doesn't fail; see §0): `kajson.dumps` → `kajson.loads` of a `DateContent` in each precision state (date-only; naive time; offset-carrying time), asserting **typed equality** — the reconstructed `date`/`time`/`tzinfo` objects, not string forms — and asserting class-registry resolution by name. Then the cross-process transport road: extend `tests/unit/pipelex/runtime_bridge/primitives/test_hydration.py` with a `Date` stuff (and one inside a `ListContent`, exercising the `__pipelex_class__` marker path) through `dump_for_transport` → `hydrate_working_memory`, offset preserved end-to-end; plus the ISO-string road (json-mode dump of the transport dict → hydrate) since payload wires that aren't kajson (pydantic json-mode, FastAPI encoders) deliver strings that `model_validate` must parse back.
- [ ] **`DateContent`** in new `pipelex/core/stuffs/date_content.py`: `date: datetime.date` (required), `time: datetime.time | None = None`, pydantic `Field(description=...)` on both per DT2 ("include the time only when the source states one — never invent a time"), the `rendered_*` overrides + `short_desc` per DT4, and a `to_datetime()` helper. Micro-decision to settle here: `to_datetime()` when `time is None` — **leaning raise** (typed error, no silent midnight); record the choice below.
- [ ] **Enum + matches:** `DATE = "Date"` in `NativeConceptCode` + arms in `structure_class` (→ `DateContent`), `is_composite` (False group), `is_text_concept` (False group), `is_dynamic_concept` (False group). Let pyright surface any other exhaustive match over the enum.
- [ ] **Factory arm** in `ConceptFactory.make_native_concept`: description exactly per DT1 — "A calendar date, optionally with a time of day — as precise as its source states."
- [ ] **Registry:** add `DateContent` to `CoreRegistryModels.STUFF`.
- [ ] **`html_rendering.py`:** confirm/add a `datetime.time` arm (ISO) so a time value inside any structured content renders.
- [ ] `make tb` (boot + config load), `make agent-check`, targeted pytest on the new test module.

### CHECKPOINT 1 — concept exists and boots

State: _not reached._ (Update with: commits, the `to_datetime` decision, anything that fought back.)

## Phase 2 — Inputs (DT5): TOML literals in, rejection narrowed

- [ ] **Tests first.** Rework `test_inputs_file_loader.py`: the rejection parametrization narrows to local-time only; new cases assert a top-level TOML local date → `DateContent(date=...)`, local datetime → `DateContent(date=..., time=...)` (naive), offset datetime → offset preserved on `time.tzinfo`. Unit tests for the factory arms: envelope `{"concept": "Date", "content": "2026-07-07"}` and `{"concept": "x.DueDate", "content": <date obj>}`; a refining concept keeps its own concept ref on the Stuff; ISO-string forms (date-only, datetime, with offset); rejection of non-ISO strings and of `int` (no epoch-seconds — disable pydantic's lenient number→temporal coercion if it leaks through). Update `test_stdin_resolver.py:345` expectations.
- [ ] **`StuffContentFactory.make_content_from_value`:** widen `value` typing and add `DateContent` target cases — `datetime.date` object; `datetime.datetime` object (split via `.date()` + `.timetz()`, preserving tzinfo; a TOML midnight datetime keeps `time=00:00:00` — TOML distinguishes date vs datetime literals by type, fidelity says keep what was stated); ISO `str` (parse date-only vs datetime forms; strict ISO, no loose formats); dict passes through `model_validate` as today.
- [ ] **`StuffFactory` case 2 (envelope):** content is a bare `datetime.date`/`datetime.datetime` → route through the resolved concept's content class (Date-compatible concepts only, else typed error); case 2.1 (str content) — extend the Text-only guard: Text-compatible → `TextContent`, Date-compatible → `DateContent` from ISO string, else the existing error (message updated to name both possibilities).
- [ ] **Loader** (`_inputs_file_loader.py`): replace `_assert_no_datetime_values` with a conversion walk — **top-level** bare `datetime.date`/`datetime.datetime` values → `DateContent` instances (enter the seam as case 1.3; concept inference is generic); `datetime.time` anywhere → the narrowed error; temporal objects *nested* inside envelope-content or structured dicts are left in place (factory arms and pydantic validation consume them). Module docstring updated.
- [ ] **Error class:** rename/narrow `InputsDatetimeNotSupportedError` → time-only semantics (proposed name `InputsTimeOnlyNotSupportedError`; message per DT5: a time of day alone has no date to attach to — include the date or quote the value as a string). Update class docstring (drop "until DATETIME concept support lands"), `user_action`, both catch sites (`_run_core.py`, `stdin_resolver.py` including its `error_type` string), then `make gep`.
- [ ] **e2e:** extend the TOML-inputs e2e coverage from #1022 (find its `.mthds` + `inputs.toml` fixtures) with a pipe consuming a `Date` input fed by TOML literals, run through `pipelex run` dry mode.
- [ ] **Dry-run mock check:** a pipe with `Date` input/output passes dry run (polyfactory synthesizes it); fix `_get_mockable_class`/generator quirks only if they surface.
- [ ] `make agent-check`.

### CHECKPOINT 2 — TOML temporal literals run end-to-end

State: _not reached._ (Update with: final error-class name, any protocol-typing friction met at the seam, commits.)

## Phase 3 — LLM output verification (DT7)

- [ ] Locate how `output = "Number"` is covered in PipeLLM tests and mirror for `Date`: assert the object path is selected (not the Text path) and the schema handed to content generation is `DateContent`'s with both field descriptions.
- [ ] Optional, non-gating: one live-gateway smoke of an extraction that should produce date-only vs date+time (manual; not CI).

No new generation machinery: the leaner scalar-native generation form is explicitly deferred to the YesNo LLM-output-ergonomics follow-up (design DT7).

## Phase 4 — DT8: fix the `date` structure-field misnomer (severable — may be dropped without touching Phases 1–3)

- [ ] **Tests first:** structure-generation tests asserting `type = "date"` fields now emit `datetime.date` (schema `format: date`) and new `type = "datetime"` fields emit `datetime.datetime` (`format: date-time`); default-value validation matches each.
- [ ] `ConceptStructureBlueprintFieldType`: add `DATETIME = "datetime"`; pyright walks the exhaustive matches (blueprint validation arms, `_validate_default_value_type`, generator mapping sites at `generator.py:375` and `:569`).
- [ ] `DATE` arms flip to `datetime.date` (generator import + default-value isinstance check); resolve the stale TODO at `concept_structure_blueprint.py:64` or carry it over consciously.
- [ ] Docs: `inline-structures.md` ("Date and datetime values..." section) + `define_your_concepts.md` — `date` = calendar date, `datetime` = timestamp; note the field-vs-concept distinction (a field wanting document-fidelity optional-time semantics uses `type = "concept", concept_ref = "Date"`).
- [ ] Regenerate the MTHDS schema (`.venv/bin/pipelex-dev generate-mthds-schema`) — the field-type enum lands in it (the native concept ref itself does not change the schema shape). Downstream copies sync in the release wave, not now.
- [ ] Changelog: breaking — `date` fields no longer carry a time; `datetime` field type added. Cookbook methods using `type = "date"` (invoice/DPE extractions) improve for free — note for the cross-repo sweep, do not edit cookbook here.

### CHECKPOINT 3 — DT8 landed or consciously dropped

State: _not reached._ (If dropped: record why, and file the misnomer as its own follow-up so it isn't lost.)

## Phase 5 — Docs, changelog, wrap

- [ ] `docs/building-methods/concepts/native-concepts.md`: table row for `Date` + a fields note in the commonly-used-fields section (`date`, optional `time`), mirroring Number's entry style.
- [ ] Inputs docs: minimal edit noting TOML date/datetime literals are now native `Date` inputs and time-only literals are the remaining unsupported case (`docs/building-methods/pipes/provide-inputs.md` gets its full rewrite in the Smart Inputs phase — keep this surgical).
- [ ] `CHANGELOG.md` under `[Unreleased]`: added native `Date` concept (one-line pitch + TOML literal support); breaking — `Date` is now a reserved native code (a bundle declaring `[concept.Date]` errors); breaking/renamed — datetime-inputs rejection narrowed to time-only (new error name); DT8 entries if Phase 4 shipped.
- [ ] Track bookkeeping: update `wip/inputs/README.md` (Datetime step → done, remaining = YesNo plan / Smart Inputs) and this plan's checkpoint states.
- [ ] Full gates: `make agent-check` + `make agent-test`.

### CHECKPOINT 4 — track complete, hand off to the next train car

State: _not reached._ (Update with: final commits, gate results, anything deferred.)

## Deferred to the release-wave sweep (NOT this plan's scope — listed so nothing is lost)

Shared per-release wave with YesNo + Smart Inputs (see `README.md`): MTHDS spec native-concepts tables (`mthds/docs/language/concepts.md`, `mthds/docs/spec/mthds-format.md`); schema-copy sync via the `mthds-schema-sync` skill; `mthds-python` protocol widening for bare temporal scalars (rides Smart Inputs D10) + any native-list mirrors; `mthds-js` mirrors; conformance rows; `mthds-plugins` skills (`mthds-inputs`, `mthds-build`); editor tooling completion lists (vscode-pipelex). Plus the YesNo/Date shared follow-up: LLM-output ergonomics for scalar natives.

`pipelex-temporal` (private plugin repo): **no code change expected** — its codec serializes the `dump_for_transport` dict via kajson and binds classes through the registry, so `DateContent` flows in with the pipelex version-pin bump. At pin-bump time, add a `Date` case to its converter round-trip tests anyway: the failure mode over there is a hang, not an error, so coverage is cheap insurance.

## Micro-decisions log

- `to_datetime()` with `time is None`: **open** — leaning raise (no silent midnight). Settle in Phase 1.
- Final narrowed-error class name: **open** — proposed `InputsTimeOnlyNotSupportedError`. Settle in Phase 2.
- (Record further micro-decisions here as they're taken, with a one-line why.)
