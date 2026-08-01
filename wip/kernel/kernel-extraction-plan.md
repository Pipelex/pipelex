# Method kernel extraction — `pipelex/kernel/`

## Status block (update at every checkpoint)

- **Current phase:** Phase 0 — scaffolding. Not started; branch `refactor/Kernel` is off `dev`, with `dev` merged in at `221b8ee0b` — which brought KF-1's tree-wide aggregate gate and shrank task 0.1c to prose plus a negative control (see [`deferred-follow-ups.md`](deferred-follow-ups.md)). Plan revised after engineering review: structure-prompt provenance settled (derive in-kernel from `output_class`, optional override), result envelope and memory contract pinned, prompt-content model home decided (kernel-native, blueprint maps down), PipeFunc executor enters as an explicit argument.
- **Next action:** task 0.1 — create the `pipelex/kernel/` package skeleton together with its guard declarations, all in the same commit.
- **Open decisions:** the kernel construction shape (task 0.2, partially settled — see Decisions). Nothing gates Phase 0.

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

- [ ] 0.1 Create the `pipelex/kernel/` package skeleton: façade module (the `MethodKernel` class, thin over module-level functions) plus per-domain ops modules (llm first; extract/img/search/compose/func come in Phase 2), with docstring doctrine stating the layering role. Then, in the **same commit**, the four guard declarations the doctrine section explains:
    - [ ] 0.1a Declare `pipelex.kernel` in `RUNTIME_LAYER_PACKAGES` ([`pipelex/cli/dev_cli/commands/hub_layering_guard.py`](../../pipelex/cli/dev_cli/commands/hub_layering_guard.py)) — an undeclared package is unpoliced, not neutral. In the same commit, add `pipelex.kernel` to the runtime-layer enumeration in [`docs/contribute/hub-layering.md`](../../docs/contribute/hub-layering.md): that doc is the boundary's specification, it claims every top-level package is accounted for, and the `hub-layering-convention` drift contract triggers on the guard file — so the doc review is mandatory either way, and same-commit is this task's own discipline applied to the doc half.
    - [ ] 0.1b Pin that declaration with a test, mirroring `test_the_measured_clean_packages_stay_declared` ([`tests/unit/pipelex/cli/dev/test_hub_layering_guard.py`](../../tests/unit/pipelex/cli/dev/test_hub_layering_guard.py)), and run the negative control: delete the entry, watch it fail, restore it.
    - [ ] 0.1c Write the no-aggregate rule into the kernel's docstring doctrine: import from definition sites only, never from `pipelex.exceptions` or any other cross-layer re-export, and never let `pipelex/kernel/__init__.py` become one (consistent with the repo-wide no-re-exports rule, but stated here because for this package it is a layering property, not a style one). The mechanical half needs no work here: KF-1's tree-wide gate ([`tests/unit/pipelex/test_runtime_layer_exceptions_aggregate_gate.py`](../../tests/unit/pipelex/test_runtime_layer_exceptions_aggregate_gate.py)) walks every package in `RUNTIME_LAYER_PACKAGES` and fails on imports and bare strings alike, module-level or function-local, so 0.1a's declaration buys it — including, for this one hazard, the function-local blind spot 0.1d records. Keep the negative control, which now proves the *coupling* rather than the test: the gate silently covers zero modules when a declared path does not resolve, so add a banned import to a kernel module, watch that gate fail, remove it.
    - [ ] 0.1d Add a kernel entry point to `RUNTIME_LAYER_ENTRY_POINTS` in the closure test ([`tests/unit/pipelex/test_runtime_layer_import_closure.py`](../../tests/unit/pipelex/test_runtime_layer_import_closure.py)), with a negative control. Remember its blind spot: it only covers module-level imports — a function-local import is invisible to it *and* to the static graph, so reviews must watch for those by hand.
    - [ ] 0.1e **Concept-resolution routing rule.** Kernel run paths answer concept compatibility with the two *pure* tiers that #1072 created — `Concept.are_compatible_by_declaration` (no registry; a caller without a loaded library supplies its own `concept_resolver`, or omits it where no `refines` crosses a package boundary) and `are_structure_classes_compatible` (takes resolved types) — and never call `ConceptLibrary.is_compatible` or `ConceptProviderAbstract.get_structure_class`, which is where resolution and therefore the ambient registry read legitimately live. Passing the concrete class alongside the concept is the preferred shape, as in the target sketch above.
