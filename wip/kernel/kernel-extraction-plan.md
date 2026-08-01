# Method kernel extraction — `pipelex/kernel/`

## Status block (update at every checkpoint)

- **Current phase:** Phase 0 — scaffolding. Not started; branch `refactor/Kernel` is fresh off `dev` (`e10a7be2a`).
- **Next action:** task 0.1 — create the `pipelex/kernel/` package skeleton together with its guard declarations, all in the same commit.
- **Open decisions:** the structure-prompt provenance (settle during Phase 1) and the kernel construction shape (task 0.2). Nothing gates Phase 0.

## Goal

Pull operator-execution semantics out of the interpreter's operator classes into shared, importable kernel functions under a new public `pipelex/kernel/` subpackage, and re-point the interpreter onto them — **zero behavior change**. Today, what a `PipeLLM` step actually *does* (deck resolution, templating-style derivation, prompt assembly, generation, memory write-back) is only reachable through a fully booted interpreter with a loaded library. After this refactor, operator semantics have **one implementation with multiple callers**: the interpreter's operators, and any programmatic caller — SDK-style embedding, hosts that boot only the runtime layer — invoking them directly on a `RuntimeBoot`-only process with zero `.mthds` loaded.

This completes the runtime/interpreter layering arc: the hub split (#1062/#1064), layer placement (#1071), concept purity (#1072), the boot split that created `RuntimeBoot` (#1073), the templating-style threading fix (#1074), and the concrete-class object path (#1076). It is a pure refactor, valuable on its own: single-sourced operator semantics are what prevent two callers from drifting apart.

## Doctrine

- **Layering.** The caller-facing kernel API is hub-free: an explicit `MethodKernel` object and explicit arguments, never an ambient lookup. Kernel *internals* may use `pipelex.runtime_hub` — never `pipelex.interpreter_hub`. This is a mechanically enforced rule (the hub-layering guard plus the runtime-layer import-closure test), but #1071's history shows the guard does not hold the line "for free" — see the four sub-tasks under 0.1, which exist because each one closes a hole that episode demonstrated: an *undeclared* package is unpoliced rather than neutral (both guard rules filter through the layer declaration, so omission makes the guard quieter); a declaration with no test pinning it is a comment; a **cross-layer re-export aggregate defeats the guard entirely** (vendor adapters once pulled the interpreter into a declared-clean runtime package by importing from `pipelex.exceptions` instead of the definition site — a module that re-exports across layers is a layer boundary with the sign filed off); and a function-local import is invisible to the static graph and the closure test at once.
- **Calls are activity-shaped.** Explicit, serializable-leaning inputs and outputs; `WorkingMemory` threaded explicitly (taken and returned); no hidden shared state. This is a design constraint, not a deliverable: it keeps a future Temporal-activity wrapping a re-decoration rather than a rewrite.
- **Functions carry the semantics; the class is a façade.** Module-level kernel functions hold the shared implementation. The `MethodKernel` class is a thin ergonomic façade over them, holding the per-run state a caller would otherwise thread through every call. The interpreter's operators call the functions directly.
- **The kernel API is fully keyword-only — zero subject grants.** The governing bar, stricter than the general rubric in [`docs/contribute/keyword-only-arguments.md`](../../docs/contribute/keyword-only-arguments.md): only the first parameter may be positional, and strictly only when it is obviously the subject — named in the function, or as unmistakable. Nothing in the kernel clears that bar: `llm_text` and `llm_object` name what they *produce*, and `memory` is threaded state (taken and returned), not the operand. So `pipelex/kernel/` records no entries in `subject_grants.toml`, every call site names every argument, and `make fix-keyword-only` mechanically produces exactly this form — there is no ordering trap. Any future kernel def that wants a positional subject must clear the stated bar in review first, not in the registry.
- **Boot contract: `RuntimeBoot.make()`** ([`pipelex/runtime_boot.py`](../../pipelex/runtime_boot.py)). Every kernel call must be servable on the runtime-only composition root, with no interpreter constructed and no library loaded. The import-closure test guards this structurally; a live smoke run proves it dynamically.
- **Zero behavior change.** The full `make agent-test` suite is the gate at every checkpoint — no test rewrites, only additions.

## Target caller experience

The sketch below is the API shape to preserve while the internals get extracted for real out of `pipe_llm.py` (which is where the deck chain, style derivation, and prompt assembly currently live). Every parameter is keyword-only, including `memory`.

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
    ) -> WorkingMemory:
        """The semantics of a PipeLLM step with a Text output."""

    async def llm_object(
        self,
        *,
        memory: WorkingMemory,
        output_class: type[StuffContentT],
        concept: Concept,
        model: str,
        user: str,
        system: str | None = None,
        result: str,
    ) -> WorkingMemory:
        """The semantics of a PipeLLM step with a structured output.

        The concrete pydantic class is handed over directly — no registry lookup,
        and no runtime schema-to-class reconstruction, because the class exists.
        """
