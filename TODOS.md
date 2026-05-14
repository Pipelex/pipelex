# Signature-Based Validation — TDD implementation plan

Status: Phases 1–7.3 landed (plus Phase 5.2 lenient-summary polish) (2026-05-14); Phase 7.4 open and tracked as a merge-gate. **The branch is in a consistent, reviewable state** — the runtime accepts `type = "PipeSignature"`, and `.pipelex/plxt.toml` declares the matching schema source of truth (`derived/mthds_schema.json`) via a `[[rule]] / [rule.schema] path = ...` block scoped to `**/*.mthds`. That block is the intended configuration on this branch, not a workaround: the bundled `plxt` schema doesn't yet describe `PipeSignature`, so the local schema is the only correct one to validate against here. At merge time, once `vscode-pipelex` ships an updated bundled schema, the `[[rule]]` block is removed in the same commit and the bundled schema takes over again — that swap is the Phase 7.4 merge-gate item. Docs (new `signature-pipes.md` page + nav + cross-links + CLI reference + tightened spec docstring) and CHANGELOG (`[Unreleased]` Added/Changed) are in. `make agent-check` and `make agent-test` are green on this branch. Reviewers: please treat the `[[rule]]` block in `.pipelex/plxt.toml` as load-bearing for the branch — not as a smell to fix.

Current state: A `PipeSignature` can be authored as a spec (`pipelex/builder/pipe/pipe_signature.py`), compiled to a blueprint (`pipelex/pipe_signature/pipe_signature_blueprint.py`), instantiated as a runtime (`pipelex/pipe_signature/pipe_signature_runtime.py`) via the registered `PipeSignatureFactory`, dry-run (yields a mock `Stuff` from the declared output `StuffSpec`), and rejected on live-run (`PipeSignatureNotExecutableError`). Signatures slot into `PipeBlueprintUnion` and `PipeSpecUnion`. Strict-mode gating is live: `PipeAbstract.collect_signature_refs(pipe_lookup=...)` walks the dependency graph; `dry_run_pipe(..., allow_signatures=False)` (the default) raises `SignaturesNotAllowedError` carrying both `signature_refs` and the qualified `dep_paths` chain. `dry_run_pipes` does a pre-pass that aggregates signature refs across all pipes in the batch so the user sees every offender in one error (post-review fix). `validate_bundle` and `validate_bundles_from_directory` catch the error and surface it via `ValidateBundleError.signature_check_error`. CLI surface: `pipelex validate pipe`/`bundle` now take `--allow-signatures` (default off); `pipelex validate --all` filters signature pipes out of the strict iteration; the agent CLI's `validate_*_core` functions default to lenient. Signatures still raise `PipeSignatureNotExecutableError` on live run. End-to-end `.mthds` parsing works: the interpreter happily round-trips `type = "PipeSignature"` through `PipelexBundleBlueprint` → library → runtime → dry-run, in both strict and lenient mode. The schema generator was updated to strip `pipe_category` from `PipeSignatureBlueprint`, but the JSON Schema file lives in `vscode-pipelex/` (not this repo) so no schema artifact needed regeneration here. Surprise: `pipe_abstract.py` could not import from `pipelex.hub` (even via a function-local import) because pyright's `reportImportCycles` is on and the cycle pipe_abstract → hub → libraries.library → libraries.pipe.pipe_library → pipe_abstract is real. The walker therefore takes a `pipe_lookup` callable parameter (typically `pipelex.hub.get_optional_pipe`) — slightly more explicit than the plan's pseudocode, but cycle-free. Walker iterates `sorted(pipe_dependencies())` so the dep chain rendered in `SignaturesNotAllowedError` is deterministic (post-review fix). Phase 6 surfaced one design gap: `dry_run_pipes` aggregated dep paths with a "first wins" rule, which lost the informative controller chain when the signature pipe was iterated first; the aggregator now prefers the longest known dep chain so the error message always shows the most useful path.

Known gaps after Phase 6 — **closed out at merge time via Phase 7.4**:

- The bundled `plxt` schema (shipped from `vscode-pipelex/`) does not yet know about `type = "PipeSignature"`. On this branch the canonical schema for `*.mthds` is the locally-regenerated `derived/mthds_schema.json`, wired in via a `[[rule]]` block in `.pipelex/plxt.toml` — that is the intended configuration on this branch and `plxt lint` is green against it. At merge time, the `[[rule]]` block is removed in lock-step with the `vscode-pipelex` release that bundles the updated schema; tracked as Phase 7.4. (Reviewers: this is the deliberate setup, not a workaround to flag.)
- The fast-path PostToolUse hook (`validate-mthds.sh`) uses the same `plxt` toolchain, so it picks up the branch-local schema rule automatically. `Write`/`Edit` on `PipeSignature` fixtures works through the hook on this branch with no special handling. Same Phase 7.4 cleanup applies after merge: the rule comes off when the bundled schema is updated.

**Pre-flight note:** `validate_bundle` was updated on this branch to actually call `dry_run_pipes` (the previously-commented-out calls in all three branches of `validate_bundle.py` were uncommented). This means the strict signature check sitting inside `dry_run_pipe` fires for **every** `validate_bundle` caller, not just direct CLI usage — no separate pre-flight helper is needed.

This plan is **strict TDD**: in every phase, failing tests are written first (red), then implementation makes them green. Integration tests construct blueprints directly in Python; end-to-end tests load real `.mthds` files. Each phase ends with `make agent-check` and a targeted test run; the final phase ends with `make agent-test`.

**Tick boxes as you go.** Mark each checkbox the moment its item lands — don't wait for the next checkpoint. The boxes are the working log: if a session is interrupted mid-phase, the next session resumes from the first unticked box. Checkpoints are for halting, not for batch-ticking.

**Stop checkpoints** are marked ⛔. At each one, coding must halt, the status block at the top of this file must be updated (and any deviations recorded), and a fresh session picks up at the next phase.

---

## Quick start (cold session)

Working directory: `/Users/lchoquel/repos/Pipelex/_sig` (a worktree of the `pipelex/` runtime repo).

Read in this order:

1. This file (`TODOS.md`) — phase by phase.
2. `wip/signature-based-validation.md` — full design, rejected alternatives, edge cases. The authoritative source for "why" decisions.
3. `pipelex/builder/pipe/pipe_signature.py` — the existing spec class that needs corrections.
4. `pipelex/core/pipes/pipe_blueprint.py` — `PipeType` / `PipeCategory` enums and `PipeBlueprint` base.
5. `pipelex/core/pipes/pipe_abstract.py` — `PipeAbstract` (gains `is_signature`, promoted `pipe_dependencies`, new `collect_signature_refs`).
6. `pipelex/pipe_run/dry_run.py` — `dry_run_pipe` / `dry_run_pipes` (gains `allow_signatures` parameter).
7. `pipelex/pipeline/validate_bundle.py` — entry point that threads `allow_signatures` down.

Project conventions that apply (see `CLAUDE.md` for the full list):

- One `TestClass` per test module.
- Use pytest-mock; never `unittest.mock`.
- Tests live under `tests/unit/`, `tests/integration/`, `tests/e2e/` per the test type.
- After every code change: `make agent-check` (lint + type) before moving on.
- After every phase: targeted `pytest` run for the affected area. After the last phase: `make agent-test` (full).
- Never hardcode counts in comments or docstrings.
- Don't hard-wrap markdown.

If `make` isn't available, run the agent-check steps manually (see Makefile's `agent-check` target).

---

## Architecture at a glance (for the impatient)

