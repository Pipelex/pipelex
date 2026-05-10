# Plan: Reintroduce `structuring_method = preliminary_text` via blueprint elaboration + a new `PipeStructure` operator

## Goal

Bring back the "text-then-object" capability that was removed in `16b775b8`, but in a fundamentally different shape:

- Introduce a first-class `PipeStructure` operator (`Text → StructuredConcept`).
- Add a bundle **elaboration pass** in `pipelex/core/interpreter/` that runs after parsing and before factories. When it sees a `PipeLLMBlueprint` with `structuring_method = preliminary_text`, it rewrites that single pipe into a `PipeSequence[PipeLLM(text), PipeStructure]`, with synthetic inner pipes tagged with the original pipe code as `parent_pipe_code`.
- The runtime layer (`PipeLLM`, cogt, Temporal) never sees `structuring_method` anymore — it is purely a **build-time directive**.

This keeps every downstream layer simple and gives users a reusable structuring operator they can also call directly when text comes from elsewhere (extracted PDFs, search results, user input).

## Non-goals (explicitly deferred)

- A generic "meta-pipe" framework for arbitrary build-time expansions. We build the one elaboration pass needed today; the abstraction can be extracted once a second concrete need appears.
- Per-step prompt customization for `structuring_method`. If users want fine control, they author the two pipes by hand using `PipeLLM` + `PipeStructure`.
- Image inputs on `PipeStructure`. v1 takes Text only; image-aware structuring stays in `PipeLLM`.

---

## Phase 1 — Foundations

Add the metadata field that synthetic pipes will carry through elaboration so traces/logs can group them under their parent.

- [ ] Add `parent_pipe_code: str | None = None` to `PipeBlueprint` base in `pipelex/core/pipes/pipe_blueprint.py`.
- [ ] Mirror the field on the runtime base `PipeAbstract` (or whichever class holds `code` / `domain_code` today) so it survives blueprint → live pipe construction. Confirm where `code` lives on the runtime side and put `parent_pipe_code` next to it.
- [ ] Wire `parent_pipe_code` through `PipeFactory.make_from_blueprint()` and the per-type factories (`PipeLLMFactory`, `PipeSequenceFactory`, the rest) so it's set on every constructed pipe when present on the blueprint.
- [ ] Add unit test confirming the field round-trips: blueprint with `parent_pipe_code` → live pipe carries the value.

---

## Phase 2 — `PipeStructure` operator (runtime + blueprint + factory)

A minimal operator: one Text input, one structured output, an LLM call in the middle.

- [ ] Create `pipelex/pipe_operators/structure/` with:
  - [ ] `__init__.py`
  - [ ] `exceptions.py` (e.g. `PipeStructureError`, `PipeStructureFactoryError`)
  - [ ] `pipe_structure_blueprint.py` defining `PipeStructureBlueprint(PipeBlueprint)` with:
    - `type: Literal["PipeStructure"] = "PipeStructure"`
    - `pipe_category: Literal["PipeOperator"] = "PipeOperator"`
    - `model: LLMModelChoice | None = None` — the structuring model (analog of `model_to_structure`).
    - `validate_inputs()` enforcing exactly one Text input.
    - `validate_output()` enforcing the output is a non-Text structured concept.
  - [ ] `pipe_structure.py` defining `PipeStructure(PipeOperator[PipeStructureOutput])`:
    - Holds `llm_choice: LLMModelChoice | None`, `text_input_name: str` (the resolved name of the single Text input).
    - `_live_run_operator_pipe`: resolve the input Text from working memory, build the structuring prompt (a small hardcoded template like `"Structure the following text into the requested schema:\n\n{{ text }}"`), append the schema via the existing helper used by `PipeLLM`, call `content_generator.make_object` (or `make_object_list` for list outputs), wrap into `PipeStructureOutput`.
    - Honor `output_multiplicity` from the parsed bracket notation (`Foo`, `Foo[]`, `Foo[N]`) just like `PipeLLM` does.
    - Reuse the existing schema-injection helper in `pipe_operators/llm/helpers.py` rather than reinventing it.
  - [ ] `pipe_structure_factory.py` defining `PipeStructureFactory(PipeFactoryProtocol[PipeStructureBlueprint, PipeStructure])`. Mirrors the lean parts of `PipeLLMFactory` (model choice resolution, output multiplicity parsing).
