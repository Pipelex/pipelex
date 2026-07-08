# PR reviewer's guide — native `YesNo` concept

> **Archived 2026-07-07.** This was the repo-root `TODOS.md` reviewer's guide for the YesNo PR (#1028). YesNo and Date have both landed on `feature/Smart-inputs` (Date via PR #1029, merged), so this guide is now historical. The durable as-built record is `yesno-implementation-plan.md`; the live track roadmap is `README.md`. Kept for the PR-reading narrative only.

This branch (`feature/Smart-inputs`) adds a new built-in native concept **`YesNo`** — the answer to a yes/no question, backed by a single required `bool`. LLM pipelines constantly produce yes/no judgments ("does this contract contain a penalty clause?"); today authors hack them as `Text` answering "yes"/"no" or a one-field structure. `YesNo` makes that a typed first-class concept.

**What is shippable in this PR:** the `YesNo` concept and its input/output plumbing (the diff below). Everything under `wip/inputs/` is planning/design for the broader *Smart Inputs* track (of which `YesNo` is the first of three native-concept prerequisites) — those docs are not implemented here and are not release-facing. Read `wip/inputs/README.md` for the track roadmap and `wip/inputs/yesno-implementation-plan.md` for the phased plan this PR executed (checkboxes + checkpoint state lines record the as-built).

## How to review this

The change is small and purely **additive** — it adds one native code and the arms an exhaustive-match tree requires, plus one factory arm for boolean envelope inputs. No existing behavior changes. Suggested reading order:

1. **`pipelex/core/stuffs/yes_no_content.py`** — the content class. `yes_no: bool` with a `Field(description=...)` (the LLM-facing generation contract), `rendered_*` overrides → `yes`/`no` for plain/markdown/html, `rendered_json` → `{"yes_no": true}`, `short_desc`. Mirrors `NumberContent`.
2. **`pipelex/core/concepts/native/concept_native.py`** + **`concept_factory.py`** + **`registry_models.py`** — the enum value `YES_NO = "YesNo"`, its arms in the exhaustive matches (`structure_class`, `is_composite`, `is_text_concept`, `is_dynamic_concept` — all in the "not composite / not text / not dynamic" groups), the factory arm ("The answer to a yes/no question"), and the `YesNoContent` registration. `structure_class_name` auto-derives to `YesNoContent`, so class-name→concept inference works with no extra code.
3. **Accessors** — `Stuff.is_yes_no` / `as_yes_no`, `WorkingMemory.get_stuff_as_yes_no` / `main_stuff_as_yes_no`, `PipeOutput.main_stuff_as_yes_no`. These faithfully mirror the `Number` accessor family layer-for-layer; `main_stuff_as_yes_no.yes_no` is how a Python caller reads a verdict.
4. **Envelope inputs** — `stuff_content_factory.py` + `stuff_factory.py`. A pipeline input in the envelope form `{"concept": "YesNo", "content": true}` (JSON or TOML) is shaped into a `YesNoContent`. The bool arm is checked **before** any int handling (`bool` ⊑ `int`) and before `model_validate` (which rejects a bare bool), and it routes through the concept resolver so a concept that `refines = "YesNo"` keeps its **own generated subclass** (which `model_validate(True)` would reject but `subclass(yes_no=...)` builds). A bool for a non-YesNo-compatible concept raises a typed error naming `native.YesNo`.

## Test coverage

- **Unit** — `yes_no_content/` (renders + smart_dump + schema-carries-description + the `bool`-vs-`int` boundary); `concept_factory/test_yes_no_refinement.py` (a `refines = "YesNo"` concept resolves `YesNoContent` — the machinery is generic); `test_stuff_content_factory.py` + `data.py` + `test_stuff_factory_implicit_memory.py` (envelope factory arm, refining-subclass preservation, no-coercion pin); `runtime_bridge/.../test_hydration.py` (transport round-trip — cheap insurance against the Temporal decode-hang failure mode, since `bool` is JSON-native).
- **Integration** — `pipe_llm/test_pipe_llm_yes_no_output_path.py` pins that `output = "YesNo"` takes the LLM **object path** (not the text path): a DRY run spies `content_generator.make_object` and asserts it is called with `object_class=YesNoContent` whose schema carries the field description. Fails loudly if someone ever makes `YesNo` Text-compatible.
- **E2E** — `pipes/yes_no/` dry-run bundle (`judge_is_urgent` outputs YesNo; `explain_verdict` takes a YesNo input) + `cli/test_yes_no_inputs_run.py` (subprocess: `pipelex run … --inputs inputs.toml --dry-run` with `content = true`).

## Scope guards (deliberate, not omissions)

- **Bare top-level `true`/`false` in an inputs file stays an error.** Only the *envelope* form works here. Bare-scalar input shaping (`"is_urgent": true` at the top level) is the Smart Inputs D5 matrix row, which activates when Smart Inputs lands. The `mthds/protocol/pipeline_inputs.py` `StuffContentOrData` union (in the external `mthds` package) is **untouched** — widening it to admit bare `bool` is the D10 protocol change, deferred to the release wave.
- **No string→bool coercion.** A `"yes"` string under a YesNo concept still errors (it takes the str path and fails as not-Text-compatible). Consistent with Smart Inputs D5 and the Datetime track.
- **No new LLM-generation machinery.** `output = "YesNo"` works day one via the existing object path; a leaner scalar-native generation form is an explicit follow-up shared with the Date track, off the critical path.
- **`boolean` field-type alias: settled NO.** The lowercase `boolean` structure-field primitive keeps one spelling; the concept-level brand is `YesNo`. Consequence: the MTHDS JSON Schema regen is a **no-diff** (the generator doesn't enumerate native codes).

## Cross-repo (release-wave, not in this PR)

- **MTHDS spec:** the `YesNo` native-concept rows + field listing are drafted in the sibling **`mthds`** repo (`docs/language/concepts.md`, `docs/spec/mthds-format.md`) on side branch `feature/native-yes-no-concept` (not pushed). Merge vehicle is the shared release wave.
- **Deferred to the per-release downstream sweep:** schema-copy sync (`mthds-schema-sync` skill), `mthds-js`/`mthds-python` mirrors, conformance rows, skills, editor completion lists — all shared with the Datetime + Smart Inputs tracks per `wip/inputs/README.md`.
- **`pipelex-temporal`** (private plugin): no code change expected (`bool` is JSON-native, classes bind via the registry); add a `YesNo` converter round-trip test at pin-bump time as cheap insurance.

## Breaking change

`YesNo` is now a reserved native concept code — a bundle declaring `[concept.YesNo]` errors. Noted in the CHANGELOG `[Unreleased]` section.