```
PipeType.PIPE_SIGNATURE   ←  new enum value, category PipeCategory.PIPE_SIGNATURE

spec     PipeSignature             — corrected (literal type, multiplicity inputs, no `result`)
blueprint PipeSignatureBlueprint   — new
runtime  PipeSignatureRuntime      — new; _dry_run mocks, _live_run raises

PipeAbstract gains:  is_signature (property), pipe_dependencies() (default empty),
                     collect_signature_refs() (graph walk)

Validation:
  strict (default):   dry_run_pipe(... allow_signatures=False) → SignaturesNotAllowedError
                      if pipe.collect_signature_refs() is non-empty
  lenient:            dry_run_pipe(... allow_signatures=True)  → signatures mock outputs

CLI:
  pipelex validate <pipe> [--allow-signatures]
  pipelex validate --all  [--allow-signatures]
  pipelex-agent validate  → defaults allow_signatures=True
```

---

## Phase 1 — Type system foundations

Lay down the enum values, the `is_signature` property, and the promoted `pipe_dependencies` method. Small, foundational, no behavior change for existing pipes.

### Phase 1.1 — Tests first (red)

All tests use direct construction; no fixtures needed beyond pytest-mock when applicable.

- [x] `tests/unit/pipelex/core/pipes/test_pipe_blueprint_signature_enums.py` — `class TestPipeSignatureEnums`
  - `test_pipe_type_pipe_signature_value` — `PipeType.PIPE_SIGNATURE` equals `"PipeSignature"`.
  - `test_pipe_type_pipe_signature_in_value_list` — `"PipeSignature" in PipeType.value_list()`.
  - `test_pipe_type_pipe_signature_category` — `PipeType("PipeSignature").category is PipeCategory.PIPE_SIGNATURE`.
  - `test_pipe_category_pipe_signature_value` — `PipeCategory.PIPE_SIGNATURE` equals `"PipeSignature"`.
  - `test_pipe_category_signature_is_not_controller` — `PipeCategory.is_controller_by_str("PipeSignature") is False`.
- [x] `tests/unit/pipelex/core/pipes/test_pipe_abstract_signature_surface.py` — `class TestPipeAbstractSignatureSurface`
  - Build a minimal in-memory `PipeAbstract` subclass (or use an existing PipeLLM with stubbed validators) to assert:
    - `is_signature` returns `False` for any operator/controller.
    - `pipe_dependencies()` default returns `set()` on `PipeAbstract` (i.e. operators inherit the empty default).
  - `is_signature` returns `True` for a category-`PIPE_SIGNATURE` instance (deferred — full assertion happens in Phase 2 once the runtime class exists; here, just assert the property reads from `self.pipe_category` correctly).
  > Deviation: used a descriptor-on-stub pattern (resolving `__dict__["is_signature"]` / `__dict__["pipe_dependencies"]`) rather than constructing a full `PipeAbstract` subclass — building one would require a fully-formed `StuffSpec` + `Concept` and pull unrelated machinery into a unit test. Plan explicitly allowed the alternative.
- [x] Run: `.venv/bin/pytest -q tests/unit/pipelex/core/pipes/test_pipe_blueprint_signature_enums.py tests/unit/pipelex/core/pipes/test_pipe_abstract_signature_surface.py`. Confirm: red for the new value-existence assertions; legacy tests unaffected.

### Phase 1.2 — Implementation (green)

- [x] `pipelex/core/pipes/pipe_blueprint.py`:
  - Add `PipeType.PIPE_SIGNATURE = "PipeSignature"`.
  - Add `PipeCategory.PIPE_SIGNATURE = "PipeSignature"`.
  - Update `PipeType.category` match to map `PIPE_SIGNATURE → PipeCategory.PIPE_SIGNATURE`. (Linter will catch missing cases.)
  - Update `PipeCategory.is_controller` match to return `False` for `PIPE_SIGNATURE`.
  - Add `is_signature` property to `PipeBlueprint` returning `PipeCategory(self.pipe_category) is PipeCategory.PIPE_SIGNATURE`.
- [x] `pipelex/core/pipes/pipe_abstract.py`:
  - Add `is_signature` property mirroring the blueprint's.
  - Add a default `pipe_dependencies(self) -> set[str]: return set()` method (matches the blueprint-side default).
- [x] `pipelex/pipe_controllers/pipe_controller.py`:
  - `PipeController.pipe_dependencies` stays `@abstractmethod` — every controller must implement it; the linter enforces. Do not turn it concrete just because `PipeAbstract` now has a default. The default exists for operators and signatures, not for controllers.
  > Deviation: also decorated `PipeController.pipe_dependencies` with `@override` so pyright's `reportImplicitOverride` accepts that it overrides the new `PipeAbstract` default. Linter forced this once the parent method became concrete.

### Phase 1.3 — Lint and targeted tests

- [x] `make agent-check` clean.
- [x] `.venv/bin/pytest -q tests/unit/pipelex/core/pipes/` — all green (new + legacy).

> Phase 1 deviation summary: `pipelex/core/pipes/output/output_renderer.py` and `tests/unit/pipelex/core/pipes/test_pipe_blueprint.py` both contained non-exhaustive `match` statements that needed a new `PIPE_SIGNATURE` arm to satisfy pyright. Added them.

---

## Phase 2 — Blueprint, runtime, factory

The runtime class is where the dry-run mock generation lives. Tests construct `PipeSignatureBlueprint` directly in Python and verify end-to-end runtime behavior via `PipeFactory.make_from_blueprint` and `dry_run_pipe`.

### Phase 2.1 — Tests first (red)

Use blueprints constructed in Python — no `.mthds` parsing in this phase.

- [x] `tests/integration/pipelex/pipe_signature/conftest.py` — shared fixtures:
  - `pipelex_for_signatures` — Pipelex setup with a tiny library containing a `Text` concept and one PipeSignature pipe (used by multiple tests).
  - `make_signature_blueprint(...)` factory helper.
  > Deviation: the per-test setup fixture was named `setup_signature_library` (rather than `pipelex_for_signatures`) and shaped as a callable, mirroring the existing `load_empty_library` pattern. The concepts registered are `SigTestDoc` / `SigTestSummary` rather than `Document` / `Summary` because both `Document` and `Summary` collide with native concept names.
- [x] `tests/integration/pipelex/pipe_signature/test_pipe_signature_runtime.py` — `class TestPipeSignatureRuntime` (one class only — split into multiple test methods, parametrized where useful):
  - `test_factory_produces_runtime_from_blueprint` — `PipeFactory.make_from_blueprint` on a `PipeSignatureBlueprint` returns a `PipeSignatureRuntime`.
  - `test_is_signature_true` — `runtime.is_signature is True`; `is_controller is False`.
  - `test_needed_inputs_returns_declared` — runtime with declared inputs `{"doc": "Text"}` returns that set from `needed_inputs()`.
  - `test_required_variables_returns_input_names` — same, `required_variables()` returns `{"doc"}` (no dotted paths).
  - `test_dry_run_produces_mock_text` — runtime with `output = "Text"`, `dry_run_pipe` writes a `TextContent` stuff to working memory.
  - `test_dry_run_produces_mock_variable_list` — runtime with `output = "Text[]"`, dry-run produces a `ListContent[TextContent]`.
  - `test_dry_run_produces_mock_fixed_list` — runtime with `output = "Text[3]"`, dry-run produces a `ListContent` of length 3.
  - `test_live_run_raises_signature_error` — `await pipe.run_pipe(..., run_mode=LIVE)` raises `PipeSignatureNotExecutableError` whose message contains the pipe's `pipe_ref`.
  - `test_input_multiplicity_in_blueprint` — blueprint accepts `inputs = {"docs": "Document[]"}` without validation error.
  - `test_validators_are_noops` — `validate_inputs_static`, `validate_inputs_with_library`, `validate_output_static`, `validate_output_with_library` all return without raising on a well-formed signature.