- [ ] Register `PipeStructureBlueprint` in `PipeBlueprintUnion` (`pipelex/core/bundles/pipelex_bundle_blueprint.py`).
- [ ] Register `PipeStructure` and `PipeStructureFactory` wherever pipe types are enumerated:
  - [ ] `PipeType` enum (find via `grep -rn "PipeType("`)
  - [ ] Class registry registration (find the place where `PipeLLMFactory`, `PipeSequenceFactory` etc. are registered)
  - [ ] Any kajson / Temporal data converter allow-lists (find via `grep -rn "PipeLLM" pipelex/temporal/`)
- [ ] Add a unit test `tests/unit/pipelex/pipes/operator/pipe_structure/test_pipe_structure.py`:
  - Blueprint validation rejects non-Text input.
  - Blueprint validation rejects Text output.
  - Factory produces a runtime `PipeStructure` with the right model choice and output multiplicity.
- [ ] Add an integration test running `PipeStructure` end-to-end on a small fixture concept (use the existing `inference` / `llm` markers).

---

### CHECKPOINT 1

`PipeStructure` exists as a standalone, directly-usable operator. A `.mthds` file can declare a `PipeStructure` pipe and run it. Elaboration not introduced yet. `make agent-check` and `make agent-test` are green.

State to capture in this file at checkpoint time:

- File paths created
- Open questions that surfaced during implementation
- Anything deferred to later phases

---

## Phase 3 — `PipeStructureSpec` (authoring layer)

Mirror the operator at the spec layer so users authoring via specs can declare it.

- [ ] Create `pipelex/builder/pipe/pipe_structure_spec.py` defining `PipeStructureSpec(PipeSpec)`:
  - `type: SkipJsonSchema[Literal["PipeStructure"]]`
  - `pipe_category: SkipJsonSchema[Literal["PipeOperator"]]`
  - `model: str | None = Field(default=None, description=...)`
  - `to_blueprint()` returning `PipeStructureBlueprint`.
  - `rendered_pretty()` consistent with the other spec classes.
- [ ] Add `PipeStructureSpec` to `PipeSpecUnion` in `pipelex/builder/pipe/pipe_spec_union.py`.
- [ ] Add `PipeStructureSpec` to `pipe_spec_map.py` if that mapping exists.
- [ ] Add a unit test for the spec → blueprint round-trip.

---

## Phase 4 — Bundle elaboration framework

Add the elaboration pass infrastructure, kept narrow on purpose. No generic plugin system yet.

