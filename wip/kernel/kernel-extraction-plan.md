# Method kernel extraction — `pipelex/kernel/`

## Status block (update at every checkpoint)

- **Current phase:** Phase 1 — LLM vertical slice. **Phase 0 is done and committed** (`23276cecd`). Phase 1 tasks 1.1–1.6 are **written and committed** (`make agent-check` green); **task 1.7 (tests) is the remaining Phase-1 work**, and the full `make agent-test` suite has NOT yet been run against the re-point. Branch `refactor/Kernel`, off `dev` with `dev` merged in at `221b8ee0b`. Nothing pushed yet; no PR open.
- **Next action:** run the full `make agent-test` suite and fix whatever the re-point broke, then write task 1.7's tests. See "Cold-start: where the code is" below for the exact shape of what landed.
- **Open decisions:** none blocking. The kernel construction shape (0.2) is settled as implemented; three deviations from the plan's letter are recorded under Decisions.

### Cold-start: where the code is

`pipelex/kernel/` now holds six modules:

| module | what is in it |
| --- | --- |
| `__init__.py` | Doctrine only, no re-exports: layering, definition-site imports, top-level imports, concept-resolution routing, memory contract, keyword-only/zero-grants, boot contract. |
| `method_kernel.py` | `MethodKernel` — `__init__`, `make()`, `make_step_metadata()`, and the `llm_text` / `llm_object` façade methods. Holds only the run-level `JobMetadata` and `CogtRunParams`. |
| `prompt_references.py` | `ImageReference(Kind)` and `DocumentReference(Kind)`, **moved** out of `pipe_operators/` (they could not stay there: a runtime-layer prompt-content model may not import an interpreter-layer type). All importers re-pointed; the two unit-test modules moved to `tests/unit/pipelex/kernel/`. |
| `llm_prompt_content.py` | `LlmPromptContent` (+ `make_from_text`) and `assemble_llm_prompt` — the whole former `LLMPromptBlueprint.make_llm_prompt` body, images/documents/registry/placeholders included. |
| `llm_results.py` | `StructuringPath` StrEnum, `LlmTextResult`, `LlmObjectResult`. |
| `llm_ops.py` | `resolve_llm_setting_for_text`, `resolve_llm_setting_for_object`, `derive_templating_style`, `derive_structure_prompt`, `generate_object_content`, `store_result`, `run_llm_text`, `run_llm_object`. |
| `exceptions.py` | `PromptContentError(ValueError)` — the former `LLMPromptBlueprintValueError`, moved with the code that raises it. |

Interpreter side: `LLMPromptBlueprint` keeps its fields, `required_variables()` and its `make_llm_prompt` **signature** (~40 test call sites depend on it) but now maps down through a new `to_prompt_content()` and delegates; `PipeLLM._live_run_operator_pipe` calls `run_llm_text` / `run_llm_object` and its `_llm_gen_object_stuff_content` is gone; `PipeStructure` calls `resolve_llm_setting_for_object`, `derive_structure_prompt`, `generate_object_content` and `store_result` (not `run_llm_object` — see Decisions); `pipe_operators/llm/helpers.py` (`get_output_structure_prompt`) is deleted.

### Verified in Phase 0 (do not redo)

All three negative controls were run and each failed as intended, then was reverted: deleting the `pipelex.kernel` entry fails `test_the_method_kernel_stays_declared`; a `pipelex.exceptions` import in a kernel module fails the aggregate gate; an `interpreter_hub` import in a kernel module fails both the closure test and the static guard.

### What 1.7 still has to do, with the traps already scouted