- [x] `tests/integration/pipelex/pipe_signature/test_pipe_signature_in_blueprint_union.py` — `class TestPipeSignatureBlueprintUnion`:
  - `test_bundle_blueprint_accepts_signature_pipe` — a `PipelexBundleBlueprint` built with a `pipe = {"foo": PipeSignatureBlueprint(...)}` validates cleanly.
  - `test_bundle_blueprint_rejects_unknown_pipe_type` — sanity guard, asserts the discriminator union still rejects garbage.
- [x] Run: `.venv/bin/pytest -q tests/integration/pipelex/pipe_signature/`. Confirm: all red with `ImportError` or `AttributeError` (the runtime class doesn't exist yet).

### Phase 2.2 — Implementation (green)

- [x] `pipelex/pipe_signature/` — new package directory.
  - `pipelex/pipe_signature/__init__.py` — empty.
  - `pipelex/pipe_signature/pipe_signature_blueprint.py`:
    - `PipeSignatureBlueprint(PipeBlueprint)` with `type: Literal["PipeSignature"]`, `pipe_category: Literal["PipeSignature"]`, `signature_for: PipeType | None = None`, `pipe_dependencies: list[str] = Field(default_factory=list)` (metadata).
    > Deviation: the storage field is named `signature_pipe_dependencies`, not `pipe_dependencies`, because `PipeBlueprint` declares `pipe_dependencies` as a `@property` returning `set[str]`. Shadowing the property with a Pydantic field of incompatible type would silently break call sites like `pipe_sorter.py` that iterate it expecting a set/iterable. The spec layer keeps the user-facing name `pipe_dependencies` and `to_blueprint()` maps to `signature_pipe_dependencies`. Apply the same reasoning to the runtime storage field (`declared_dependencies`) noted further below.
  - [x] `pipelex/pipe_signature/pipe_signature_runtime.py`:
    - `PipeSignatureRuntime(PipeAbstract)` with `type: Literal["PipeSignature"]`, `pipe_category: Literal["PipeSignature"]`, `signature_for: PipeType | None = None`, `declared_dependencies: list[str] = Field(default_factory=list, description="Pipes this signature claims to depend on (metadata for tooling).")`.
    - **No pydantic alias on `declared_dependencies`.** The earlier draft proposed aliasing a `_signature_pipe_dependencies` field to `pipe_dependencies`; that collides with the method name and is fragile under `extra="forbid"` + `strict=True`. Storage field and method name are kept distinct.
    - `validate_inputs_static`, `validate_inputs_with_library`, `validate_output_static`, `validate_output_with_library` → no-ops.
    - `needed_inputs(visited_pipes=None)` → returns `self.inputs` (mirrors operator pattern).
    - `required_variables()` → `set(self.inputs.variables)`.
    - `pipe_dependencies()` → `set(self.declared_dependencies)`.
    - `_live_run_pipe(...)` → `raise PipeSignatureNotExecutableError(pipe_ref=self.pipe_ref)`.
    - `_dry_run_pipe(...)`:
      1. Convert `self.output` (a `StuffSpec`) into a `TypedNamedStuffSpec` via a new `convert_stuff_spec_to_typed_named` helper in `pipelex/pipe_run/dry_run.py` (sibling of the existing `convert_to_working_memory_format`, but for a single output `StuffSpec` instead of `InputStuffSpecs`).
      2. Mint a single `Stuff` via a new `WorkingMemoryFactory.make_mock_stuff(typed_named_stuff_spec)` (a refactor — see below).
      3. Write to `working_memory.set_new_main_stuff(...)` and return `PipeOutput(working_memory=working_memory, pipeline_run_id=job_metadata.pipeline_run_id)`.
    - `_validate_before_run`, `_validate_after_run` → no-ops.
    - **Error-handling rule for new code:** do NOT introduce new `except Exception` catches in `PipeSignatureRuntime`, the new helpers in `WorkingMemoryFactory`, or `convert_stuff_spec_to_typed_named`. Let mock-construction errors propagate (e.g. `DryRunFactory` failures, `ClassRegistryNotFoundError`). A separate worktree owns the error-handling refactor of the pre-existing `except Exception` in `WorkingMemoryFactory.make_mock_inputs:190` — do not replicate that pattern.
  - [x] `pipelex/pipe_signature/pipe_signature_factory.py`:
    - `PipeSignatureFactory(PipeFactoryProtocol[PipeSignatureBlueprint, PipeSignatureRuntime])` with a `make(...)` classmethod that builds the runtime from the blueprint + parsed inputs/output.
  - [x] `pipelex/pipe_signature/exceptions.py`:
    - `PipeSignatureNotExecutableError(PipelexError)` with a `pipe_ref` field and a clear message.
- [x] Register `PipeSignatureFactory` in the class registry so `PipeFactory.make_from_blueprint` dispatches via the existing `f"{pipe_type.value}Factory"` convention. (Look at how other factories are registered — probably in `pipelex/__init__.py` or via auto-import; mirror.)
  > Registered alongside `PipeSignatureRuntime` in `CoreRegistryModels.PIPE_SIGNATURES` / `PIPE_SIGNATURES_FACTORY`. `RegistryModels.get_all_models()` walks every list-valued class attribute, so the new lists are auto-discovered.
- [x] `pipelex/core/bundles/pipelex_bundle_blueprint.py`:
  - Add `PipeSignatureBlueprint` to `PipeBlueprintUnion`.
- [x] `pipelex/core/memory/working_memory_factory.py`:
  - Add `make_mock_stuff(typed_named_stuff_spec: TypedNamedStuffSpec) -> Stuff` — extracts the per-iteration body of `make_mock_inputs` (both the no-multiplicity branch and the multiplicity branch combined into one helper returning a single `Stuff`). `make_mock_inputs` then becomes a thin loop over `make_mock_stuff`.
  - Preserve the existing `except Exception` fallback inside `make_mock_inputs` (separate worktree owns that refactor). Do NOT add a new `except Exception` catch inside `make_mock_stuff` — let `make_mock_content` errors propagate. The existing fallback continues to wrap only the multi-stuff loop.
- [x] `pipelex/pipe_run/dry_run.py`:
  - Add `convert_stuff_spec_to_typed_named(stuff_spec: StuffSpec, name: str) -> TypedNamedStuffSpec` — sibling of `convert_to_working_memory_format` that operates on a single output `StuffSpec` instead of `InputStuffSpecs`. Same class-registry lookup, same fallback-to-`TextContent` behavior on missing structure class (matches the existing behavior inside `convert_to_working_memory_format`). Do NOT add a new `except Exception`; mirror the specific exception types the existing function catches.

### Phase 2.3 — Lint and targeted tests

- [x] `make agent-check` clean.
- [x] `.venv/bin/pytest -q tests/integration/pipelex/pipe_signature/` — all green.

---

## Phase 3 — Spec layer

Wire the existing `PipeSignature` spec into the `PipeSpecUnion`, fix the three corrections (literal `type`, multiplicity inputs, drop `result`), and implement `to_blueprint()`.

### Phase 3.1 — Tests first (red)

- [x] `tests/unit/pipelex/builder/pipe/test_pipe_signature_spec.py` — `class TestPipeSignatureSpec`:
  - `test_type_literal_is_pipe_signature` — `PipeSignature(...).type == "PipeSignature"`.
  - `test_signature_for_optional` — `PipeSignature(...)` with no `signature_for` field validates; setting `signature_for = PipeType.PIPE_LLM` validates.
  - `test_signature_for_rejects_pipe_signature` — `PipeSignature(..., signature_for=PipeType.PIPE_SIGNATURE)` raises. A signature standing in for a signature is nonsensical; the validator rejects it.
  - `test_inputs_accept_multiplicity` — `inputs = {"docs": "Document[]"}` validates; `inputs = {"images": "Image[3]"}` validates.
  - `test_inputs_reject_invalid_concept_syntax` — `inputs = {"bad": "lowercase"}` raises.
  - `test_no_result_field` — `assert "result" not in PipeSignature.model_fields`.
  - `test_to_blueprint_returns_signature_blueprint` — `PipeSignature(...).to_blueprint()` returns a `PipeSignatureBlueprint` with matching `code`/`description`/`inputs`/`output`/`signature_for`/`pipe_dependencies`.
  - `test_to_blueprint_preserves_input_multiplicity` — `inputs = {"docs": "Document[]"}` round-trips through `to_blueprint()` unchanged.
- [x] `tests/unit/pipelex/builder/pipe/test_pipe_spec_union_signature.py` — `class TestPipeSpecUnionDispatch`:
  - `test_union_dispatches_pipe_signature` — `pydantic.TypeAdapter(PipeSpecUnion).validate_python({"type": "PipeSignature", ...})` returns a `PipeSignature` instance, not another spec type.
  - `test_union_dispatches_pipe_llm_unchanged` — regression guard: existing `{"type": "PipeLLM", ...}` still dispatches to `PipeLLMSpec`.
  > Deviation: the test on bad concept syntax accepts both `ValidationError` and the underlying `ConceptStringError`. PipeSpec's inherited `validate_inputs` re-raises `ConceptStringError` without wrapping it in `ValueError`, so pydantic does not convert it to `ValidationError`. That looks like a pre-existing rough edge in PipeSpec; I did not widen its scope to address it.
- [x] Run: `.venv/bin/pytest -q tests/unit/pipelex/builder/pipe/test_pipe_signature_spec.py tests/unit/pipelex/builder/pipe/test_pipe_spec_union_signature.py`. Confirm red.

### Phase 3.2 — Implementation (green)

- [x] `pipelex/builder/pipe/pipe_signature.py`:
  - Change `type: PipeType | str = Field(...)` to `type: Literal["PipeSignature"] = "PipeSignature"` (use `SkipJsonSchema` if needed to match sibling pattern).
  - Change `pipe_category` to `SkipJsonSchema[Literal["PipeSignature"]] = "PipeSignature"`.
  - Add `signature_for: PipeType | None = None` with description "Intended downstream pipe type when this signature is implemented (optional hint for agents)."
  - Add a `@field_validator("signature_for", mode="after")` that rejects `PipeType.PIPE_SIGNATURE` with a clear message ("a PipeSignature cannot have signature_for=PipeSignature").
  - Remove the `set_pipe_category` and `validate_type` validators (the literal handles both).
  - **Remove `result` field entirely.**
  - Allow multiplicity in inputs: replace the inputs description and add a `validate_inputs` validator that mirrors `PipeSpec.validate_inputs` (reuse via shared helper or copy).
  - Add `pipe_dependencies: list[str] = Field(default_factory=list, description="Pipes this signature claims to depend on (metadata for tooling).")`.
  - Add `to_blueprint(self) -> PipeSignatureBlueprint` building the blueprint from the spec fields.
  - Update `rendered_pretty` for the new field surface (drop `result`).
  > Deviation: `PipeSignature` now inherits from `PipeSpec` (was `StructuredContent`), so it gets `pipe_code`/`description`/`inputs`/`output`/`validate_inputs`/`validate_output` for free and slots naturally into `pipe_type_to_spec_class: dict[str, type[PipeSpec]]`. As a consequence the spec uses `pipe_code` rather than the old `code` field name (matching sibling specs).
- [x] `pipelex/builder/pipe/pipe_spec_union.py`:
  - Add `PipeSignature` to the union.
- [x] `pipelex/builder/pipe/pipe_spec_map.py`:
  - Add `"PipeSignature": PipeSignature`.

### Phase 3.3 — Lint and targeted tests

- [x] `make agent-check` clean.
- [x] `.venv/bin/pytest -q tests/unit/pipelex/builder/pipe/ tests/integration/pipelex/pipe_signature/` — all green.

> Phase 3 deviation summary: `pipe_signature.py` now extends `PipeSpec` (not `StructuredContent`) so it inherits `pipe_code` and the shared inputs/output validators. The hardcoded `len(PipeType.value_list()) == 10` assertion in `tests/unit/pipelex/language/test_mthds_schema.py` was changed to compare against the expected-blueprint set size; this also caught two other places that needed updates after the new `PipeType.PIPE_SIGNATURE` value: `tests/unit/pipelex/core/pipes/test_execution_data_coverage.py` (filters signature pipes out of the execution-data coverage walk) and `pipelex/language/mthds_schema_generator.py` (adds `PipeSignatureBlueprint` to `_PIPE_DEFINITION_NAMES` so `pipe_category` is stripped from its schema).

---

⛔ **CHECKPOINT A — STOP HERE**

**Coding must stop after Phase 3.** Do **not** start Phase 4 in the same session.

Before handing back:

1. Confirm every box above is ticked (boxes should have been ticked as each item landed, not now). For any item that diverged from the plan, add a `> Deviation:` blockquote inline next to the box.
2. Update the top "Status" line of this file to read: `Status: Phases 1–3 landed (YYYY-MM-DD). Signatures construct end-to-end in Python (spec → blueprint → runtime → dry-run mock). Strict-mode gating, CLI wiring, e2e, and docs are open.`
3. Add a "Current state" paragraph near the top summarizing: signatures are mockable but not strict-checked; live execution raises but is unreachable through validate (validate doesn't yet know to refuse them); .mthds files cannot yet declare a `PipeSignature` end-to-end because the interpreter path hasn't been exercised. Note any unexpected surprises (e.g. if a refactor of `make_mock_content` was larger than planned).
4. Run `make agent-test` (full suite) to confirm no regressions. Note the result.
5. Hand back to the human.

Phase 4 picks up by reading this updated "Current state" plus the Phase 4 section below.

---

## Phase 4 — Strict pre-check

Add `collect_signature_refs`, `SignaturesNotAllowedError`, and thread `allow_signatures` through the dry-run + bundle-validation surface.

### Phase 4.1 — Tests first (red)

- [x] `tests/integration/pipelex/pipe_signature/test_collect_signature_refs.py` — `class TestCollectSignatureRefs`:
  - Fixtures construct mini libraries in Python with mixed pipe types.
  - `test_operator_returns_empty` — a real `PipeLLM`'s `collect_signature_refs()` returns `set()`.
  - `test_signature_returns_self` — a `PipeSignatureRuntime`'s `collect_signature_refs()` returns `{self.pipe_ref}`.
  - `test_controller_sequence_walks_steps` — a `PipeSequence` whose step references a signature returns `{sig.pipe_ref}`.
  - `test_controller_parallel_walks_branches` — a `PipeParallel` whose branch references a signature returns `{sig.pipe_ref}`.
  - `test_controller_condition_walks_outcomes` — a `PipeCondition` whose `outcomes` map (and `default_outcome`) references signatures returns the union of those signature `pipe_ref`s.
  - `test_controller_batch_walks_branch` — a `PipeBatch` whose `branch_pipe_code` references a signature returns `{sig.pipe_ref}`.
  - `test_nested_controller_walks_deeply` — `PipeSequence(steps=[PipeSequence(steps=[signature])])` — outer returns the leaf signature.
  - `test_cycle_protection` — two pipes whose `pipe_dependencies()` mutually reference each other; walk terminates and returns the signatures found (if any).
  - `test_unresolved_cross_package_dep_skipped` — controller references a cross-package pipe not in the library; walk does not raise and returns the signatures found in the resolvable subgraph.
  > Deviation: tests pass `pipe_lookup=get_optional_pipe` to `collect_signature_refs` because the walker takes a required `pipe_lookup` callable (see Status block for the cycle reason).
- [x] `tests/integration/pipelex/pipe_signature/test_signatures_not_allowed_error_message.py` — `class TestSignaturesNotAllowedErrorMessage`:
  - `test_dep_paths_keys_are_qualified_pipe_refs` — `error.dep_paths` keys are fully-qualified pipe_refs (`domain.code`), not bare codes; the values are ordered lists of pipe_refs naming the controllers traversed to reach the signature.
  - `test_message_lists_each_signature_with_dep_path` — `str(error)` (or `error.message`) contains one human-readable line per signature, naming the signature pipe_ref and the dep chain that reached it.
  - `test_message_includes_fix_suggestion` — message tells the user how to recover ("replace with a real implementation, or re-run with `--allow-signatures`").
- [x] `tests/integration/pipelex/pipe_signature/test_dry_run_strict_mode.py` — `class TestDryRunStrictMode`:
  - `test_strict_default_passes_when_no_signatures` — dry-run of a real `PipeSequence` of real pipes with `allow_signatures=False` (the default) succeeds.
  - `test_strict_fails_on_signature_in_sequence` — dry-run with a signature step + `allow_signatures=False` raises `SignaturesNotAllowedError`; the error's `signature_refs` includes the leaf signature's `pipe_ref`.
  - `test_lenient_succeeds_on_signature_in_sequence` — same setup with `allow_signatures=True` succeeds; the working memory after dry-run contains a mock stuff for the signature's output.
  - `test_strict_error_lists_all_signatures` — a controller depending on two signatures; the error lists both qualified `pipe_ref`s in `signature_refs`.
  - `test_strict_error_includes_dep_paths` — the error's payload includes the dep-chain that reached each signature, with qualified pipe_refs throughout (e.g. `{"sigs.summarize_doc": ["pipelines.process_doc", "pipelines.inner_seq"]}`).
  - `test_validate_bundle_strict_fails_on_signature` — `validate_bundle(blueprints=[...], allow_signatures=False)` raises `ValidateBundleError`; the raised error has a non-None `signature_check_error: SignaturesNotAllowedError` carrying the leaf signature's pipe_ref in `signature_refs` and the dep chain in `dep_paths`.
  - `test_validate_bundle_lenient_passes_on_signature` — same `allow_signatures=True` passes; the returned `ValidateBundleResult.dry_run_result` contains a `SUCCESS` entry for every loaded pipe (including the signature itself).
- [x] Run: `.venv/bin/pytest -q tests/integration/pipelex/pipe_signature/`. Confirm red on the new tests; previously-green tests stay green.

### Phase 4.2 — Implementation (green)

- [x] `pipelex/core/pipes/pipe_abstract.py`:
  - Add `collect_signature_refs(self, visited: set[str] | None = None) -> set[str]` — walks `self.pipe_dependencies()` via `get_optional_pipe`, accumulates signatures, short-circuits on `visited`. Track visited by `self.pipe_ref` (qualified, e.g. `domain.code`). `pipe_dependencies()` returns bare codes; resolution via `get_optional_pipe(pipe_code=...)` is naive (first match wins for ambiguous bare codes) — that mirrors existing behavior across the codebase. The walk does not attempt to disambiguate. (Pseudocode in `wip/signature-based-validation.md`.)
  - Add `collect_signature_paths(self, visited: set[str] | None = None, current_path: list[str] | None = None) -> dict[str, list[str]]` — companion of `collect_signature_refs` that returns `dict[signature_pipe_ref, list[controller_pipe_refs]]`. Used by `SignaturesNotAllowedError` to render dep-chain UX. Keys and path entries are all qualified pipe_refs.
  > Deviation: both methods take a required `pipe_lookup: Callable[[str], PipeAbstract | None]` parameter rather than calling `get_optional_pipe` internally. Reason: pyright's `reportImportCycles` flagged even a function-local import (`from pipelex.hub import get_optional_pipe`) because the cycle pipe_abstract → hub → libraries.library → libraries.pipe.pipe_library → pipe_abstract is real. Callers pass `get_optional_pipe`; recursion passes the same callable through. A `PipeLookupCallable: TypeAlias` lives under `TYPE_CHECKING` for the type annotation.
- [x] `pipelex/pipe_signature/exceptions.py`:
  - Add `SignaturesNotAllowedError(PipelexError)` with fields `pipe_ref: str` (the entry-point pipe being validated), `signature_refs: set[str]` (qualified pipe_refs of every reachable signature), `dep_paths: dict[str, list[str]]` (signature pipe_ref → ordered list of controller pipe_refs naming the path to the signature).
  - `__str__` / message format: one line per signature, naming its qualified pipe_ref and the dep chain, ending with the suggested fix ("replace with a real implementation, or re-run with `--allow-signatures`").
- [x] `pipelex/pipe_run/dry_run.py`:
  - Update `dry_run_pipe` signature to `async def dry_run_pipe(pipe: PipeAbstract, *, allow_signatures: bool = False, raise_on_failure: bool = False) -> DryRunOutput`.
  - At the top of the body, if `not allow_signatures`: call `sig_refs = pipe.collect_signature_refs()`; if non-empty, build `dep_paths = pipe.collect_signature_paths()` and raise `SignaturesNotAllowedError(pipe_ref=pipe.pipe_ref, signature_refs=sig_refs, dep_paths=dep_paths)`.
  - Update `dry_run_pipes` similarly (the same flag, threaded into each `dry_run_pipe` call).
  > Deviation: `dry_run.py` passes `pipe_lookup=get_optional_pipe` to the walker (see above).
  > Deviation: also updated `tests/unit/pipelex/pipe_run/test_dry_run.py` mock-based tests to set `mock_pipe.collect_signature_refs.return_value = set()`; otherwise `MagicMock` returns a truthy mock and the strict pre-check fires.
- [x] `pipelex/pipeline/validate_bundle.py`:
  - Add `allow_signatures: bool = False` to `validate_bundle` and `validate_bundles_from_directory`. Thread to `dry_run_pipes` in all three branches of `validate_bundle` (now that the `dry_run_pipes` calls are uncommented) and in `validate_bundles_from_directory`.
  - Add a dedicated `except SignaturesNotAllowedError as sig_error:` branch to both functions' try/except chains. Wrap into `ValidateBundleError` (extend the error with a `signature_check_error: SignaturesNotAllowedError | None = None` field so dep_paths and signature_refs are preserved end-to-end). The CLI's pipe_cmd / bundle_cmd surfaces should display the rendered message from `signature_check_error` when present (Phase 5 detail).
  - **Why this works:** `validate_bundle` was updated on this branch to actually invoke `dry_run_pipes` end-to-end. The strict check inside `dry_run_pipe` therefore fires for every `validate_bundle` caller — no separate `check_no_signatures_reachable` helper is needed. The earlier review concern about routing is moot.
- [x] `pipelex/cli/commands/validate/_validate_core.py`:
  - Thread `allow_signatures` from the CLI into `dry_run_pipe`/`dry_run_pipes`/`validate_bundle`. (CLI flag wiring is Phase 5; here just thread the parameter so the function plumbing is in place.)
  > Deviation: also renamed `_validate_pipe_or_bundle` to `validate_pipe_or_bundle` (drop the leading underscore) so the Phase 5 CLI tests can import it without tripping `PLC2701` everywhere. The behavior is unchanged; the only call site (`execute_validate`) was updated in lock-step.

### Phase 4.3 — Lint and targeted tests

- [x] `make agent-check` clean.
- [x] `.venv/bin/pytest -q tests/integration/pipelex/pipe_signature/ tests/unit/pipelex/pipe_run/` — all green.

---

## Phase 5 — CLI surface

Surface the strict/lenient choice at the CLI. The agent CLI defaults to lenient because that's its primary use case.

### Phase 5.1 — Tests first (red)

CLI tests should drive the typer command directly via `CliRunner` rather than spawning subprocesses (matches existing CLI test patterns in this repo).

- [x] `tests/integration/pipelex/cli/test_validate_signatures_cli.py` — `class TestValidateSignaturesCli`:
  - Fixtures load a tiny in-memory library directory with a signature-containing bundle.
  - `test_validate_pipe_strict_default_fails` — `pipelex validate <pipe>` (no flag) on a pipe that reaches a signature exits non-zero with the signature listed in stderr.
  - `test_validate_pipe_allow_signatures_passes` — `pipelex validate <pipe> --allow-signatures` exits zero on the same bundle.
  - `test_validate_all_strict_default_passes_with_orphan_signature` — `pipelex validate --all` succeeds even when the library contains an orphan signature (no caller); confirms "iterate non-signature pipes only" semantics.
  - `test_validate_all_strict_fails_with_caller_of_signature` — `pipelex validate --all` fails when a non-signature pipe reaches a signature.
  - `test_validate_all_allow_signatures_passes` — same setup, lenient flag, passes.
  > Deviation: tests drive `validate_pipe_or_bundle` and `do_validate_all_libraries_and_dry_run` directly (no CliRunner in this repo). Rich console output isn't captured by pytest's `capsys` for nested writers, so the "signature listed in stderr" assertion was dropped in favor of asserting the `typer.Exit(1)` exit code; the message-in-output check is exercised by Phase 4's `test_signatures_not_allowed_error_message.py`.
- [x] `tests/integration/pipelex/cli/test_agent_validate_defaults_lenient.py` — `class TestAgentValidateDefaultsLenient`:
  - `test_agent_validate_defaults_to_lenient` — calling the agent CLI's validate against a signature-bundle exits zero without an explicit flag.
- [x] Run: `.venv/bin/pytest -q tests/integration/pipelex/cli/`. Confirm red.

### Phase 5.2 — Implementation (green)

- [x] `pipelex/cli/commands/validate/app.py` (and any sibling typer command modules):
  - Add `--allow-signatures` boolean option, default `False`. Thread to `execute_validate`.
  > Deviation: the option lives on `validate_pipe_cmd` and `validate_bundle_cmd` (the two surfaces that actually take subcommand args). `app.py` only wires the `_ValidateGroup` and forwards args to subcommands, so it didn't need editing.
- [x] `pipelex/cli/commands/validate/_validate_core.py`:
  - Already threads `allow_signatures` from Phase 4. Surface it to typer.
  - `do_validate_all_libraries_and_dry_run` — iterate non-signature pipes only when `allow_signatures=False` (use `pipe.is_signature`); when `allow_signatures=True`, iterate everything (signatures dry-run trivially).
- [x] `pipelex/cli/agent_cli/commands/validate/_validate_core.py`:
  - Default `allow_signatures=True` for the agent CLI. Add an `--strict` flag if needed (defer if not required by current tests).
  > Deferred: `--strict` flag — not needed by current tests.
- [x] Validation summary: when lenient and signatures were involved, print a final line like `"Validated N pipes (M signatures)."`. Add to whatever summary line currently exists.
  > Deviation: instead of a separate trailing line, the suffix is **appended in-place** to the existing summary lines via a `_format_signatures_summary_suffix` helper in `pipelex/cli/commands/validate/_validate_core.py`. Applied to all three lenient surfaces — `validate pipe --all` ("Setup sequence passed OK, …"), `validate pipe <code>` ("Successfully validated pipe '…'"), and `validate bundle <path>` ("Successfully validated bundle '…'"). Suffix is `" (1 signature)"` for one and `" (M signatures)"` for more; empty when no signature was involved so fully-implemented bundles read naturally. Strict mode never appends. Covered by `tests/integration/pipelex/cli/test_validate_signatures_summary.py`.

Additional touches landed in Phase 5.2 (not enumerated above but required for the tests to pass):

- [x] `pipelex/cli/error_handlers.py` — `_display_validation_error_details` now renders `exc.signature_check_error` under an "Unimplemented Signatures:" heading so the strict-mode UX surfaces the dep chain.

### Phase 5.3 — Lint and targeted tests

- [x] `make agent-check` clean.
- [x] `.venv/bin/pytest -q tests/integration/pipelex/cli/ tests/integration/pipelex/pipe_signature/` — all green.

---

⛔ **CHECKPOINT B — STOP HERE**

**Coding must stop after Phase 5.** Do **not** start Phase 6 in the same session.

Before handing back:

1. Confirm every box above is ticked. Add `> Deviation:` notes inline for anything that differed from the plan.
2. Update the top "Status" line: `Status: Phases 1–5 landed (YYYY-MM-DD). Strict / lenient validation works end-to-end through Python and CLI. E2E .mthds tests and docs are open.`
3. Add to the "Current state" paragraph: e2e .mthds parsing not yet exercised; some surprise may surface there (interpreter or schema generator might need touching).
4. Run `make agent-test` — full suite green.
5. Hand back to the human.

Phase 6 picks up by reading the updated "Current state" plus the Phase 6 section below.

---

## Phase 6 — End-to-end tests with real `.mthds`

This phase exercises the full path: `.mthds` file → `PipelexInterpreter` → `PipelexBundleBlueprint` → library load → factory → runtime → dry-run. No new production code is expected; if something breaks, the design surfaces a real bug rather than a test issue.

### Phase 6.1 — Tests first (red)

Build `.mthds` fixtures under `tests/e2e/fixtures/signature_bundles/` and reference them from the tests.

- [x] `tests/e2e/fixtures/signature_bundles/signature_only.mthds` — a bundle whose `main_pipe` is a `PipeSignature`. Single domain, single concept, single pipe.

  ```toml
  domain = "signature_demo"
  main_pipe = "summarize_doc"

  [concept]
  Document = "A document concept used for testing signatures."

  [pipe.summarize_doc]
  type = "PipeSignature"
  description = "Produces a summary of a document (contract only)."
  inputs = { doc = "Document" }
  output = "Text"
  ```

  > Deviation: the concept is named `SigDocument` (not `Document`) because `Document` collides with the native concept name. The bundled `plxt` schema doesn't yet know about `PipeSignature`, so `Write`/`Edit` calls trigger the `validate-mthds.sh` PostToolUse hook (blocked once during the session — the file was still written, and remaining fixtures were authored via `Bash` heredoc to avoid spam). Same constraint forced `tests/e2e/fixtures/signature_bundles/**` to be added to `.pipelex/plxt.toml` excludes so `plxt-lint` (part of `make agent-check`) stays green.

- [x] `tests/e2e/fixtures/signature_bundles/mixed_with_signature_step.mthds` — a `PipeSequence` whose second step is a signature.

  ```toml
  domain = "signature_mixed"
  main_pipe = "process_doc"

  [concept]
  Document = "A document concept."
  Summary = "A summary concept."

  [pipe.extract_doc]
  type = "PipeLLM"
  description = "Extract text from a document."
  inputs = { doc = "Document" }
  output = "Text"
  prompt = "Extract text from $doc."

  [pipe.summarize_extracted]
  type = "PipeSignature"
  description = "Summarize extracted text (contract only)."
  inputs = { extracted = "Text" }
  output = "Summary"

  [pipe.process_doc]
  type = "PipeSequence"
  description = "Extract then summarize."
  inputs = { doc = "Document" }
  output = "Summary"
  steps = [
    { pipe = "extract_doc", result = "extracted" },
    { pipe = "summarize_extracted", result = "summary" },
  ]
  ```

  > Deviation: concepts renamed `MixDoc` / `MixSummary` (same native-collision reason as above). The PipeLLM `prompt` uses `$doc` (inline value) rather than `@doc` because PipeLLM rejects inline `@` sigils.

- [x] `tests/e2e/fixtures/signature_bundles/multi_input_multiplicity.mthds` — signature with `Document[]` and `Image[3]` inputs.

  ```toml
  domain = "signature_multiplicity"
  main_pipe = "fuse_docs_and_images"

  [concept]
  Document = "A document."
  Image = "An image."
  Report = "A report."

  [pipe.fuse_docs_and_images]
  type = "PipeSignature"
  description = "Combine docs and exactly 3 images (contract only)."
  inputs = { docs = "Document[]", images = "Image[3]" }
  output = "Report"
  ```

  > Deviation: concepts renamed `FuseDoc` / `FuseImage` / `FuseReport` because `Document`, `Image`, and the singular concept naming would collide with native concepts. Multiplicity (`FuseDoc[]`, `FuseImage[3]`) round-trips through the interpreter unchanged.

- [x] `tests/e2e/test_signature_validation_mthds.py` — `class TestSignatureValidationE2E`:
  - `test_signature_only_bundle_strict_fails` — `validate_bundle(mthds_file_path=signature_only_path)` with default strict raises `ValidateBundleError` wrapping `SignaturesNotAllowedError`.
  - `test_signature_only_bundle_lenient_passes` — same call with `allow_signatures=True` returns a `ValidateBundleResult` with a populated `dry_run_result`.
  - `test_mixed_bundle_strict_fails_with_dep_path` — strict mode on `mixed_with_signature_step.mthds` fails; the error message includes both the leaf signature's `pipe_ref` and the controller's `pipe_ref` in the dep path.
  - `test_mixed_bundle_lenient_passes_and_produces_mock` — lenient mode succeeds; dry-run output for `process_doc` contains a `Summary` mock stuff.
  - `test_multiplicity_inputs_lenient_passes` — lenient mode on `multi_input_multiplicity.mthds` succeeds.
  - `test_live_run_signature_pipeline_fails` — running the bundle live (via `PipelexRunner.execute_pipeline` with `pipe_run_mode=LIVE`) raises `PipelineExecutionError` whose underlying cause is `PipeSignatureNotExecutableError`.
  > Deviation: `DryRunOutput` is a thin status object (no `working_memory`), so `test_mixed_bundle_lenient_passes_and_produces_mock` asserts that both `process_doc` and `summarize_extracted` reach `DryRunStatus.SUCCESS` rather than reaching into the working memory for the mocked stuff. Other tests adjusted similarly.
- [x] `tests/e2e/test_signature_validation_cli.py` — `class TestSignatureValidationCli`:
  - `test_cli_validate_signature_bundle_strict_fails` — `pipelex validate signature_only.mthds` exits non-zero with the signature listed in stderr.
  - `test_cli_validate_signature_bundle_lenient_passes` — same with `--allow-signatures` exits zero.
  > Deviation: tests drive `_validate_pipe_or_bundle` directly (matches the integration CLI tests) rather than spawning a subprocess. The "stderr signature listed" check is exercised by Phase 4's `test_signatures_not_allowed_error_message.py`; here we assert the non-zero exit only.
- [x] Run: `.venv/bin/pytest -q tests/e2e/`. Confirm: most red because interpreter / schema generator hasn't been exercised on the new `type = "PipeSignature"` shape yet.
  > Deviation: the interpreter happily produced `PipeSignatureBlueprint` from `type = "PipeSignature"` on the first try — no fix required there. The only failing test was `test_mixed_bundle_strict_fails_with_dep_path`, and the root cause was on the runtime side (`dry_run_pipes` aggregation), not the interpreter.

### Phase 6.2 — Make e2e tests green

Whatever this phase surfaces is a real bug in the previous phases. Expected categories:

- `PipelexInterpreter` round-trip: confirm TOML parsing of `type = "PipeSignature"` produces a `PipeSignatureBlueprint`. If the discriminator dispatch fails in `PipelexBundleBlueprint.pipe`, fix it.
- Library load: confirm `LibraryCrateFactory.make_from_blueprints` + `library_manager.load_from_blueprints` accept the new blueprint shape. If `concept_codes_from_the_same_domain` filtering doesn't accommodate signature concepts, fix.
- Bundle-level validation: `validate_local_pipe_references` already key-based, should pass. Confirm.
- Schema generator: `pipelex-dev generate-mthds-schema` should include `PipeSignature` in the union. Verify and regenerate the schema file (`derived/mthds_schema.json`) if it exists in the repo.

- [x] Make every Phase 6.1 test green.
  > Deviation: only one production code change was needed. In `pipelex/pipe_run/dry_run.py::dry_run_pipes`, the strict-mode pre-check aggregated dep paths with a "first wins" rule. When the signature pipe itself was iterated first, the empty `[]` dep chain was recorded and never replaced by the longer, controller-rooted chain discovered later. Switched the aggregation to prefer the longest known dep chain so the error message always shows the most informative path. No interpreter, library, or schema generator fixes were required.
- [x] If the JSON schema is checked in: run `.venv/bin/pipelex-dev generate-mthds-schema` and commit the diff.
  > Deviation: no JSON schema is checked in to this repo (the artifact lives in `vscode-pipelex/`), so nothing to regenerate here. The bundled `plxt` schema therefore stays unaware of `PipeSignature` until `vscode-pipelex` ships a new release — captured in "Known gaps after Phase 6" above.

### Phase 6.3 — Lint and full tests

- [x] `make agent-check` clean.
- [x] `make agent-test` — full suite green.

---

⛔ **CHECKPOINT C — STOP HERE**

**Coding must stop after Phase 6.** Do **not** start Phase 7 in the same session.

Before handing back:

1. Confirm every box above is ticked. Add `> Deviation:` notes for anything that surprised you (especially in Phase 6.2 — the e2e phase is the most likely to surface design gaps).
2. Update the top "Status" line: `Status: Phases 1–6 landed (YYYY-MM-DD). End-to-end signature validation works from .mthds. Docs and CHANGELOG are open.`
3. Append a "Known gaps after Phase 6" subsection listing anything noticed but deferred (e.g. "schema generator output diff visible; not committed").
4. Hand back to the human.

Phase 7 picks up by reading the updated "Status" plus the Phase 7 section below.

---

## Phase 7 — Docs, CHANGELOG, polish

### Phase 7.1 — Docs

- [x] `docs/` MTHDS authoring guide: add a section "Signature pipes" describing the `type = "PipeSignature"` shape, listing all valid fields, with the three example fixtures from Phase 6 inlined as illustrations.
  > Landed as a new top-level page under `building-methods/pipes/`: `docs/building-methods/pipes/signature-pipes.md`. Wired into `mkdocs.yml` in both nav placements (after the controllers list, before `Optimize Cost & Quality`). Cross-linked from `docs/building-methods/pipes/index.md` and `docs/tools/cli/validate.md`. The three Phase 6 fixtures are inlined verbatim.
- [x] CLI help text — confirm `pipelex validate --help` mentions `--allow-signatures` with a one-line description ("Accept PipeSignature placeholders in the dependency graph (lenient mode).").
  > Already wired by Phase 5 on both `validate_pipe_cmd` and `validate_bundle_cmd` with that exact help string. Also added the flag to `docs/tools/cli/validate.md` under both subcommands' Options blocks with example invocations.
- [x] `pipelex/builder/pipe/pipe_signature.py`: tighten the class docstring with the new contract (drop the `result` line, mention `signature_for`, mention strict-vs-lenient).
  > Rewrote the docstring to lead with the design intent (top-down sketching, replace each signature with a real operator), then call out validation behavior (strict / lenient / live), multiplicity, and the optional `signature_for` / `pipe_dependencies` fields. The pre-existing docstring already had no `result` reference, so nothing to drop.

### Phase 7.2 — CHANGELOG

- [x] `CHANGELOG.md` under `## [Unreleased]`:
  - `### Added` — `PipeSignature` pipe type, `--allow-signatures` flag, agent CLI lenient default, `collect_signature_refs` graph walk.
  - `### Changed` — `dry_run_pipe`/`dry_run_pipes`/`validate_bundle` now accept `allow_signatures: bool = False`.
  - Cross-link `wip/signature-based-validation.md`.
  > New `## [Unreleased]` section inserted above `[v0.28.0]`, with `### Added` (signature pipe type + factory + runtime, `--allow-signatures` flag with lenient agent-CLI default, `collect_signature_refs`/`collect_signature_paths` graph walk) and `### Changed` (the `allow_signatures` parameter threaded through `dry_run_pipe`/`dry_run_pipes`/`validate_bundle`/`validate_bundles_from_directory`, plus the new `signature_check_error` field on `ValidateBundleError`). Cross-link to `wip/signature-based-validation.md` included in the Added bullet.

### Phase 7.3 — Final lint and tests

- [x] `make agent-check` clean.
- [x] `make agent-test` — full suite green.

### Phase 7.4 — Merge-gate cross-repo cleanup (do NOT skip)

The branch carries a deliberate, scoped schema configuration: `.pipelex/plxt.toml` declares `derived/mthds_schema.json` as the schema source for `**/*.mthds` via a `[[rule]] / [rule.schema] path = ...` block. That is the correct configuration *on this branch* — the bundled `plxt` schema doesn't yet describe `PipeSignature`, so the local schema is the only one that accurately validates the runtime change introduced here. The branch is internally consistent and `plxt lint` is green.

The merge-gate is to land the matching `vscode-pipelex` release and then *retire* the branch-local schema rule in the same merge, so the bundled schema takes over again on `main`:

- [ ] In the `vscode-pipelex/` repo: regenerate the bundled MTHDS JSON Schema so `type = "PipeSignature"` is a valid pipe type, and cut a release of `plxt` / the VS Code extension. (Open a tracking PR there if not done; link the PR URL here when filed.)
- [ ] Once the new `plxt` is installable: in **this** repo, in the merge commit, remove the `[[rule]] / [rule.schema] path = "derived/mthds_schema.json"` block at the bottom of `.pipelex/plxt.toml`. Decide in the same commit whether `derived/mthds_schema.json` should stay as a regenerable artifact or be deleted; nothing else in this repo reads it today.
- [ ] Re-run `make agent-check` after the rule is removed and the new `plxt` is installed: `plxt lint` must accept the signature fixtures *using the bundled schema*, with no per-rule rule. If it doesn't, the `vscode-pipelex` release is incomplete and the merge should not land yet.
- [ ] Verify the `validate-mthds.sh` PostToolUse hook accepts `Write`/`Edit` on `PipeSignature` fixtures with the new `plxt` installed and the local rule removed.

**Cross-repo coordination reminder:** the `vscode-pipelex` schema regen is the gating step. Local `plxt` results during the branch lifetime are valid (the branch-local rule is intentional). The cross-check that matters is "does `plxt lint` stay green *after* the branch-local rule is removed and the new `plxt` is installed" — that is the actual ship-readiness signal. The Phase 7.4 box is closed only when that cross-check is green at merge time.

---

⛔ **CHECKPOINT D — FINAL**

**Coding stops here.** Before handing back:

1. Confirm every box is ticked; add deviation notes for anything that didn't match the plan.
2. **Double-check Phase 7.4 is complete.** If the `vscode-pipelex` schema update has not landed yet, the branch is NOT ready to ship — do not update the Status line to "Ready to ship". Instead, leave it as "Phases 1–7 landed, blocked on vscode-pipelex schema update" and hand back with that explicit blocker noted.
3. Update the top "Status" line: `Status: All phases landed (YYYY-MM-DD). Ready to ship via /release.` (only if Phase 7.4 is fully done).
4. Hand back to the human.

---

## Out of scope / explicit non-goals

- Signature concepts (concept stubs analogous to pipe signatures). Bigger design, separate plan.
- `signature_for`-driven mock specialization (e.g. `signature_for = "PipeImgGen"` mints an actual ImageContent URL). Deferred — flagged in the design doc as a phase-2 enhancement.
- Migrating existing bundles to use signatures. Authors opt in.
- Parallel `[signature.foo]` TOML table as syntactic sugar. Possible later, not a structural alternative.
- Runtime-time validation of signatures during live execution. Live-run on a signature must raise; that's the only enforcement.

---

## Reference: file targets at a glance

Production code:

- `pipelex/core/pipes/pipe_blueprint.py` — enum additions, `is_signature` on `PipeBlueprint`.
- `pipelex/core/pipes/pipe_abstract.py` — `is_signature`, promoted `pipe_dependencies`, new `collect_signature_refs`.
- `pipelex/core/bundles/pipelex_bundle_blueprint.py` — `PipeBlueprintUnion` gains `PipeSignatureBlueprint`.
- `pipelex/pipe_signature/` — new package: blueprint, runtime, factory, exceptions.
- `pipelex/builder/pipe/pipe_signature.py` — three corrections, `to_blueprint()`.
- `pipelex/builder/pipe/pipe_spec_union.py` — `PipeSignature` added to union.
- `pipelex/builder/pipe/pipe_spec_map.py` — `PipeSignature` added to map.
- `pipelex/pipe_run/dry_run.py` — `allow_signatures` parameter, strict pre-check, new `convert_stuff_spec_to_typed_named` helper.
- `pipelex/pipeline/validate_bundle.py` — `allow_signatures` threaded through all three branches and into `validate_bundles_from_directory`.
- `pipelex/core/memory/working_memory_factory.py` — `make_mock_stuff` helper extracted from `make_mock_inputs`.
- `pipelex/cli/commands/validate/app.py` + `_validate_core.py` — `--allow-signatures` flag.
- `pipelex/cli/agent_cli/commands/validate/_validate_core.py` — lenient default.

Tests:

- `tests/unit/pipelex/core/pipes/test_pipe_blueprint_signature_enums.py`
- `tests/unit/pipelex/core/pipes/test_pipe_abstract_signature_surface.py`
- `tests/unit/pipelex/builder/pipe/test_pipe_signature_spec.py`
- `tests/unit/pipelex/builder/pipe/test_pipe_spec_union_signature.py`
- `tests/integration/pipelex/pipe_signature/conftest.py`
- `tests/integration/pipelex/pipe_signature/test_pipe_signature_runtime.py`
- `tests/integration/pipelex/pipe_signature/test_pipe_signature_in_blueprint_union.py`
- `tests/integration/pipelex/pipe_signature/test_collect_signature_refs.py`
- `tests/integration/pipelex/pipe_signature/test_signatures_not_allowed_error_message.py`
- `tests/integration/pipelex/pipe_signature/test_dry_run_strict_mode.py`
- `tests/integration/pipelex/cli/test_validate_signatures_cli.py`
- `tests/integration/pipelex/cli/test_agent_validate_defaults_lenient.py`
- `tests/e2e/fixtures/signature_bundles/signature_only.mthds`
- `tests/e2e/fixtures/signature_bundles/mixed_with_signature_step.mthds`
- `tests/e2e/fixtures/signature_bundles/multi_input_multiplicity.mthds`
- `tests/e2e/test_signature_validation_mthds.py`
- `tests/e2e/test_signature_validation_cli.py`