- [ ] 0.2 Kernel construction shape: `MethodKernel.make()` mints `JobMetadata` + `CogtRunParams`; decide what the instance holds vs what stays per-call. Two constraints on that decision are settled now. First, the instance holds only identity and run-scoped state (the run-level `JobMetadata`, the `CogtRunParams`); anything derived from config or the model deck — resolved settings, prompting style — is computed per-call and never cached on the instance, exactly the deliberate per-run derivation `pipe_llm.py` documents today, because cached derived state is hidden shared state and breaks per-call `run_mode` variation. Second, the run-level metadata the instance holds is not what a step runs under: each call mints a per-step copy via `copy_with_update` (per-step `pipe_run_id`), matching the interpreter's pass-down-a-modified-copy pattern, so trace and usage attribution stay per-step.

## Phase 1 — LLM vertical slice (the meat)

Each item is a fragment of `PipeLLM` to extract into a kernel function for real:

- [ ] 1.1 **Deck-resolution chain**: pipe choice → deck `llm_choice_overrides` → `llm_choice_defaults`, for_text and for_object (including object-falls-back-to-text), → `LLMSetting`. Out of `pipe_llm.py`, into a kernel function.
- [ ] 1.2 **Templating-style derivation**: setting/model → `prompting_target` → configured style.
- [ ] 1.3 **Prompt assembly**: the full `make_llm_prompt` path (text, images and their `ImageRegistry`, documents as the `[Document N]` substitution dict) as kernel functions, so kernel coverage equals PipeLLM coverage — not just a text-only form. The input shapes need a home and it is not the blueprint: `LLMPromptBlueprint` and its reference types live in `pipe_operators/llm/` and are language-side (blueprints are what `.mthds` parses into), so the kernel cannot import them without breaking the closure. The kernel defines its own runtime-layer prompt-content model (template strings, image/document references over memory) and the blueprint's `make_llm_prompt` becomes a thin mapping onto the kernel functions — the same move `core/` made with `ConceptProviderAbstract`: the semantics migrate to the layer that owns them, the language artifact keeps its parse-and-validate role and maps down.
- [ ] 1.4 **`llm_text` / `llm_object` semantics**: structure prompt (settled — see the decision record below: derived in-kernel from `output_class` by default, optional `structure_prompt` argument overrides), output multiplicity (single / variable list / fixed count), result storage into memory, and the typed result envelope the sketch describes (updated memory + rendered prompts + resolved setting + structuring path), which is what lets the interpreter's tracer ride the same functions instead of keeping a parallel path.
- [ ] 1.5 **Concrete-class object path**: the kernel's object call passes its `output_class` through to `ContentGenerator.make_object` (whose parameter is named `object_class`), which threads it down since #1076 — so no schema-to-class rebuild happens inline when the class is in hand. The schema round-trip stays where it serves the distributed activity boundary; do not remove it.
- [ ] 1.6 **Re-point** `PipeLLM` (and `PipeStructure`, which shares the object semantics) onto the kernel functions. The cut line, stated so nobody has to find it by trial: the interpreter retains blueprint resolution, the library-backed text-vs-object dispatch (`is_compatible` against native Text, `pipe_llm.py`), and its error-context wrapping (`PipeRunError` with the pipe stack — the kernel raises the same cogt-level errors the moved code raises today, and the operator rewraps as it always has); it calls `llm_text` or `llm_object` with resolved values, and the kernel never re-asks the library. Dispatch is the caller's job by construction — the kernel's two entry points are the fork made explicit. One quiet arm belongs on the interpreter's side of that line, cheaper remembered than rediscovered: today `get_output_structure_prompt` returns `None` when the concept's structure class is not in the class registry, and generation proceeds without a structure prompt — the kernel's `llm_object` *requires* `output_class`, so the re-point must keep that no-class arm in the interpreter (it is part of blueprint resolution, not of the kernel's semantics) rather than assume class resolution always succeeds. The zero-behavior-change suite is the backstop; this is the arm it would catch.
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
- **Kernel construction shape** (task 0.2) — still open in part: what else the instance holds beyond the settled constraints recorded in 0.2 (identity/run-scoped state only, per-call derivation of anything config- or deck-derived, per-step metadata minting).

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