1. **Run the full `make agent-test`.** Not yet done against the re-point. The targeted slice to run first is `tests/unit/pipelex/kernel tests/unit/pipelex/pipe_operators tests/integration/pipelex/pipes tests/unit/pipelex/cli/dev tests/unit/pipelex/test_runtime_layer_import_closure.py tests/unit/pipelex/test_runtime_layer_exceptions_aggregate_gate.py`.
2. **Kernel unit tests (dry mode)** for the two arms the re-pointed interpreter suite structurally cannot reach: `structure_prompt` supplied vs derived-by-default, and the memory mutate-and-return contract. The third arm the task names — the `concept_resolver`-omitted one — **does not exist in Phase 1**; see the deviation record under Decisions before writing it.
3. **The permanent boot-contract test.** Subprocess pattern from `tests/unit/pipelex/test_runtime_layer_import_closure.py` (a suite-level boot already owns the process singletons, so it must be a subprocess). Boot `RuntimeBoot.make(needs_inference=False)` — which forces DRY — construct `MethodKernel.make(run_mode=PipeRunMode.DRY, user_id=…)`, and assert an `llm_object` call returns an `LlmObjectResult`. Two things the writer needs and would otherwise rediscover: dry generation mocks inside the leaves (`revalidate_leaf_object(..., is_mock_built=cogt_run_params.run_mode.is_dry)` in `content_generator.py`), so no provider is called; and `llm_object` needs a `Concept` plus its class, which on a zero-`.mthds` process means a native concept via `ConceptFactory.make_native_concept` and a class registered by `CoreRegistryModels` at boot.
4. **Two checkpoint chores not yet done:** a `CHANGELOG.md` `[Unreleased]` entry for the whole PR, and the drift workflow (`make drift-plan` → review → `git add` the trigger files → `make drift-ack`), which this branch will owe because it edits `hub_layering_guard.py`, a `hub-layering-convention` trigger file.
5. **Settle the deferred runtime-boot question**, because this test is the first real caller of `RuntimeBoot.make()`. `runtime_boot.py`'s orchestrator-rejection comment defers the external-interpreter-orchestrator half-application hole to exactly this moment; the analysis, including two candidate remedies and why #1073 declined both, is in [`wip/boot-split/runtime-boot-external-interpreter-orchestrator.md`](../boot-split/runtime-boot-external-interpreter-orchestrator.md). Decide there: guard it, or record here why the first caller does not trigger it (it names no `boot_orchestrator`, so the gate is not reached) and leave the hole documented rather than silently inherited.

## Goal

Pull operator-execution semantics out of the interpreter's operator classes into shared, importable kernel functions under a new public `pipelex/kernel/` subpackage, and re-point the interpreter onto them — **zero behavior change**. Today, what a `PipeLLM` step actually *does* (deck resolution, templating-style derivation, prompt assembly, generation, memory write-back) is only reachable through a fully booted interpreter with a loaded library. After this refactor, operator semantics have **one implementation with multiple callers**: the interpreter's operators, and any programmatic caller — SDK-style embedding, hosts that boot only the runtime layer — invoking them directly on a `RuntimeBoot`-only process with zero `.mthds` loaded.