```

## Phase 0 — scaffolding

- [ ] 0.1 Create the `pipelex/kernel/` package skeleton: façade module (the `MethodKernel` class, thin over module-level functions) plus per-domain ops modules (llm first; extract/img/search/compose/func come in Phase 2), with docstring doctrine stating the layering role. Then, in the **same commit**, the four guard declarations the doctrine section explains:
    - [ ] 0.1a Declare `pipelex.kernel` in `RUNTIME_LAYER_PACKAGES` ([`pipelex/cli/dev_cli/commands/hub_layering_guard.py`](../../pipelex/cli/dev_cli/commands/hub_layering_guard.py)) — an undeclared package is unpoliced, not neutral.
    - [ ] 0.1b Pin that declaration with a test, mirroring `test_the_measured_clean_packages_stay_declared` ([`tests/unit/pipelex/cli/dev/test_hub_layering_guard.py`](../../tests/unit/pipelex/cli/dev/test_hub_layering_guard.py)), and run the negative control: delete the entry, watch it fail, restore it.
    - [ ] 0.1c Write the no-aggregate rule into the kernel's docstring doctrine: import from definition sites only, never from `pipelex.exceptions` or any other cross-layer re-export, and never let `pipelex/kernel/__init__.py` become one (consistent with the repo-wide no-re-exports rule, but stated here because for this package it is a layering property, not a style one).
    - [ ] 0.1d Add a kernel entry point to `RUNTIME_LAYER_ENTRY_POINTS` in the closure test ([`tests/unit/pipelex/test_runtime_layer_import_closure.py`](../../tests/unit/pipelex/test_runtime_layer_import_closure.py)), with a negative control. Remember its blind spot: it only covers module-level imports — a function-local import is invisible to it *and* to the static graph, so reviews must watch for those by hand.
    - [ ] 0.1e **Concept-resolution routing rule.** Kernel run paths answer concept compatibility with the two *pure* tiers that #1072 created — `Concept.are_compatible_by_declaration` (no registry; a caller without a loaded library supplies its own `concept_resolver`, or omits it where no `refines` crosses a package boundary) and `are_structure_classes_compatible` (takes resolved types) — and never call `ConceptLibrary.is_compatible` or `ConceptProviderAbstract.get_structure_class`, which is where resolution and therefore the ambient registry read legitimately live. Passing the concrete class alongside the concept is the preferred shape, as in the target sketch above.
- [ ] 0.2 Kernel construction shape: `MethodKernel.make()` mints `JobMetadata` + `CogtRunParams`; decide what the instance holds vs what stays per-call.

## Phase 1 — LLM vertical slice (the meat)

Each item is a fragment of `PipeLLM` to extract into a kernel function for real:

- [ ] 1.1 **Deck-resolution chain**: pipe choice → deck `llm_choice_overrides` → `llm_choice_defaults`, for_text and for_object (including object-falls-back-to-text), → `LLMSetting`. Out of `pipe_llm.py`, into a kernel function.
- [ ] 1.2 **Templating-style derivation**: setting/model → `prompting_target` → configured style.
- [ ] 1.3 **Prompt assembly**: the full `make_llm_prompt` path (text, images, documents, registries) as kernel functions, so kernel coverage equals PipeLLM coverage — not just a text-only form.
- [ ] 1.4 **`llm_text` / `llm_object` semantics**: structure prompt (see the open decision below), output multiplicity (single / variable list / fixed count), result storage into memory.
- [ ] 1.5 **Concrete-class object path**: the kernel's object call passes `output_class` through to `ContentGenerator.make_object`, which threads it down since #1076 — so no schema-to-class rebuild happens inline when the class is in hand. The schema round-trip stays where it serves the distributed activity boundary; do not remove it.
- [ ] 1.6 **Re-point** `PipeLLM` (and `PipeStructure`, which shares the object semantics) onto the kernel functions.
- [ ] 1.7 Tests: kernel unit tests (dry mode), full `make agent-test` green, plus a smoke script proving the boot contract — `RuntimeBoot.make()`, no `.mthds` loaded, a kernel `llm_object` call returning a typed result.

**CHECKPOINT A** — LLM slice extracted and re-pointed; gates green (`make agent-check` + full `make agent-test` + `make drift-check`); cold `/code-review` on the diff; update this doc's status block with decisions taken and cold-start state.

## Phase 2 — remaining operators

Same treatment, one operator at a time, interpreter re-pointed as each lands:

- [ ] 2.1 `PipeExtract` → kernel extract ops (`extract_pages`, `render_page_views`).
- [ ] 2.2 `PipeImgGen` → kernel image ops (single / list).
- [ ] 2.3 `PipeSearch` → kernel search ops (sourced answer / structured).
- [ ] 2.4 `PipeCompose` → kernel templating + structured-composition ops.
- [ ] 2.5 `PipeFunc` → kernel function-call op over the **`PipeFuncExecutorProtocol` seam**, not a bare registry lookup. The executor is pluggable: `run_pipe_func` (live objects) and `run_pipe_func_transported` (serialized request/response via `pipe_func_execution_dtos`), selected by `pipe_func_config.execution_mode` (`direct` by default) through `HubSlot.PIPE_FUNC_EXECUTOR`. The kernel op must carry **both arms**.

**CHECKPOINT B** — all operators riding the kernel; gates green; this doc updated.

## Phase 3 — memory boundary and run-scoped state parity

- [ ] 3.1 Boundary shaping: kernel `shape_inputs` over the existing `InputShaper` (per-signature specialization is out of scope).
- [ ] 3.2 Result extraction helpers (main-stuff and named-slot, typed).
- [ ] 3.3 Per-step `JobMetadata` semantics (`pipe_run_id` minting, `copy_with_update`) as a kernel duty; optional trace-context wiring so cost/usage reporting reaches parity when a caller provides one. **Parity bar:** a kernel-driven run should be able to produce the same `TokensUsageRecord` list ([`pipelex/reporting/usage_records.py`](../../pipelex/reporting/usage_records.py)) that `/execute` returns on `pipe_output.tokens_usages` and durable runs persist as `tokens_usages.json`.
- [ ] 3.4 Docs: a `docs/` page for the kernel — public-API doctrine, the layering contract, what a programmatic caller may import and how it boots.

**CHECKPOINT C = done** — interpreter operator semantics fully single-sourced in the kernel; smoke run live on it; full gates; this doc updated and the `docs/` page landed.

## Open decisions

- **Structure-prompt provenance (settle during Phase 1).** Proposed: the kernel takes the output-structure prompt as an optional argument. The interpreter passes the registry-derived one (`get_output_structure_prompt` needs a loaded library); a library-free caller supplies its own or omits it. Keeps the kernel library-free.
- **Kernel construction shape** (task 0.2): what `MethodKernel.make()` mints vs what stays per-call.

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
