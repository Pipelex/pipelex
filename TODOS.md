# Plan: Reintroduce `structuring_method = preliminary_text` via blueprint elaboration + a new `PipeStructure` operator

---

## CHECKPOINT — current state (resume here)

**Branch:** `feature/Text-then-object` (worktree at `_tto/`).

**Last verified:** `make agent-check` clean (ruff/plxt/pyright/mypy all 0 errors, 0 warnings). Targeted run for the touched source areas: `1506 passed, 1 xfailed`. PipeStructure-focused subset (`tests/unit/pipelex/pipe_operators/pipe_structure/ tests/unit/pipelex/core/interpreter/ tests/integration/pipelex/pipes/operator/pipe_structure/`): `92 passed`.

### Status by phase

- [x] **Phase 1 — bundle elaboration metadata.** `StepRole`, `ElaborationMetadata`, and the `elaboration_metadata: dict[str, ElaborationMetadata] | None = Field(default=None, exclude=True)` side-table live on `PipelexBundleBlueprint` (`pipelex/core/bundles/pipelex_bundle_blueprint.py`). Accessor `get_elaboration_for(pipe_code)` added. Unit tests in `tests/unit/pipelex/core/bundles/test_elaboration_metadata.py`.
- [x] **Phase 2 — PipeStructure operator.** Module at `pipelex/pipe_operators/structure/` with `__init__.py`, `pipe_structure_blueprint.py`, `pipe_structure.py`, `pipe_structure_factory.py` (no `exceptions.py` — neither operator-level nor factory-level errors had call sites, so the file was deleted per "no half-finished implementations"). Registered in `PipeBlueprintUnion`, `PipeType.PIPE_STRUCTURE`, `CoreRegistryModels.PIPE_OPERATORS{,_FACTORY}`. Added `PipeType.PIPE_STRUCTURE` arm to the `match` in `pipelex/core/pipes/output/output_renderer.py:_collect_possible_outputs` and to `_PIPE_DEFINITION_NAMES` in `pipelex/language/mthds_schema_generator.py`. New `structuring_prompt` template under `[cogt.llm_config.generic_templates]` in `pipelex/pipelex.toml`. Unit tests in `tests/unit/pipelex/pipe_operators/pipe_structure/` + dry-run integration test in `tests/integration/pipelex/pipes/operator/pipe_structure/`. Regenerated `derived/mthds_schema.json` via `pipelex-dev generate-mthds-schema`.
- [x] **Phase 3 — PipeStructureSpec.** `pipelex/builder/pipe/pipe_structure_spec.py`, registered in `pipe_spec_union.py` and `pipe_spec_map.py`. Tests in `tests/unit/pipelex/builder/pipe/pipe_operator/pipe_structure/test_pipe_structure_spec.py`.
- [x] **Phase 4 — bundle elaboration framework.** `pipelex/core/interpreter/bundle_elaborator.py` with `BundleElaborator.elaborate()`, `BundleElaboratorError(PipelexInterpreterError)`, fast-path short-circuit (identity-preserving), recursive-elaboration guard, post-elaboration `model_validate` re-run. Wired into `PipelexInterpreter.make_pipelex_bundle_blueprint`. Uses a module-level `TypeGuard` (`_is_preliminary_text_pipe`) so callers narrow `PipeBlueprintUnion → PipeLLMBlueprint` without casts.
- [x] **Phase 5 — preliminary_text elaboration.** Synthesizes step-1 (`<code>__draft_text` PipeLLM, output always literal `Text`), step-2 (`<code>__structure` PipeStructure, original output preserved), and replaces the original `<code>` with a `PipeSequence` wrapping both. `elaboration_metadata` populated for the two synthetic codes. Tests in `tests/unit/pipelex/core/interpreter/test_bundle_elaborator.py` cover: short-circuit identity, empty bundle, three-pipe rewrite shape, multiplicity preservation (`Foo` / `Foo[]` / `Foo[3]`), Text-output rejection (incl. `native.Text` and bracketed forms — gated by both the blueprint validator at construction time AND the elaborator's defense-in-depth check via `model_construct`), synthetic-name collision, image-input only on step-1, `main_pipe` regression, model + `model_to_structure` propagation. **Integration test against a real LLM is deferred to Phase 8.**
- [x] **Phase 6 — remove `structuring_method` from runtime PipeLLM.** Done.
  - Removed field, validator, NotImplementedError block, and `execution_data_dict` line from `PipeLLM`. Factory no longer forwards the field.
  - Added `model_validator(mode="after")` `validate_preliminary_text_output` on `PipeLLMBlueprint` — rejects `preliminary_text + Text output` at construction time, before the elaborator runs. The elaborator's matching pre-check stays as defense-in-depth (only reachable via `model_construct`).
  - Added `is_preliminary_text` `@property` on `StructuringMethod` (project rule: never `==` against an enum value).
  - `PipeLLMSpec` exposes `structuring_method: StructuringMethod | None = None` (plain `Field`, not `SkipJsonSchema`) and forwards it in `to_blueprint()`.
  - Deleted obsolete `test_pipe_llm_preliminary_text_raises_not_implemented` integration test.
  - Updated `tests/unit/pipelex/language/test_mthds_schema.py::test_all_pipe_types_present` to derive expected blueprint names from `PipeType.value_list()` instead of hardcoding the count (the count test was failing once `PipeStructure` was added).
- [x] **Phase 8 — round-out tests.** Done. (Phase 7 intentionally skipped per the plan.) Files added:
  - `tests/unit/pipelex/pipe_operators/pipe_structure/test_pipe_structure_kajson.py` — kajson round-trip for `PipeStructureBlueprint`, `PipeLLMBlueprint` with `structuring_method = preliminary_text`, and every blueprint in an elaborated bundle. (The dedicated `ElaborationMetadata` round-trip case was dropped after review — already covered by `tests/unit/pipelex/core/bundles/test_elaboration_metadata.py`.)
  - `tests/unit/pipelex/core/interpreter/test_interpreter_preliminary_text.py` — `PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=...)` end-to-end, both with and without `structuring_method = "preliminary_text"`.
  - `tests/integration/pipelex/pipes/operator/pipe_structure/test_pipe_structure_in_sequence.py` + `text_then_structure_helpers.mthds` — hand-authored `PipeSequence` wrapping a PipeLLM (text) + a `PipeStructure` step (no elaboration sugar). Live-mode shape assertions on the structured `RestaurantReview` output.
  - `tests/integration/pipelex/pipes/operator/pipe_structure/test_pipe_structure_in_batch.py` — `PipeBatch` iterating a `PipeStructure` over three free-form review texts; live-mode per-item shape assertions on `RestaurantReview`.
  - `tests/integration/pipelex/pipes/operator/pipe_structure/test_preliminary_text_e2e.py` + `preliminary_text_e2e.mthds` — Python-class case. Parametrized over **all three multiplicity forms** (`RestaurantReview`, `RestaurantReview[]`, `RestaurantReview[2]`). Asserts the wrapping pipe is a `PipeSequence`, step-2 is a `PipeStructure`, the run produces a populated typed result, and **exactly two LLM calls are issued** in live mode (one for the draft text, one for the structuring step) via a private-registry helper.
  - `tests/integration/pipelex/pipes/operator/pipe_structure/test_preliminary_text_inline_e2e.py` + `preliminary_text_inline_e2e.mthds` — **Inline-structure case**. Declares a richer `HikingTripReport` concept (12 fields including numbers, integers and several lists of text) entirely via `[concept.HikingTripReport.structure]` — no Python class file. Pipelex generates the backing class at library load. Parametrized over single + dynamic-list output, same 2-LLM-call assertion.
  - **Concept richness.** `RestaurantReview` (Python class in `test_structures_basic.py`) has 8 fields including two `list[str]`. `HikingTripReport` (inline) has 12 fields. The pre-existing `SimpleResult` (title + score) is untouched and still backs the original `test_pipe_structure.py` integration test.
  - **Prompt topics.** All Phase-8 prompts use everyday non-AI topics (restaurants, hiking trails) — no self-references to Pipelex.
  - **PipeStructure in MTHDS not yet supported by `plxt`.** Authoring `type = "PipeStructure"` directly in a `.mthds` file fails plxt schema validation (the bundled schema in `vscode-pipelex/crates/taplo-common/schemas/mthds_schema.json` is from before this PR). The `preliminary_text` path works because the synthesized `PipeStructure` is built in-memory after plxt parsing. Phase 8.3 / 8.4 therefore exercise PipeStructure programmatically. **Follow-up:** ship a plxt release with the regenerated schema so users can author `PipeStructure` directly in MTHDS. Captured in the follow-up TODOs.
  - **Note on the previously-listed Temporal test.** The original Phase 8 bullet for "preliminary_text via Temporal" is dropped: with the runtime change in Phase 6, Temporal sees only the elaborated form (PipeSequence + PipeLLM + PipeStructure), and Temporal's PipeStructure handling rides on the existing PipeOperator path that the Temporal data converter / class registry already cover. Re-add a dedicated Temporal smoke test only if a Temporal-specific bug surfaces.
- [ ] **Phase 9 — docs & changelog.** Not started.
- [ ] **Phase 10 — final validation.** Not started.

### Code-quality decisions made during implementation (audit notes)

- **No premature error types.** `pipe_operators/structure/exceptions.py` was deleted — the operator/factory had no call site that distinguished from generic `PipeRunError` / Pydantic `ValidationError`. Easy to add back when a real raise site appears.
- **No speculative `try/except`.** `pipe_structure.py` initially caught `ValidationError` around `make_object`. PipeLLM's parallel path doesn't catch it (the cogt layer wraps any underlying validation error in `LLMCompletionError`), so the catch was speculative — removed per CLAUDE.md "do not add try/except speculatively."
- **No duplicated factory-level input validation.** `PipeStructureFactory` no longer re-checks `len(blueprint.inputs) == 1`. The blueprint's `model_validator` runs unconditionally on construction; the factory trusts it.
- **`QualifiedRef.parse(...).local_code`** is used in three places (`pipe_structure_blueprint.py`, `pipe_llm_blueprint.py`, `bundle_elaborator.py`) instead of inline `split(".")` — consolidates "extract the local code from a possibly qualified ref" through the existing helper.
- **`StructuringMethod.is_preliminary_text` property** added so call sites read as `method.is_preliminary_text` rather than `method == StructuringMethod.PRELIMINARY_TEXT`.
- **`TypeGuard[PipeLLMBlueprint]`** on `_is_preliminary_text_pipe` eliminates the `# type: ignore[arg-type]` that was bridging `PipeBlueprintUnion → PipeLLMBlueprint` at the elaborator's iteration site.
- **Bundle re-validation pattern.** `BundleElaborator.elaborate` round-trips the new bundle through `model_validate(elaborated.model_dump(by_alias=True))` purely for error detection — the validate result is discarded and the original `model_copy`-built bundle (with its side-table intact) is returned.

### Open questions / observations

- **`StructuringMethod.DIRECT`** kept in the enum per original plan decision. No functional difference from `None` today. Revisit if no second method materializes.

### How to resume

1. `git status` to see uncommitted state — Phase 8 added test modules + two MTHDS fixtures under `tests/integration/pipelex/pipes/operator/pipe_structure/`. Decide whether to commit before Phase 9.
2. Move on to **Phase 9 (docs & changelog)**:
   - Restore / rewrite the structuring docs deleted in `16b775b8` (the old runtime mechanism is gone — the new docs explain the build-time elaboration).
   - Add a `PipeStructure` operator page (mirror the `PipeLLM` page).
   - Document the trade-off: `preliminary_text` produces 2 LLM calls per invocation.
   - Add a `[Unreleased]` entry in `CHANGELOG.md`.
   - Reconcile with the partial docs work already on this branch in commits `bb9bdb32` and `fabb22a2` — review them before adding new content.
3. Then **Phase 10 (final validation)**.
4. **Cross-repo follow-up (out of scope for this PR):** open a PR on `vscode-pipelex` to refresh `crates/taplo-common/schemas/mthds_schema.json` from `derived/mthds_schema.json` (regenerate via `pipelex-dev generate-mthds-schema`) and ship a new `pipelex-tools` release. Without this, `plxt lint` rejects MTHDS files that author `PipeStructure` directly.

---

### CHECKPOINT 3 — end of Phase 8

`structuring_method = preliminary_text` is now exercised end-to-end via the library loader (real-LLM-capable), across all three output multiplicities and across both Python-class and inline-structure concept declarations. `PipeStructure` is also exercised inside hand-authored `PipeSequence` and `PipeBatch`. Kajson round-tripping holds for the synthesized blueprints. Each elaborated run is asserted to issue exactly two LLM calls in live mode. Runtime has no knowledge of `structuring_method`. Tests green, lint/types clean.

State to capture for the next session:

- New MTHDS fixtures under `tests/integration/pipelex/pipes/operator/pipe_structure/`: `text_then_structure_helpers.mthds`, `preliminary_text_e2e.mthds`, `preliminary_text_inline_e2e.mthds`. The earlier `test_structures_basic.mthds` is unchanged.
- New Python concept class `RestaurantReview` (added to `test_structures_basic.py`) is shared by all Python-class Phase-8 tests; the inline `HikingTripReport` is exercised in the inline-structure test.
- All synthetic-pipe assertions reference codes `<parent>__draft_text` / `<parent>__structure` (still the working naming convention — revisit only if length pressure surfaces).
- LLM-call counting uses `ReportingManager._get_or_create_registry(pipeline_run_id).get_current_tokens_usage()` filtered to `LLMTokensUsage`. Helper duplicated across the two e2e test files; if a third consumer appears, hoist it to a shared fixture / utility.
- One ergonomics gap surfaced: the bundled plxt schema (in `vscode-pipelex/crates/taplo-common/schemas/mthds_schema.json`) does not yet include `PipeStructure`. The `preliminary_text` path is unaffected because the synthesized `PipeStructure` lives in-memory only. Captured as a Phase 9 cross-repo follow-up.

---

## Goal

Bring back the "text-then-object" capability that was removed in `16b775b8`, but in a fundamentally different shape:

- Introduce a first-class `PipeStructure` operator (`Text → StructuredConcept`).
- Add a bundle **elaboration pass** in `pipelex/core/interpreter/` that runs after parsing and before the runtime pipe construction. When it sees a `PipeLLMBlueprint` with `structuring_method = preliminary_text`, it rewrites that single pipe into a `PipeSequence[PipeLLM(text), PipeStructure]`. Synthetic pipes are tracked in a **bundle-level side-table** so the language surface stays clean.
- The runtime layer (`PipeLLM`, cogt, Temporal) never sees `structuring_method` anymore — it is purely a **build-time directive**.

This keeps every downstream layer simple and gives users a reusable structuring operator they can also call directly when text comes from elsewhere (extracted PDFs, search results, user input).

## Architectural decisions locked in (from review)

- **Synthetic-pipe metadata lives on the bundle, NOT on every pipe.** A new `PipelexBundleBlueprint.elaboration_metadata: dict[str, ElaborationMetadata] | None` side-table stores the synthetic→parent mapping. The base `PipeBlueprint` and runtime `PipeAbstract` do NOT get a `parent_pipe_code` field. This keeps the user-facing pipe schema unpolluted and makes the elaboration concern strictly internal.
- **PipeStructure's user-prompt template is config-driven.** Defined under `[cogt.llm_config.generic_templates]` next to `output_structure_prompt`, retrievable via `llm_config.get_template(template_name="structuring_prompt")`. Default text shipped in `pipelex.toml`. No hardcoded prompt inside the operator.
- **PipeStructure accepts any Text-compatible concept.** Validation uses `Concept.are_concept_compatible(strict=False)` so domain concepts that `refines = Text` (e.g. `business.RawDocument`) work without an extra cast pipe. The elaboration path always passes literal `Text`.
- **Multiplicity rule (matches deleted-code behavior).** Step-1 always produces a **single** `Text`; step-2 (`PipeStructure`) produces the list when the original output was `Foo[]` or `Foo[N]`. Confirmed by reading `make_text_then_object_list` at `16b775b8^:pipelex/pipe_operators/llm/pipe_llm.py`.
- **Phase 7 is dropped entirely from this PR.** No synthetic-pipe marker, no friendly rendering, no CLI exclusion. Synthetic pipes appear as regular pipes in logs/traces/graph viewer until the follow-up TODOs land. The `bundle.elaboration_metadata` side-table is the durable source of truth that downstream tools can read whenever they're wired up. Keeps this PR focused on the language and runtime change.
- **`StructuringMethod.DIRECT` is kept as-is.** Functionally a no-op identical to `None`, but kept in the enum for language symmetry and future extensibility. Documented in Open Questions for future revisit.

## Non-goals (explicitly deferred)

- A generic "meta-pipe" framework for arbitrary build-time expansions. We build the one elaboration pass needed today; the abstraction can be extracted once a second concrete need appears.
- Per-step prompt customization for `structuring_method`. If users want fine control, they author the two pipes by hand using `PipeLLM` + `PipeStructure`.
- Image inputs on `PipeStructure`. v1 takes Text only; image-aware structuring stays in `PipeLLM`.
- Friendly synthetic-pipe rendering across logs, traces, and graph viewer. Captured as a follow-up TODO at the end of this file.
- Any synthetic-pipe marker on graph node tags or CLI listings. Also a follow-up TODO.

---

## Phase 1 — Foundations: bundle-level elaboration metadata

A side-table on the bundle blueprint records which synthesized pipes belong to which user-authored pipe and what role they play. Nothing leaks onto the per-pipe blueprint surface or onto the runtime pipe object.

- [ ] In `pipelex/core/bundles/pipelex_bundle_blueprint.py`:
  - [ ] Add a `StepRole(StrEnum)` (or `Literal`) enum with `DRAFT_TEXT = "draft_text"` and `STRUCTURE = "structure"`. Use the StrEnum pattern per `pipelex.types`.
  - [ ] Add an `ElaborationMetadata(BaseModel)` model with `parent_pipe_code: str` and `step_role: StepRole`.
  - [ ] Add `elaboration_metadata: dict[str, ElaborationMetadata] | None = Field(default=None, exclude=True)` to `PipelexBundleBlueprint`. The `exclude=True` ensures it is never serialized back to MTHDS / TOML / JSON.
  - [ ] Add a small accessor: `def get_elaboration_for(pipe_code: str) -> ElaborationMetadata | None`.
- [ ] Confirm by read-through of `library_manager.py` callers that the bundle blueprint is never re-serialized to disk after construction. If any code path does (`pipelex export`, builder helpers, etc.), audit it to make sure `elaboration_metadata` is dropped on output. The `exclude=True` should make this automatic, but verify.
- [ ] Unit test: `ElaborationMetadata` round-trips through `model_dump` / `model_validate`. `model_dump` of a `PipelexBundleBlueprint` with `elaboration_metadata` set produces output that has NO `elaboration_metadata` key (excluded).

---

## Phase 2 — `PipeStructure` operator (runtime + blueprint + factory)

A minimal operator: one Text-compatible input, one structured output, one LLM call in the middle.

- [ ] Add the structuring prompt template to `pipelex/pipelex.toml` under `[cogt.llm_config.generic_templates]`, alongside `output_structure_prompt`. Default body roughly:

  ```toml
  structuring_prompt = """
  Read the following text carefully and produce the requested structured output from it.

  ---
  {{ text }}
  """
  ```

- [ ] Create `pipelex/pipe_operators/structure/` with:
  - [ ] `__init__.py`
  - [ ] `exceptions.py` defining `PipeStructureError(PipelexError)`, `PipeStructureFactoryError(PipelexError)`.
  - [ ] `pipe_structure_blueprint.py` defining `PipeStructureBlueprint(PipeBlueprint)`:
    - `type: Literal["PipeStructure"] = "PipeStructure"`
    - `pipe_category: Literal["PipeOperator"] = "PipeOperator"`
    - `model: LLMModelChoice | None = None` — the structuring model (analog of `model_to_structure`).
    - `validate_inputs()` enforces exactly one input, and that input's concept must be **Text-compatible** (use `concept_library.is_compatible(tested_concept=..., wanted_concept=native.Text)` — equivalent to `strict=False`).
    - `validate_output()` enforces the output is NOT Text-compatible (i.e. structured concept).
  - [ ] `pipe_structure.py` defining `PipeStructure(PipeOperator[PipeStructureOutput])`:
    - Holds `llm_choice: LLMModelChoice | None`, `text_input_name: str`, `output_multiplicity: VariableMultiplicity | None`.
    - `_live_run_operator_pipe`:
      1. Resolve the input `Text` from `working_memory` by `text_input_name`.
      2. Render the structuring user prompt by loading `cogt.llm_config.get_template(template_name="structuring_prompt")` and substituting `{{ text }}` with the input's text content.
      3. Append the schema via `get_output_structure_prompt(...)` from `pipelex/pipe_operators/llm/helpers.py` (the same helper PipeLLM uses).
      4. Resolve the LLM setting with the same precedence as PipeLLM: `self.llm_choice → llm_choice_overrides.for_object → llm_choice_defaults.for_object`.
      5. Use `output_multiplicity_to_apply` to resolve list vs single, then call `content_generator.make_object` or `content_generator.make_object_list` with `nb_items` from the multiplicity.
      6. Wrap in `PipeStructureOutput`.
      7. `_register_execution_data(...)` with `{"resolved_model": ..., "is_multiple_output": ..., "rendered_user_prompt": ..., "structuring_path": "structure"}`.
    - `_dry_run_operator_pipe` mirrors PipeLLM's pattern: delegate to `_live_run_operator_pipe(..., content_generator=ContentGeneratorDry())`. **This bullet is mandatory — without it, dry-run tests will fail.**
    - `validate_inputs_static`, `validate_inputs_with_library`, `validate_output_static`, `validate_output_with_library`: implement to mirror the PipeLLM analogues, minus image / document concerns.
    - `needed_inputs()` returns the single Text input.
    - `required_variables()` returns `{self.text_input_name}` (PipeStructure has no user template variables; the structuring template's only var is `text`, fed from working memory).
  - [ ] `pipe_structure_factory.py` defining `PipeStructureFactory(PipeFactoryProtocol[PipeStructureBlueprint, PipeStructure])`:
    - Resolve LLM choice from `blueprint.model`.
    - Parse output multiplicity from `blueprint.output` (single `Foo`, `Foo[]`, `Foo[N]`).
    - Resolve `text_input_name` from `inputs` (must be exactly one).
    - **No template analysis** (no image refs, no document refs — PipeStructure has no user-controlled prompt). This is intentionally simpler than `PipeLLMFactory`.
- [ ] Register `PipeStructureBlueprint` in `PipeBlueprintUnion` (`pipelex/core/bundles/pipelex_bundle_blueprint.py`).
- [ ] Register `PipeStructure` and `PipeStructureFactory` in:
  - [ ] `pipelex/core/registry_models.py` → append to `CoreRegistryModels.PIPE_OPERATORS` and `PIPE_OPERATORS_FACTORY`. The class-registry lookup key is `"PipeStructureFactory"` (computed by `pipe_factory.py:108` as `f"{pipe_type.value}Factory"`).
  - [ ] `pipelex/core/pipes/pipe_blueprint.py` `PipeType` enum → add `PIPE_STRUCTURE = "PipeStructure"` and the corresponding `category` mapping in the match statement (must be exhaustive — no default case allowed).
- [ ] Audit Temporal data converter / kajson allow-lists. From inspection, `pipelex/temporal/temporal_data_converter.py` does not enumerate pipe types directly; it uses the global class registry. Confirm registration via `CoreRegistryModels` is sufficient.
- [ ] Unit tests in `tests/unit/pipelex/pipes/operator/pipe_structure/test_pipe_structure.py`:
  - Blueprint validation rejects non-Text-compatible input.
  - Blueprint validation accepts a domain concept that `refines = Text`.
  - Blueprint validation rejects Text output.
  - Factory produces a runtime `PipeStructure` with the right model choice and output multiplicity for `Foo`, `Foo[]`, `Foo[N]`.
  - Long pipe_code edge case: declare a `PipeStructure` with a maximally long valid snake_case pipe_code; confirm the factory and runtime construct successfully.
  - Dry-run: `_dry_run_operator_pipe` produces a dry-run output without LLM calls.
- [ ] Integration test running `PipeStructure` end-to-end on a small fixture concept (use the existing `inference` / `llm` markers).

---

### CHECKPOINT 1

`PipeStructure` exists as a standalone, directly-usable operator. A `.mthds` file can declare a `PipeStructure` pipe and run it. Elaboration not introduced yet. `make agent-check` and `make agent-test` are green.

State to capture in this file at checkpoint time:

- File paths created.
- Open questions that surfaced during implementation.
- Anything deferred to later phases.

---

## Phase 3 — `PipeStructureSpec` (authoring layer)

Mirror the operator at the spec layer so AI builders authoring via specs can declare it.

- [ ] Create `pipelex/builder/pipe/pipe_structure_spec.py` defining `PipeStructureSpec(PipeSpec)`:
  - `type: SkipJsonSchema[Literal["PipeStructure"]] = "PipeStructure"`
  - `pipe_category: SkipJsonSchema[Literal["PipeOperator"]] = "PipeOperator"`
  - `model: str | None = Field(default=None, description="...")`
  - `to_blueprint()` returning `PipeStructureBlueprint`.
  - `rendered_pretty()` consistent with the other spec classes.
- [ ] Add `PipeStructureSpec` to `PipeSpecUnion` in `pipelex/builder/pipe/pipe_spec_union.py`.
- [ ] Add `PipeStructureSpec` to `pipelex/builder/pipe/pipe_spec_map.py` if that mapping exists.
- [ ] Unit test for the spec → blueprint round-trip.

---

## Phase 4 — Bundle elaboration framework

Add the elaboration pass infrastructure, kept narrow on purpose. No generic plugin system yet.

- [ ] Create `pipelex/core/interpreter/bundle_elaborator.py`:
  - [ ] `BundleElaboratorError(PipelexInterpreterError)` exception type.
  - [ ] `class BundleElaborator` with a single classmethod `elaborate(bundle: PipelexBundleBlueprint) -> PipelexBundleBlueprint`.
  - [ ] **Fast-path short-circuit**: scan bundle for any `PipeLLMBlueprint` with `structuring_method == StructuringMethod.PRELIMINARY_TEXT`. If none found, return the input bundle unchanged. **This avoids per-bundle dump/validate overhead in the common case.**
  - [ ] When elaboration is needed, build a NEW `PipelexBundleBlueprint` (don't mutate input). Copy `domain`, `description`, `system_prompt`, `main_pipe`, `concept`, `source` over; rebuild `pipe` dict by walking each entry; populate `elaboration_metadata` with one entry per synthetic pipe inserted.
  - [ ] Internal helpers per elaboration kind. v1 has only `_elaborate_preliminary_text` (Phase 5), but the dispatch is structured so adding more is mechanical.
  - [ ] **Recursive-elaboration guard**: after elaboration, assert that no synthetic blueprint contains a `preliminary_text` directive itself. Raise `BundleElaboratorError` if violated. Cheap defense in depth — protects against future mistakes when adding new elaboration kinds.
  - [ ] **Post-elaboration re-validation**: after producing the new bundle dict, call `PipelexBundleBlueprint.model_validate(elaborated.model_dump(...))` once more to re-run bundle-level validators (`validate_local_concept_references`, `validate_local_pipe_references`, `validate_main_pipe`) against the synthetic pipes. Wrap any `ValidationError` in `BundleElaboratorError` with context naming which synthetic pipe triggered it. Skip when the fast-path short-circuit fired.
- [ ] Wire elaboration into `PipelexInterpreter.make_pipelex_bundle_blueprint()` in `pipelex/core/interpreter/interpreter.py`. After the existing `model_validate(blueprint_dict)` and `pipelex_bundle_blueprint.source = ...`, call `BundleElaborator.elaborate(...)` and return the elaborated bundle. Errors raised by the elaborator must surface as `PipelexInterpreterError` with clear context (which pipe, which directive).
- [ ] Verify all callers of `make_pipelex_bundle_blueprint()` (in `library_manager.py` lines 363, 697, 909) still work; the contract is unchanged from their perspective.
- [ ] Unit tests in `tests/unit/pipelex/core/interpreter/test_bundle_elaborator.py`:
  - Vanilla bundle (no `preliminary_text`, contains `PipeLLM`, `PipeFunc`, `PipeImgGen` mix) → elaborator returns the input unchanged (use `is` identity check to confirm short-circuit, not just equality).
  - Empty `bundle.pipe = None` or `{}` → no crash, returns unchanged.
  - Recursive-elaboration guard fires when a synthetic blueprint is artificially given `preliminary_text` (test the guard itself).

---

## Phase 5 — `preliminary_text` elaboration

Implement the actual rewrite. This is the meat of the change.

- [ ] In `BundleElaborator._elaborate_preliminary_text`, given an entry `(pipe_code, PipeLLMBlueprint)` with `structuring_method = preliminary_text`:
  - [ ] **Pre-checks** (raise `BundleElaboratorError` with good context on failure):
    - [ ] Output concept must NOT be Text-compatible. (Today this is a runtime check in `pipe_llm.py:66`; move it here with a clear message tying back to the user's pipe code.)
    - [ ] No collision: synthetic codes (`<pipe_code>__draft_text`, `<pipe_code>__structure`) must not already exist in `bundle.pipe`.
    - [ ] Synthetic codes must pass `is_pipe_code_valid` (snake_case check). Raise with a clear message if the original `pipe_code` is so long that the suffixed synthetic code becomes invalid.
  - [ ] **Synthesize step-1**: a `PipeLLMBlueprint` keyed at `<pipe_code>__draft_text`:
    - `inputs = original.inputs` (all of them — including any image inputs the user declared).
    - `system_prompt = original.system_prompt` (verbatim).
    - `prompt = original.prompt` (verbatim).
    - `model = original.model` (verbatim).
    - `model_to_structure = None` (step-1 produces Text, no structuring needed).
    - `output = "Text"` — **always single Text**, never `Text[]` or `Text[N]`. This matches the deleted code's `make_text_then_object_list` behavior, where one preliminary text was structured into N objects.
    - `structuring_method = None`.
    - `description = f"Draft text for {pipe_code}"`.
  - [ ] **Synthesize step-2**: a `PipeStructureBlueprint` keyed at `<pipe_code>__structure`:
    - `inputs = {"draft_text": "Text"}`.
    - `output = original.output` (preserves multiplicity: `Foo`, `Foo[]`, or `Foo[N]`).
    - `model = original.model_to_structure` (may be `None` → step-2 falls back to `model_deck.llm_choice_overrides.for_object` at runtime; this is identical to the old PipeLLM behavior when `model_to_structure` was not set).
    - `description = f"Structure step for {pipe_code}"`.
  - [ ] **Synthesize the wrapping sequence**: a `PipeSequenceBlueprint` keyed at the original `pipe_code`:
    - `inputs = original.inputs`.
    - `output = original.output`.
    - `description = original.description`.
    - `steps = [SubPipeBlueprint(pipe="<code>__draft_text", result="draft_text"), SubPipeBlueprint(pipe="<code>__structure", result=<original_result_or_pipe_code>)]`.
    - Step references use **bare codes** (no domain prefix), per the bundle's same-domain reference convention.
  - [ ] Insert all three blueprints into the new `pipe` dict (replacing the original entry at `pipe_code`).
  - [ ] Register two entries in `elaboration_metadata`:
    - `<pipe_code>__draft_text → ElaborationMetadata(parent_pipe_code=pipe_code, step_role=DRAFT_TEXT)`.
    - `<pipe_code>__structure → ElaborationMetadata(parent_pipe_code=pipe_code, step_role=STRUCTURE)`.
    - The wrapping sequence is NOT registered — it's the user-facing pipe.
- [ ] **Image-input handling**: deliberately do NOT add explicit drop logic. Step-2's input dict is `{"draft_text": "Text"}` and step-2's prompt template is the canned `structuring_prompt`, which references only `{{ text }}`. Any image variables on the original prompt naturally flow only to step-1, where they belong. Document this in a code comment in `_elaborate_preliminary_text` so future maintainers understand the mechanism.
- [ ] Unit tests in `tests/unit/pipelex/core/interpreter/test_bundle_elaborator.py`:
  - [ ] Bundle with one `preliminary_text` PipeLLM produces the expected three-pipe structure (one PipeSequence + two synthetic pipes) and two `elaboration_metadata` entries.
  - [ ] Output `Text` raises `BundleElaboratorError` with a message naming the user's pipe code.
  - [ ] Output `Text`-compatible concept (refines Text) ALSO raises `BundleElaboratorError`.
  - [ ] Synthetic-name collision raises `BundleElaboratorError`.
  - [ ] Multiplicity preserved for `Foo`, `Foo[]`, `Foo[N]`. Step-1's output is always literal `Text` (single), regardless of original output's multiplicity.
  - [ ] Image input present on original → declared on step-1's `inputs`, NOT declared on step-2's `inputs`.
  - [ ] `model_to_structure = None` on original → step-2 has `model = None` (defaults applied at runtime).
  - [ ] `main_pipe = "<pipe_code>"` pointing at the original `preliminary_text` pipe → still resolves correctly post-elaboration (the original code is now the wrapping sequence). This is a **mandatory regression test** per review.
  - [ ] Long pipe_code edge case: original pipe_code at the boundary of `is_pipe_code_valid` length → either passes or fails with a clear message.
  - [ ] Bundle without `preliminary_text` is unchanged (identity check confirming short-circuit).
- [ ] Integration test (`tests/integration/...`) running an end-to-end `preliminary_text` PipeLLM through a real LLM call, asserting the structured output is valid. Use `inference` and `llm` markers.

---

### CHECKPOINT 2

`structuring_method = preliminary_text` works end-to-end via elaboration. Tests green. The runtime layer still has the legacy field on `PipeLLM` though — Phase 6 cleans it.

State to capture:

- Final synthetic naming convention chosen (`__draft_text` / `__structure` is the working assumption — see Open Questions).
- Multiplicity confirmed as "single Text → list" (matches deleted code).
- Any blockers found in the existing factories or registries.

---

## Phase 6 — Remove `structuring_method` from runtime `PipeLLM`

The field is now purely a build-time directive. The runtime should not know about it.

- [ ] Remove `structuring_method: StructuringMethod | None = None` from `PipeLLM` (`pipelex/pipe_operators/llm/pipe_llm.py:61`).
- [ ] Remove the `validate_output_concept_consistency` validator (`pipe_llm.py:64-72`) — the elaborator now owns this check.
- [ ] Remove the `if self.structuring_method is not None:` block in `_live_run_operator_pipe` (the `NotImplementedError` raise site at `pipe_llm.py:190-199`).
- [ ] Remove the `structuring_method` line in `execution_data_dict` near `pipe_llm.py:338-339`.
- [ ] In `PipeLLMFactory.make()` (`pipe_llm_factory.py:148`): stop passing `structuring_method=blueprint.structuring_method` to the `PipeLLM(...)` constructor.
- [ ] Keep `structuring_method` on `PipeLLMBlueprint` — it remains part of the language surface and is consumed by the elaborator. Add a `model_validator(mode="after")` on `PipeLLMBlueprint` that enforces the same rule the elaborator does: `structuring_method != PRELIMINARY_TEXT or output is not Text-compatible`. Raise plain `ValueError` (Pydantic convention; `PipelexInterpreter` already wraps `ValidationError` into `PipelexInterpreterError` with categorized error data). Authoring-time errors then surface during `model_validate`, before the elaborator runs. The elaborator's own check stays as defense in depth.
- [ ] Add `structuring_method: StructuringMethod | None = None` field to `PipeLLMSpec` (`pipelex/builder/pipe/pipe_llm_spec.py`) so AI builders can opt in. Use plain `Field(default=None, description="...")` — **NOT** `SkipJsonSchema` — so the field appears in the JSON schema given to AI agents.
- [ ] Update `PipeLLMSpec.to_blueprint()` to forward the field.
- [ ] Run `make agent-check` and verify the `StructuringMethod` enum is still imported only where it's used (the blueprint, the spec, the elaborator).

---

## Phase 7 — Skipped

All trace/log/CLI/graph-viewer integration work is deferred to follow-up TODOs at the bottom of this file. The runtime stays unaware of which pipes are synthetic; only `bundle.elaboration_metadata` knows. Downstream tools can opt in later by consulting that side-table when they load bundles.

**Do not add anything to this phase.** Anything that would touch tracer / CLI / graph viewer / run reporting belongs in the follow-up TODO list, not here.

---

## Phase 8 — Round-out tests

Belt-and-suspenders coverage.

- [ ] Test: running the same `preliminary_text` PipeLLM via Temporal works (elaboration runs once at bundle load; Temporal sees only the expanded form). Use the existing Temporal integration test infrastructure.
- [ ] Test: kajson serialization of the elaborated bundle (or its individual synthetic pipes) round-trips correctly. Specifically, confirm `PipeStructureBlueprint` and `PipeLLMBlueprint` round-trip through `kajson.dumps` / `kajson.loads`.
- [ ] Test: an MTHDS file with `structuring_method = "preliminary_text"` validates and parses (not just programmatic blueprints). Add a fixture `.mthds` file under `tests/...`.
- [ ] Test: directly using `PipeStructure` in a hand-written `PipeSequence` (independent of the elaboration sugar).
- [ ] Test: `PipeStructure` inside a `PipeBatch` — process a list of texts, structuring each into a `Foo`. This is a common composition users will reach for.
- [ ] Test: confirm the "no preliminary_text → no behavior change" guarantee — the existing PipeLLM test suite passes unchanged. **Mandatory regression gate.**
- [ ] Test: an MTHDS file that previously failed with `NotImplementedError` (the current behavior in `pipe_llm.py:194-197`) now succeeds. Delete the old negative-case test that asserted that NotImplementedError, if any exists.

---

## Phase 9 — Documentation & changelog

- [ ] Add a docs page for `PipeStructure` under the operators section (mirror the structure of the `PipeLLM` page). Cover: what it does, when to use it, inputs / outputs, model choice, examples (including text-from-PDF and text-from-search-results scenarios).
- [ ] Restore / rewrite the structuring docs that were deleted in `16b775b8` (the deleted file was `*/llm-structured-generation-config.md` per that commit's stat). New version explains the build-time elaboration behavior, NOT the old runtime mechanism. Show before/after of what the user writes vs what runs.
- [ ] Note in the docs: `preliminary_text` produces 2 LLM calls per invocation (text + structure). Document the trade-off vs single-call structuring.
- [ ] Add an entry under `[Unreleased]` in `CHANGELOG.md` summarizing: new `PipeStructure` operator, `structuring_method = preliminary_text` works again, runtime simplification.
- [ ] Cross-check `mkdocs.yml` includes any new doc pages.
- [ ] Reconcile with the partial docs work already on this branch in commits `bb9bdb32` and `fabb22a2` — review them before adding new content to avoid duplication.

---

## Phase 10 — Final validation

- [ ] `make agent-check` (lint + types) clean.
- [ ] `make agent-test` (full test suite) clean.
- [ ] Manually run a small `.mthds` example using `structuring_method = preliminary_text` and a separate one using `PipeStructure` directly. Confirm both produce structured output.
- [ ] Spot-check a graph trace for a `preliminary_text` run — synthetic pipes will appear as regular nodes for now (no marker). Confirm the run completes successfully and the output structure matches the user's declared output concept. Note any rendering oddities for the follow-up TODOs.
- [ ] Update this `TODOS.md` with any deviations from the plan and remaining follow-ups.

---

## Open questions to revisit during implementation

- **Synthetic-name pattern**: `__draft_text` / `__structure` (descriptive) vs shorter (`__t` / `__s`). Plan assumes descriptive. Revisit only if pipe-code length becomes a real problem in practice.
- **`StructuringMethod.DIRECT` enum value**: kept for symmetry per decision during planning. Functionally identical to `None`. Revisit if the enum stays single-meaningful-value for too long without a second method appearing.
- **Recursive elaboration**: v1 only expands the top-level `bundle.pipe` dict and explicitly guards against synthetic blueprints containing `preliminary_text` (Phase 4 guard). If a future elaboration kind needs fixed-point iteration, lift that guard into a proper iteration loop.
- **`PipeStructure` direct-usage validation strictness**: plan accepts any Text-compatible concept. If users frequently misuse this with concepts that *technically* refine Text but are semantically not text-like, tighten later.

---

## Follow-up TODOs (out of scope for this PR)

These are captured here for project tracking; they should be moved to wherever the team tracks deferred work after this PR lands.

1. **Synthetic-pipe marker on graph node tags + CLI listing exclusion.** Smallest follow-up: when emitting `NodeSpec`, look up `bundle.elaboration_metadata.get(self.code)` and, if present, set `tags["synthetic"] = "true"` and `tags["parent_pipe_code"] = parent`. Plumbing question: the graph tracer doesn't currently have direct access to the bundle, so this needs either (a) an optional runtime-only field on `PipeAbstract` populated by the factory, or (b) a side-registry keyed by pipe code. Also: hide synthetic pipes from `pipelex list`-style CLI surfaces. Cheap, ~2–3 file edits.

2. **Friendly synthetic-pipe rendering across logs, traces, and run-reporting.** After (1) lands, render `<parent_pipe_code> [<step_role_label>]` everywhere `self.code` appears in observability surfaces. Touches: graph_tracer, run_reporting, journal, distributed-tracing files. Estimate ~5–8 file edits. Driver: observability UX.

3. **`mthds-ui` graph viewer integration.** After (1) ships the `tags["synthetic"]` API, decide in the UI repo whether to nest synthetic pipes under their parent or hide them entirely. Requires `mthds-ui` repo work that this PR does not block on.

4. **Bundle-load benchmark in CI.** Microbenchmark library load time on a representative library set; alert on >5% regression. Protects against future elaboration-pass additions silently slowing startup.

5. **PipeStructure image input support.** When a concrete need arises (e.g. structure a PDF page image into an invoice without an intermediate `PipeExtract`), extend `PipeStructure` to accept an optional image input alongside the Text input. Out of scope for v1 to keep the operator narrow.

6. **Per-step prompt customization for `structuring_method = preliminary_text`.** If users complain that the canned `structuring_prompt` is wrong for their domain, expose a per-pipe override on `PipeLLMBlueprint` that gets propagated to the synthesized step-2. Don't build until requested.

7. **Generic meta-pipe / build-time elaboration framework.** When a SECOND build-time elaboration directive appears, promote `BundleElaborator._elaborate_preliminary_text` into a registry of elaboration plugins. Today's narrow shape is intentional.

8. **`pipelex-dev elaborate-bundle <path>`** debugging CLI to print the elaborated form of a bundle without running it. Helpful when diagnosing weird behavior. Low priority.

9. **Revisit `StructuringMethod.DIRECT`** — currently kept for symmetry. If a year passes with no second method materializing and no consumer for `DIRECT`, delete it.