This completes the runtime/interpreter layering arc: the hub split (#1062/#1064), layer placement (#1071), concept purity (#1072), the boot split that created `RuntimeBoot` (#1073), the templating-style threading fix (#1074), and the concrete-class object path (#1076). It is a pure refactor, valuable on its own: single-sourced operator semantics are what prevent two callers from drifting apart.

## Doctrine

- **Layering.** The caller-facing kernel API is hub-free: an explicit `MethodKernel` object and explicit arguments, never an ambient lookup. Kernel *internals* may use `pipelex.runtime_hub` — never `pipelex.interpreter_hub`. This is a mechanically enforced rule (the hub-layering guard plus the runtime-layer import-closure test), but #1071's history shows the guard does not hold the line "for free" — see the four sub-tasks under 0.1, which exist because each one closes a hole that episode demonstrated: an *undeclared* package is unpoliced rather than neutral (both guard rules filter through the layer declaration, so omission makes the guard quieter); a declaration with no test pinning it is a comment; a **cross-layer re-export aggregate defeats the guard entirely** (vendor adapters once pulled the interpreter into a declared-clean runtime package by importing from `pipelex.exceptions` instead of the definition site — a module that re-exports across layers is a layer boundary with the sign filed off; that hole is the one now closed mechanically tree-wide, and the kernel inherits the coverage by being declared); and a function-local import is invisible to the static graph and the closure test at once.
- **Calls are activity-shaped.** Explicit, serializable-leaning inputs and outputs; `WorkingMemory` threaded explicitly (taken and returned); no hidden shared state. This is a design constraint, not a deliverable: it keeps a future Temporal-activity wrapping a re-decoration rather than a rewrite. The memory contract, stated so both caller classes read the same thing: a kernel call may mutate the memory it is passed and returns it — callers must treat the returned memory as the result and must not rely on aliasing of the argument, because inline execution aliases the two today and a serialization boundary will not.
- **Functions carry the semantics; the class is a façade.** Module-level kernel functions hold the shared implementation. The `MethodKernel` class is a thin ergonomic façade over them, holding the per-run state a caller would otherwise thread through every call. The interpreter's operators call the functions directly.
- **The kernel API is fully keyword-only — zero subject grants.** The governing bar, stricter than the general rubric in [`docs/contribute/keyword-only-arguments.md`](../../docs/contribute/keyword-only-arguments.md): only the first parameter may be positional, and strictly only when it is obviously the subject — named in the function, or as unmistakable. Nothing in the kernel clears that bar: `llm_text` and `llm_object` name what they *produce*, and `memory` is threaded state (taken and returned), not the operand. So `pipelex/kernel/` records no entries in `subject_grants.toml`, every call site names every argument, and `make fix-keyword-only` mechanically produces exactly this form — there is no ordering trap. Any future kernel def that wants a positional subject must clear the stated bar in review first, not in the registry.
- **Boot contract: `RuntimeBoot.make()`** ([`pipelex/runtime_boot.py`](../../pipelex/runtime_boot.py)). Every kernel call must be servable on the runtime-only composition root, with no interpreter constructed and no library loaded. The import-closure test guards this structurally; a live smoke run proves it dynamically.
- **Zero behavior change.** The full `make agent-test` suite is the gate at every checkpoint — no test rewrites, only additions.

## Target caller experience

The sketch below is the API shape to preserve while the internals get extracted for real out of `pipe_llm.py` (which is where the deck chain, style derivation, and prompt assembly currently live). Every parameter is keyword-only, including `memory`. Two contracts the sketch elides for brevity, stated here because they are load-bearing: `user` and `system` are prompt *templates* rendered against `memory` inside the kernel — template references are how images and documents enter the prompt (task 1.3's assembly functions do the rendering) — and the return value is a small typed result carrying the updated memory plus the rendered prompts, the resolved model setting, and the structuring path taken, because the interpreter's execution-graph tracer consumes those intermediates after generation and recomputing them outside the kernel would mean a second assembly path. Expect the signatures to grow explicit keyword parameters for setting overrides and output multiplicity as tasks 1.1–1.4 extract the real thing; the shape that must survive is fully-named arguments over explicit state.

```python
class MethodKernel:
    """Façade over the module-level kernel ops; holds per-run state."""

    def __init__(self, *, job_metadata: JobMetadata, cogt_run_params: CogtRunParams): ...

    @classmethod
    def make(cls, *, run_mode: PipeRunMode = PipeRunMode.LIVE, user_id: str) -> "MethodKernel": ...

    async def llm_text(
        self,
        *,
        memory: WorkingMemory,
        model: str,
        user: str,
        system: str | None = None,
        result: str,
    ) -> LlmTextResult:
        """The semantics of a PipeLLM step with a Text output.

        `user`/`system` are templates rendered against `memory`; the result
        carries the returned memory plus the rendered prompts and resolved
        setting for the caller's tracing needs.
        """

    async def llm_object(
        self,
        *,
        memory: WorkingMemory,
        output_class: type[StuffContentT],
        concept: Concept,
        model: str,
        user: str,
        system: str | None = None,
        structure_prompt: str | None = None,
        result: str,
    ) -> LlmObjectResult:
        """The semantics of a PipeLLM step with a structured output.

        The concrete pydantic class is handed over directly — no registry lookup,
        and no runtime schema-to-class reconstruction, because the class exists.
        The structure prompt is derived from `output_class` by default (same
        config template as today); pass `structure_prompt` to override it.
        """
```

## Phase 0 — scaffolding

- [x] 0.1 Create the `pipelex/kernel/` package skeleton: façade module (the `MethodKernel` class, thin over module-level functions) plus per-domain ops modules (llm first; extract/img/search/compose/func come in Phase 2), with docstring doctrine stating the layering role. Then, in the **same commit**, the four guard declarations the doctrine section explains:
    - [x] 0.1a Declare `pipelex.kernel` in `RUNTIME_LAYER_PACKAGES` ([`pipelex/cli/dev_cli/commands/hub_layering_guard.py`](../../pipelex/cli/dev_cli/commands/hub_layering_guard.py)) — an undeclared package is unpoliced, not neutral. In the same commit, add `pipelex.kernel` to the runtime-layer enumeration in [`docs/contribute/hub-layering.md`](../../docs/contribute/hub-layering.md): that doc is the boundary's specification, it claims every top-level package is accounted for, and the `hub-layering-convention` drift contract triggers on the guard file — so the doc review is mandatory either way, and same-commit is this task's own discipline applied to the doc half.
    - [x] 0.1b Pin that declaration with a test, mirroring `test_the_measured_clean_packages_stay_declared` ([`tests/unit/pipelex/cli/dev/test_hub_layering_guard.py`](../../tests/unit/pipelex/cli/dev/test_hub_layering_guard.py)), and run the negative control: delete the entry, watch it fail, restore it.
    - [x] 0.1c Write the no-aggregate rule into the kernel's docstring doctrine: import from definition sites only, never from `pipelex.exceptions` or any other cross-layer re-export, and never let `pipelex/kernel/__init__.py` become one (consistent with the repo-wide no-re-exports rule, but stated here because for this package it is a layering property, not a style one). The mechanical half needs no work here: KF-1's tree-wide gate ([`tests/unit/pipelex/test_runtime_layer_exceptions_aggregate_gate.py`](../../tests/unit/pipelex/test_runtime_layer_exceptions_aggregate_gate.py)) walks every package in `RUNTIME_LAYER_PACKAGES` and fails on imports and bare strings alike, module-level or function-local, so 0.1a's declaration buys it — including, for this one hazard, the function-local blind spot 0.1d records. Keep the negative control, which now proves the *coupling* rather than the test: the gate silently covers zero modules when a declared path does not resolve, so add a banned import to a kernel module, watch that gate fail, remove it.
    - [x] 0.1d Add a kernel entry point to `RUNTIME_LAYER_ENTRY_POINTS` in the closure test ([`tests/unit/pipelex/test_runtime_layer_import_closure.py`](../../tests/unit/pipelex/test_runtime_layer_import_closure.py)), with a negative control. Remember its blind spot: it only covers module-level imports — a function-local import is invisible to it *and* to the static graph, so reviews must watch for those by hand.
    - [x] 0.1e **Concept-resolution routing rule.** Kernel run paths answer concept compatibility with the two *pure* tiers that #1072 created — `Concept.are_compatible_by_declaration` (no registry; a caller without a loaded library supplies its own `concept_resolver`, or omits it where no `refines` crosses a package boundary) and `are_structure_classes_compatible` (takes resolved types) — and never call `ConceptLibrary.is_compatible` or `ConceptProviderAbstract.get_structure_class`, which is where resolution and therefore the ambient registry read legitimately live. Passing the concrete class alongside the concept is the preferred shape, as in the target sketch above.
- [x] 0.2 Kernel construction shape: `MethodKernel.make()` mints `JobMetadata` + `CogtRunParams`; decide what the instance holds vs what stays per-call. Two constraints on that decision are settled now. First, the instance holds only identity and run-scoped state (the run-level `JobMetadata`, the `CogtRunParams`); anything derived from config or the model deck — resolved settings, prompting style — is computed per-call and never cached on the instance, exactly the deliberate per-run derivation `pipe_llm.py` documents today, because cached derived state is hidden shared state and breaks per-call `run_mode` variation. Second, the run-level metadata the instance holds is not what a step runs under: each call mints a per-step copy via `copy_with_update` (per-step `pipe_run_id`), matching the interpreter's pass-down-a-modified-copy pattern, so trace and usage attribution stay per-step.

## Phase 1 — LLM vertical slice (the meat)

Each item is a fragment of `PipeLLM` to extract into a kernel function for real:

- [x] 1.1 **Deck-resolution chain**: pipe choice → deck `llm_choice_overrides` → `llm_choice_defaults`, for_text and for_object (including object-falls-back-to-text), → `LLMSetting`. Out of `pipe_llm.py`, into a kernel function.
- [x] 1.2 **Templating-style derivation**: setting/model → `prompting_target` → configured style.
- [x] 1.3 **Prompt assembly**: the full `make_llm_prompt` path (text, images and their `ImageRegistry`, documents as the `[Document N]` substitution dict) as kernel functions, so kernel coverage equals PipeLLM coverage — not just a text-only form. The input shapes need a home and it is not the blueprint: `LLMPromptBlueprint` and its reference types live in `pipe_operators/llm/` and are language-side (blueprints are what `.mthds` parses into), so the kernel cannot import them without breaking the closure. The kernel defines its own runtime-layer prompt-content model (template strings, image/document references over memory) and the blueprint's `make_llm_prompt` becomes a thin mapping onto the kernel functions — the same move `core/` made with `ConceptProviderAbstract`: the semantics migrate to the layer that owns them, the language artifact keeps its parse-and-validate role and maps down.
- [x] 1.4 **`llm_text` / `llm_object` semantics**: structure prompt (settled — see the decision record below: derived in-kernel from `output_class` by default, optional `structure_prompt` argument overrides), output multiplicity (single / variable list / fixed count), result storage into memory, and the typed result envelope the sketch describes (updated memory + rendered prompts + resolved setting + structuring path), which is what lets the interpreter's tracer ride the same functions instead of keeping a parallel path.
- [x] 1.5 **Concrete-class object path**: the kernel's object call passes its `output_class` through to `ContentGenerator.make_object` (whose parameter is named `object_class`), which threads it down since #1076 — so no schema-to-class rebuild happens inline when the class is in hand. The schema round-trip stays where it serves the distributed activity boundary; do not remove it.
- [x] 1.6 **Re-point** `PipeLLM` (and `PipeStructure`, which shares the object semantics) onto the kernel functions. The cut line, stated so nobody has to find it by trial: the interpreter retains blueprint resolution, the library-backed text-vs-object dispatch (`is_compatible` against native Text, `pipe_llm.py`), and its error-context wrapping (`PipeRunError` with the pipe stack — the kernel raises the same cogt-level errors the moved code raises today, and the operator rewraps as it always has); it calls `llm_text` or `llm_object` with resolved values, and the kernel never re-asks the library. Dispatch is the caller's job by construction — the kernel's two entry points are the fork made explicit. One quiet arm belongs on the interpreter's side of that line, cheaper remembered than rediscovered: today `get_output_structure_prompt` returns `None` when the concept's structure class is not in the class registry, and generation proceeds without a structure prompt — the kernel's `llm_object` *requires* `output_class`, so the re-point must keep that no-class arm in the interpreter (it is part of blueprint resolution, not of the kernel's semantics) rather than assume class resolution always succeeds. The zero-behavior-change suite is the backstop; this is the arm it would catch.
- [ ] 1.7 Tests: kernel unit tests (dry mode), naming the kernel-only arms explicitly because the re-pointed interpreter suite structurally cannot reach them — the structure-prompt argument supplied vs derived-by-default, the `concept_resolver`-omitted arm (cross-package `refines` stays unestablished), and the memory mutate-and-return contract; full `make agent-test` green; and the boot contract proven **permanently**, not once: a committed dry-mode pytest boots `RuntimeBoot.make()` in a subprocess (the closure test's isolation pattern — a suite-level boot already holds the process singletons), loads zero `.mthds`, and asserts a kernel `llm_object` call returns a typed result, with a live smoke script kept as the manual Checkpoint C verification. Note for whoever writes that test: it is the first real caller of a runtime-only boot, and `runtime_boot.py`'s orchestrator-rejection comment explicitly defers the external-interpreter-orchestrator half-application question to that first caller (analysed in `wip/boot-split/runtime-boot-external-interpreter-orchestrator.md`) — settle it or guard it there, don't inherit it silently.

**CHECKPOINT A** — LLM slice extracted and re-pointed; gates green (`make agent-check` + full `make agent-test` + `make drift-check`); cold `/code-review` on the diff; update this doc's status block with decisions taken and cold-start state.

## Phase 2 — remaining operators

Same treatment, one operator at a time, interpreter re-pointed as each lands. Each task includes kernel unit tests for that operator's kernel-only arms — the paths the re-pointed interpreter suite never takes are exactly where the two callers could drift undetected.

- [ ] 2.1 `PipeExtract` → kernel extract ops over the `make_extract_pages` seam, including the page-view handling (`should_include_page_views`, `page_views_dpi`, `max_page_images`).
- [ ] 2.2 `PipeImgGen` → kernel image ops (single / list).
- [ ] 2.3 `PipeSearch` → kernel search ops (sourced answer / structured).
- [ ] 2.4 `PipeCompose` → kernel templating + structured-composition ops.
- [ ] 2.5 `PipeFunc` → kernel function-call op over the **`PipeFuncExecutorProtocol` seam**, not a bare registry lookup. The executor is pluggable — `run_pipe_func` (live objects) and `run_pipe_func_transported` (serialized request/response via `pipe_func_execution_dtos`) are its two arms — and the kernel op must carry **both arms**. But the kernel never reads `HubSlot.PIPE_FUNC_EXECUTOR`: that slot is applied in `Pipelex.setup`, so it does not exist on a runtime-only boot, and an ambient read would break the boot contract for this one op. Instead the executor enters as an explicit protocol-typed argument — the interpreter passes its hub-resolved one (selected by `pipe_func_config.execution_mode`, `direct` by default), a programmatic caller passes the direct executor or its own — which also means the protocol needs a runtime-layer home, since it currently lives in `pipe_operators/func/`.

**CHECKPOINT B** — all operators riding the kernel; gates green; this doc updated.

## Phase 3 — memory boundary and run-scoped state parity

- [ ] 3.1 Boundary shaping: kernel `shape_inputs` over the existing `InputShaper` (per-signature specialization is out of scope).
- [ ] 3.2 Result extraction helpers (main-stuff and named-slot, typed).
- [ ] 3.3 Per-step `JobMetadata` semantics (per-step `pipe_run_id` minted from the instance's run-level metadata via `copy_with_update`, per the 0.2 constraint) as a kernel duty; optional trace-context wiring so cost/usage reporting reaches parity when a caller provides one. This task must also answer the lifecycle-ownership question it implies: the interpreter's run machinery is what opens and closes usage reporting today, so state who owns that lifecycle for a kernel-driven run. **Parity bar, measured not asserted:** a test runs an equivalent step through the re-pointed interpreter and through direct kernel calls (mock usage) and asserts the two produced `TokensUsageRecord` lists ([`pipelex/reporting/usage_records.py`](../../pipelex/reporting/usage_records.py)) match in shape and count — the list `/execute` returns on `pipe_output.tokens_usages` and durable runs persist as `tokens_usages.json`.
- [ ] 3.4 Docs: a `docs/` page for the kernel — public-API doctrine, the layering contract, what a programmatic caller may import and how it boots.

**CHECKPOINT C = done** — interpreter operator semantics fully single-sourced in the kernel; smoke run live on it; full gates; this doc updated and the `docs/` page landed.

## Decisions

- **Structure-prompt provenance — SETTLED: derived in-kernel, optional override.** The registry was only ever needed for the concept→class hop, and the kernel's object call already holds the class — so the kernel derives the structure prompt from `output_class` itself (same config template, same `StructurePrinter`, same `is_structure_prompt_enabled` gate as today), and an optional `structure_prompt` argument overrides it for callers who want to supply their own. The interpreter drops `get_output_structure_prompt`'s registry hop and rides the kernel derivation, so both callers produce the same prompt by default — the alternative (prompt as argument only) would have left the derivation outside the kernel and forked the two callers' default behavior, which is the drift this extraction exists to kill.
- **Kernel construction shape** (task 0.2) — **SETTLED as implemented.** `MethodKernel` holds exactly `job_metadata` (run-level, fresh `uuid4` `pipeline_run_id`) and `cogt_run_params`. `make_step_metadata()` mints the per-step copy with a fresh `pipe_run_id` and an explicit `otel_context=None`. Nothing config- or deck-derived is cached.

### Deviations from the plan's letter, taken during Phase 1

- **The deck chain is two functions, not one `resolve_llm_settings`.** `resolve_llm_setting_for_text` and `resolve_llm_setting_for_object` (the latter taking the optional `llm_choice_for_text` that makes its chain one rung longer). A single function returning both settings would have made `PipeStructure` — which resolves only the object setting today — newly resolve the text one too, which is a behavior change on the one gate that matters. Two functions keep each caller resolving exactly what it resolved before, and the chain is still single-sourced.
- **`PipeStructure` rides the kernel's *pieces*, not `run_llm_object`.** It shares the object semantics — structure-prompt derivation, generation, memory write-back — and calls those three kernel functions. It does **not** share prompt assembly: it has no template of its own and no memory-borne references, it renders one configured `structuring_prompt` template over one input string, and forcing that through `assemble_llm_prompt` would have changed the render context from `{"text": …}` to the whole working memory. That is a real behavior change for a cosmetic gain.
- **`templating_style` is an explicit argument to `run_llm_text` / `run_llm_object`, not derived inside them.** `PipeLLM` derives it from its **text** setting and uses it on both paths; a kernel that derived from its own setting would silently change the object path's rendering style. The derivation itself (`derive_templating_style`) is single-sourced in the kernel; *which* setting governs is the caller's decision, and it has to be, because a caller can hold two.
- **One deliberate widening, worth watching in review:** `PipeLLM`'s text path used to wrap only `structure_class(text=…)` in `except ValidationError`. That construction is now inside the kernel call, so the handler wraps the whole call. A `ValidationError` raised elsewhere inside it (prompt assembly, result construction) would now surface as `PipeRunError("Error generating text content in PipeLLM …")` instead of propagating raw. Same error class, same wrap, slightly wider scope.
- **`assemble_llm_prompt` does not log the assembled user text**; `LLMPromptBlueprint.make_llm_prompt` still does, keeping its `output_concept_ref` parameter (whose only job was that log) so ~40 test call sites are untouched. Moving the log into the kernel would have meant either duplicating it or carrying a log-only parameter across the layer boundary.
- **The concept-resolution routing rule (0.1e) is satisfied vacuously in Phase 1.** The LLM kernel ops answer no concept-compatibility question at all — the text-vs-object dispatch stays interpreter-side by construction, which is stronger than routing through the pure tiers. The rule is written into the kernel doctrine and applies to whatever Phase 2 adds; there is no `concept_resolver`-omitted arm to test yet, so task 1.7's third named arm does not exist and should not be invented.

## Non-goals (explicit)

- **Controllers stay interpreter-side.** This effort covers operator semantics only; `pipelex/pipe_controllers/` is untouched.
- **No standalone PyPI distribution yet.** A separately installable kernel dist is a later milestone, once the cogt hub/plugins coupling is unwound; for now the kernel is a subpackage of `pipelex`.
- **No behavior changes and no new operator features.** Extraction is behavior-preserving; the full test suite must pass unmodified.
- **No Temporal activity target.** Activity-shaped is a design constraint on call signatures, not a deliverable of this refactor.

## Key runtime files for the extraction

`pipelex/pipe_operators/llm/pipe_llm.py`, `pipelex/pipe_operators/llm/llm_prompt_blueprint.py`, `pipelex/cogt/content_generation/content_generator.py` (+ `assignment_models.py`, `llm_generate.py`, `schema_to_model_factory.py`), `pipelex/cogt/models/model_deck.py`, `pipelex/core/memory/working_memory.py`.

## Working setup and gates

- **Branch:** `refactor/Kernel` in the `_kernel/` worktree (treat it as repo root), off `dev`; PR targets `dev` on `Pipelex/pipelex`. The branch's `remote` and `pushRemote` are pinned to `origin`.
- **First-time setup:** `make install` (fresh worktree, fresh venv). `derived/mthds_schema.json` is gitignored — regenerate with `.venv/bin/pipelex-dev generate-mthds-schema` if plxt lint complains.
- **Gates at every checkpoint:** `make agent-check`, full `make agent-test`, `make drift-check`. This work touches keyword-only trigger files, so budget for the drift workflow: `make drift-plan` → review → `git add` the trigger files → `make drift-ack CONTRACT=<id> RATIONALE="…"`.
- **Checkpoint discipline:** at each checkpoint, update the status block at the top of this doc with completed phases, decisions taken, open questions, and the current state of the code, so the work hands off cleanly into a fresh session.