- [ ] Create `pipelex/core/interpreter/bundle_elaborator.py` with:
  - [ ] `BundleElaboratorError(PipelexInterpreterError)` exception type.
  - [ ] `class BundleElaborator` with a single classmethod `elaborate(bundle: PipelexBundleBlueprint) -> PipelexBundleBlueprint`.
  - [ ] Internal helpers per elaboration kind. v1 has only `_elaborate_preliminary_text` (Phase 5), but the dispatch is structured so adding more is mechanical.
  - [ ] The pass returns a **new** `PipelexBundleBlueprint` (don't mutate input). Copy `domain`, `description`, `system_prompt`, `main_pipe`, `concept`, `source` over, rebuild `pipe` dict by walking each entry.
- [ ] Wire elaboration into `PipelexInterpreter.make_pipelex_bundle_blueprint()` in `pipelex/core/interpreter/interpreter.py`. After successful `model_validate()`, call `BundleElaborator.elaborate(...)` and return the elaborated bundle. Errors raised by the elaborator must be wrapped in `PipelexInterpreterError` with clear context (which pipe, which directive).
- [ ] Verify all callers of `make_pipelex_bundle_blueprint()` (in `library_manager.py`) still work; the contract is unchanged from their perspective.
- [ ] Add a unit test passing a vanilla bundle through and confirming no-op behavior (output equals input semantically).

---

## Phase 5 — `preliminary_text` elaboration

Implement the actual rewrite. This is the meat of the change.

- [ ] In `BundleElaborator._elaborate_preliminary_text`, given an entry `(pipe_code, PipeLLMBlueprint)` with `structuring_method = preliminary_text`:
  - [ ] **Pre-checks** (raise `BundleElaboratorError` with good context on failure):
    - [ ] Output concept must NOT be `Text` (today this is a runtime check in `pipe_llm.py:66`; move it here with a clear message tying back to the user's pipe code).
    - [ ] No collision: synthetic codes (`<pipe_code>__draft_text`, `<pipe_code>__structure`) must not already exist in `bundle.pipe`.
  - [ ] **Synthesize step-1**: a `PipeLLMBlueprint` named `<pipe_code>__draft_text`:
    - Inherits `inputs`, `system_prompt`, `prompt`, `model` from the original.
    - `output = "Text"` (or `"Text[]"` / `"Text[N]"` matching the original's multiplicity — both steps must agree on shape).
    - `structuring_method = None`.
    - `parent_pipe_code = pipe_code`.
    - `description` derived from the original (e.g. `"Draft text for {pipe_code}"`).
  - [ ] **Synthesize step-2**: a `PipeStructureBlueprint` named `<pipe_code>__structure`:
    - `inputs = {"draft_text": "Text"}` (or matching multiplicity).
    - `output` = original output.
    - `model` = original `model_to_structure`.
    - `parent_pipe_code = pipe_code`.
    - `description` derived (e.g. `"Structure step for {pipe_code}"`).
  - [ ] **Synthesize the wrapping sequence**: a `PipeSequenceBlueprint` keyed at the original `pipe_code`:
    - `inputs` = original inputs.
    - `output` = original output.
    - `description` = original description.
    - `steps` = `[SubPipeBlueprint(pipe="<code>__draft_text", result="draft_text"), SubPipeBlueprint(pipe="<code>__structure", result="<original_result_name_or_pipe_code>")]`.
    - `parent_pipe_code = None` — the sequence is the user-facing pipe, not synthetic.
  - [ ] Insert the three resulting blueprints into the new `pipe` dict (replacing the original entry at `pipe_code`).
- [ ] Multiplicity propagation: if the original output is `Foo[]` or `Foo[3]`, both step-1 (`Text[]` / `Text[3]`) and step-2 (`Foo[]` / `Foo[3]`) must agree. Decide and implement: either step-1 generates a single Text and step-2 produces a list (current "structure into list from a single text" behavior of the old code), or step-1 generates `Text[N]` and step-2 maps. Pick the simpler one consistent with the deleted code's behavior — review the deleted `make_text_then_object_list` signature in commit `16b775b8` to confirm.
- [ ] Image inputs handling: any image inputs on the original `PipeLLM` must flow ONLY to step-1. Step-2 is text-only. Add this constraint and a unit test.
- [ ] Add unit tests in `tests/unit/pipelex/core/interpreter/test_bundle_elaborator.py`:
  - [ ] Bundle with one `preliminary_text` PipeLLM produces the expected three-pipe structure.
  - [ ] `parent_pipe_code` is set on synthetic pipes, not on the sequence.
  - [ ] Output `Text` raises `BundleElaboratorError` with a message naming the user's pipe code.
  - [ ] Synthetic-name collision raises `BundleElaboratorError`.
  - [ ] Multiplicity preserved for `Foo`, `Foo[]`, `Foo[N]`.
  - [ ] Image input present on original → image flows to step-1 only.
  - [ ] Bundle without `preliminary_text` is unchanged.
- [ ] Add an integration test (`tests/integration/...`) running an end-to-end `preliminary_text` PipeLLM through a real LLM call, asserting the structured output is valid.

---

### CHECKPOINT 2

`structuring_method = preliminary_text` works end-to-end via elaboration. Tests green. The runtime layer still has the legacy field on `PipeLLM` though — Phase 6 cleans it.

State to capture:

- Final synthetic naming convention chosen (and any divergence from `<code>__draft_text` / `<code>__structure`)
- Multiplicity decision (step-1 single vs list)
- Any blockers found in the existing factories or registries

---

## Phase 6 — Remove `structuring_method` from runtime `PipeLLM`

The field is now purely a build-time directive. The runtime should not know about it.

- [ ] Remove `structuring_method: StructuringMethod | None = None` from `PipeLLM` (`pipelex/pipe_operators/llm/pipe_llm.py`).
- [ ] Remove the `validate_output_concept_consistency` validator that checks `structuring_method` (the elaborator now owns this check).
- [ ] Remove the `if self.structuring_method is not None:` block in `_live_run_operator_pipe` (the `NotImplementedError` raise site).
- [ ] Remove the `structuring_method` line in `execution_data_dict` near `pipe_llm.py:338`.
- [ ] In `PipeLLMFactory.make()`: stop passing `structuring_method=blueprint.structuring_method` to the `PipeLLM(...)` constructor.
- [ ] Keep `structuring_method` on `PipeLLMBlueprint` — it remains part of the language surface and is consumed by the elaborator. Add a `model_validator` on `PipeLLMBlueprint` that enforces `structuring_method != PRELIMINARY_TEXT or output != "Text"` so authoring-time errors surface fast (the elaborator also checks, but blueprint-level catch is friendlier).
- [ ] Add `structuring_method: StructuringMethod | None = None` field to `PipeLLMSpec` so spec authors can opt in.
- [ ] Update `PipeLLMSpec.to_blueprint()` to forward the field.
- [ ] Run `make agent-check` and verify the StructuringMethod enum is still imported only where it's used (the blueprint, the spec, the elaborator).

---

## Phase 7 — Trace / log UX

Make synthetic pipes friendly in observability surfaces.

- [ ] Find every place that logs / traces a pipe execution (search for usages of `pipe_code` in tracing, run_reporting, journal, distributed-tracing files). For each: when `parent_pipe_code` is set, render as `<parent_pipe_code> [<step_role>]` where step role is derived from the suffix (`draft_text` → `text draft`, `structure` → `structuring`). Plain `pipe_code` is the fallback.
- [ ] If there is a `pipelex list` command or an MCP / CLI surface that enumerates user-facing pipes, exclude pipes with `parent_pipe_code != None` from listings (they're implementation details). Confirm by running the CLI command.
- [ ] If `mthds-ui` graph viewer renders the graph, decide whether to nest synthetic pipes under their parent or treat them as top-level. Defer the UI change if it requires `mthds-ui` repo work — record as a follow-up TODO here, don't block the Pipelex change on it.

---

## Phase 8 — Round-out tests

Belt-and-suspenders coverage.

- [ ] Test that running the same `preliminary_text` PipeLLM via Temporal works (elaboration runs once at bundle load; Temporal sees only the expanded form).
- [ ] Test that kajson serialization of the elaborated bundle round-trips correctly (synthetic pipes survive).
- [ ] Test that an MTHDS file with `structuring_method = "preliminary_text"` validates and parses (not just programmatic blueprints).
- [ ] Test directly using `PipeStructure` in a hand-written `PipeSequence` (independent of the elaboration sugar).
- [ ] Confirm the "no preliminary_text → no behavior change" guarantee: the existing PipeLLM test suite should still pass unchanged.

---

## Phase 9 — Documentation & changelog

- [ ] Add a docs page for `PipeStructure` under the operators section (mirror the structure of the `PipeLLM` page). Cover: what it does, when to use it, inputs / outputs, model choice, examples.
- [ ] Restore / rewrite the structuring docs that were deleted in `16b775b8` (the deleted file was `*/llm-structured-generation-config.md` per that commit's stat). New version explains the build-time elaboration behavior, not the old runtime mechanism. Show before/after of what the user writes vs what runs.
- [ ] Add an entry under `[Unreleased]` in `CHANGELOG.md` summarizing: new `PipeStructure` operator, `structuring_method = preliminary_text` works again, runtime simplification.
- [ ] Cross-check `mkdocs.yml` includes any new doc pages.

---

## Phase 10 — Final validation

- [ ] `make agent-check` (lint + types) clean.
- [ ] `make agent-test` (full test suite) clean.
- [ ] Manually run a small `.mthds` example using `structuring_method = preliminary_text` and a separate one using `PipeStructure` directly. Confirm both produce structured output.
- [ ] Spot-check a trace / log line for a `preliminary_text` run — confirm `parent_pipe_code` shows up in the friendly form.
- [ ] Update this `TODOS.md` with any deviations from the plan and remaining follow-ups.

---

## Open questions to revisit during implementation

- Final synthetic-name pattern: `__draft_text` / `__structure` or shorter (`__t` / `__s`)? Lean toward the descriptive form unless there's a code-length constraint.
- Should `PipeStructureSpec` also accept image references, given Phase 2 forbids them on the operator? Likely no — keep parity.
- Does the elaborator need to handle nested expansions (a `PipeLLM` with `preliminary_text` *inside a synthesized sequence* of another expansion)? v1 only expands the top-level `bundle.pipe` dict; if an expansion produces a blueprint that itself needs expansion, we'd need fixed-point iteration. Out of scope today, but flag it if it surfaces.
- Where exactly does `PipeType` live, and is the registry static or pluggable? Confirm during Phase 2 implementation; if pluggable, no Pipelex-internal change needed beyond registration.
