---
title: "The Pipelex Kernel"
description: "Operator semantics as importable functions — what pipelex/kernel/ is, the layering contract that keeps it callable without a loaded method, and how a programmatic caller boots it."
---

# The Pipelex Kernel

This page is for contributors working on Pipelex internals, and for anyone embedding the runtime directly rather than running `.mthds` methods. For how the operator classes above it fit into the whole, see [Architecture Overview](./architecture-overview.md).

What a `PipeLLM` step actually *does* — resolve a model off the deck, derive a prompting style, assemble the prompt, generate, write the result into memory — used to be reachable only through a fully booted interpreter with a method loaded. [`pipelex/kernel/`](https://github.com/Pipelex/pipelex/tree/main/pipelex/kernel) holds that semantics as plain functions, so it has **one implementation with two kinds of caller**:

- the interpreter's operator classes (`PipeLLM`, `PipeExtract`, `PipeImgGen`, `PipeSearch`, `PipeCompose`, `PipeFunc`), which resolve blueprints, validate inputs, wrap errors and trace, then call the kernel;
- any **programmatic caller** embedding the runtime, which calls the same functions on a process with zero `.mthds` loaded.

Single-sourcing is the whole point. Two callers with two copies of "what an LLM step means" drift, and nothing tells you when they have.

---

## The boot contract

Every kernel call must be servable on `RuntimeBoot.make()` ([`pipelex/runtime_boot.py`](https://github.com/Pipelex/pipelex/blob/main/pipelex/runtime_boot.py)) — the **runtime-only** composition root, with no interpreter constructed and no library loaded.

```python
from pipelex.runtime_boot import RuntimeBoot
from pipelex.kernel.pipelex_kernel import PipelexKernel

RuntimeBoot.make()
kernel = PipelexKernel.make(user_id="my-service")
```

That boot stands up the model deck, the content generator, the class registry, the reporting delegate and the plugin registries — the machinery inference needs. It does **not** stand up the library manager, the pipe router or the pipeline manager, because a kernel caller has no method to load.

`needs_inference=False` boots keyless (no credentials, no model-deck validation) and sets the forced-DRY flag: every run the process initiates is coerced to `run_mode=DRY`, so the leaves mock instead of calling a provider. `PipelexKernel.make` applies that rule through the same `runtime_hub.resolve_run_mode_for_boot` the pipe tier uses — a second copy of the rule at a second factory is how the two would drift apart.

---

## Layering: what the kernel may and may not touch

| May | May not |
|---|---|
| `pipelex.runtime_hub` — the model deck, the content generator, the reporting delegate | `pipelex.interpreter_hub`, directly or transitively |
| `pipelex.core`, `pipelex.cogt`, `pipelex.tools`, `pipelex.tracing` | `pipelex.libraries`, `pipelex.pipe_operators`, `pipelex.pipe_controllers`, `pipelex.pipe_run`, `pipelex.pipeline`, `pipelex.mthds_parsing`, … |
| Definition-site imports | `pipelex.exceptions` or any other cross-layer re-export aggregate |
| Module-top-level imports | Function-local imports (invisible to the static graph *and* to the import-closure test at once) |

The **caller-facing** API is stricter still: hub-free. Everything method-specific arrives as an explicit argument — the concept, the concrete output class, the resolved setting, the working memory — and never through an ambient lookup. Concept compatibility, when a kernel path needs it at all, goes through the pure tiers (`Concept.are_compatible_by_declaration`, `are_structure_classes_compatible`), never through `ConceptLibrary.is_compatible`.

Four gates hold this, and each covers something the others miss — see [Hub Layering](../contribute/hub-layering.md) for the full picture:

| Gate | What it proves |
|---|---|
| `pipelex-dev check-hub-layering` | No kernel *module* imports the interpreter hub |
| `tests/unit/pipelex/test_runtime_layer_import_closure.py` | A kernel entry point *imports* clean |
| `tests/unit/pipelex/test_runtime_layer_exceptions_aggregate_gate.py` | No kernel module reaches the exceptions aggregate — imports and bare strings alike |
| `tests/unit/pipelex/kernel/test_kernel_boot_contract.py` | Every kernel entry point **runs** on a keyless boot, swept afterwards — except the three `resolve_*_setting` helpers, which read the model deck (a separate question from this one) |

Only the last one can see a function-local interpreter import, and it is **per-function**: it catches one inside `run_search` only by calling `run_search`. Every new kernel entry point owes it an arm.

---

## What a programmatic caller imports

Module-level functions carry the semantics. `PipelexKernel` is a thin façade over the LLM pair, holding the per-run state a caller would otherwise thread through every call; every other operator is called directly.

Both façade calls take the concept and the output class the caller wants, defaulting to `Text` and `TextContent` when it wants neither. `llm_text` accepts them because a text step is not always a *native*-`Text` step: a method may declare its output as a concept refining `Text`, and a façade that hardcoded the native one would write a different concept into memory than the interpreter writes from the same authored declaration.

| Module | Entry points |
|---|---|
| `pipelex.kernel.pipelex_kernel` | `PipelexKernel.make`, `.llm_text`, `.llm_object`, `.make_step_metadata` |
| `pipelex.kernel.llm_ops` | `resolve_llm_setting_for_text` / `_for_object`, `derive_templating_style`, `derive_structure_prompt`, `generate_object_content`, `run_llm_text`, `run_llm_object` |
| `pipelex.kernel.extract_ops` | `resolve_extract_setting`, `build_extract_job_params`, `run_extract` |
| `pipelex.kernel.img_gen_ops` | `resolve_img_gen_setting`, `resolve_default_size`, `build_img_gen_job_params`, `run_img_gen` |
| `pipelex.kernel.search_ops` | `resolve_search_setting`, `run_search` |
| `pipelex.kernel.compose_ops` | `build_compose_context`, `build_composed_content`, `run_compose_template` |
| `pipelex.kernel.func_ops` | `call_registered_function`, `run_func` |
| `pipelex.kernel.memory_ops` | `shape_inputs`, `store_result`, `extract_main_content` / `extract_named_content`, `extract_main_content_as_list` / `extract_named_content_as_list` |
| `pipelex.kernel.llm_prompt_content` | `LlmPromptContent`, `assemble_llm_prompt` |
| `pipelex.kernel.img_gen_prompt` | `assemble_img_gen_prompt` |
| `pipelex.kernel.*_results` | The typed result envelopes |

The two `assemble_*` functions are there because `run_llm_text` and `run_img_gen` both take a *ready* prompt. A caller that could not build one would be holding an operator it cannot reach, which is what image generation was until `assemble_img_gen_prompt` existed: its only builder was an interpreter-layer blueprint. What they own is the part a caller must not re-derive — resolving `ImageReference` and `DocumentReference` out of working memory, and, on the image side, keeping the `[Image N]` tokens numbered from the same registry that orders `input_images`, since a mismatch mislabels which image the prompt is describing and nothing downstream can detect it.

There are **no re-exports**: `pipelex/kernel/__init__.py` holds doctrine and nothing else, and every symbol is imported from the module that defines it. For this package that is a layering property rather than a style one — a module that re-exports across layers is a layer boundary with the sign filed off.

Every kernel function is **fully keyword-only**, with zero entries in `subject_grants.toml`. Call sites name every argument.

---

## The memory boundary

`WorkingMemory` is threaded explicitly: a call takes it and returns it. The contract, which both kinds of caller must read the same way:

!!! warning "Treat the returned memory as the result"
    A kernel call may mutate the memory it was passed **and** returns it. Callers must use the returned one and must not rely on the two being the same object — inline execution aliases them today, and a serialization boundary will not.

`pipelex.kernel.memory_ops` holds the three ends of that boundary — shape in, write back, read out:

- **`shape_inputs`** — interpret raw values against the specs declared for them (Smart Inputs: a bare string becomes the declared concept, a dict validates against a structured one, a list shapes element-wise). It takes a `ConceptProviderAbstract` explicitly, because resolving concepts is what a loaded method's library is for and the kernel must stay callable without one. The interpreter hands over its concept library; a library-free caller supplies its own provider (the boot-contract test shows the smallest one that works — native concepts from `ConceptFactory`, compatibility from the declaration tier, structure classes from the class registry a boot fills).
- **`store_result`** — the write-back every operator's ops end with, and the one place the memory contract is implemented.
- **`extract_main_content` / `extract_named_content`** — the typed read. Needed even though every result envelope already carries the produced content, because those fields are annotated with the base `StuffContent`: pass the class you asked for and get it back narrowed.
- **`extract_main_content_as_list` / `extract_named_content_as_list`** — the same typed read for a call that produced several objects. A multiple-output call stores one `ListContent`, which the single-content reads cannot narrow: the bare item class raises, and `ListContent[item_type]` is rejected by design. These verify every item against `item_type`, so the list comes back typed all the way down.

```python
memory = shape_inputs(inputs={"topic": "kernels"}, concept_provider=provider, input_specs=specs)
result = await kernel.llm_object(memory=memory, output_class=Summary, concept=summary_concept, model=model, user="Summarize $topic", result="summary")
summary = extract_main_content(memory=result.memory, content_type=Summary)
```

Reach for the list pair whenever the call asked for several — `is_multiple_output=True` or `fixed_nb_output=n`:

```python
result = await kernel.llm_object(memory=memory, output_class=Summary, concept=summary_concept, model=model, user="Summarize $topic", result="summaries", is_multiple_output=True)
summaries = extract_main_content_as_list(memory=result.memory, item_type=Summary).items
```

---

## Run-scoped state, and who owns the usage lifecycle

`PipelexKernel` holds exactly two things, both run-scoped identity:

- **`job_metadata`** — the run-level metadata. It is not what a step runs under: every call mints a per-step copy through `make_step_metadata()`, carrying a fresh `pipe_run_id` and inheriting the trace context, so trace and usage attribution stay per-step. This mirrors the interpreter's pass-down-a-modified-copy pattern.
- **`cogt_run_params`** — the execution-mode contract (`run_mode`, and the DRY-only `is_mock_usage` sub-flag) that every cogt leaf reads off the assignment it is handed.

Nothing derived from config or the model deck is cached on the instance — resolved settings and prompting styles are computed per call, because cached derived state would shadow a later config or deck change and break per-call variation.

**Cost and usage reporting is the caller's lifecycle, not the kernel's.** The interpreter's run machinery opens a graph tracer, builds an event log, registers it on the report delegate and closes all three in a `finally`, because it has a run boundary to hang that on. A kernel call has no such boundary — it is one step, and a caller may make one or a thousand. So the kernel takes a `TraceContext` and does exactly one thing with it: stamp it onto every step's `JobMetadata`, which is what the cogt leaf reads to decide whether to emit a usage event.

Everything else is yours:

```python
from pipelex.runtime_hub import get_report_delegate
from pipelex.system.trace_context import TraceContext
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.usage_aggregator import UsageAggregator

event_log = InMemoryEventLog()
trace_context = TraceContext(graph_id=run_id, data_inclusion=data_inclusion, emit_graph_events=False, emit_usage_events=True)
get_report_delegate().set_event_log(context_key=trace_context.lookup_key, event_log=event_log, workflow_id="direct", pipeline_run_id=run_id)
try:
    kernel = PipelexKernel.make(user_id="my-service", trace_context=trace_context)
    ...
    tokens_usages = UsageAggregator.aggregate(event_log.read_events(run_id))
finally:
    get_report_delegate().clear_event_log(context_key=trace_context.lookup_key)
```

Passing a `trace_context` adopts its `graph_id` as the run's `pipeline_run_id`. The two are one identity: letting them diverge would scatter a single run's usage events across two ids, because the registered-context emit path stamps the event log's id while the runner fallback stamps the metadata's — and a read-back keyed on either would silently miss the other's.

`pipelex.tracing` holds both halves a caller needs (`make_event_log` for a configured backend, `UsageAggregator` for the read-back) and is runtime-layer, so none of this costs the boot contract. The records that come out are the same [`TokensUsage` wire records](./tokens-usage-wire-records.md) an `/execute` response carries — pinned by an integration test that runs the same step through both callers and compares them.

---

## What the kernel deliberately does not cover

Two arms of the interpreter stayed interpreter-side, both because moving them would cost more than the caller gains:

- **`PipeCompose`'s construct mode.** Its semantics are `StructuredContentComposer` over a `ConstructBlueprint`, and a blueprint is an MTHDS language artifact with a language-side consumer. A programmatic caller holds real Python and builds its structured object directly rather than describing the construction declaratively. The template path *is* fully extracted, and the one thing both paths share — the three-layer context ordering — is single-sourced in `build_compose_context`.
- **`PipeFunc`'s pluggable executor seam.** The protocol and its DTOs are typed on interpreter models (`PipeRunParams`, `LibraryCrate`), so the kernel cannot name them. What running a function *means* — registry lookup, async-vs-sync dispatch, content coercion — is single-sourced in `call_registered_function`, which both the in-process executor and the kernel's `run_func` ride. What stays outside is *where* the function runs, which is configured deployment machinery rather than operator semantics. So a kernel `run_func` always runs in this process.

Beyond those: controllers are out of scope entirely (`pipelex/pipe_controllers/` is the interpreter's), the kernel is not separately installable from PyPI, and "activity-shaped" is a design constraint on the call signatures rather than a distributed-execution deliverable.
