---
title: "The Pipelex Kernel"
description: "Operator semantics as importable functions — what pipelex/kernel/ is, the layering contract that keeps it callable without a loaded method, and how a programmatic caller boots it."
---

# The Pipelex Kernel

This page is for contributors working on Pipelex internals, and for anyone embedding the kernel directly rather than running `.mthds` methods. For how the operator classes above it fit into the whole, see [Architecture Overview](./architecture-overview.md).

What a `PipeLLM` step actually *does* — resolve a model off the deck, resolve the templating style, assemble the prompt, generate, write the result into memory — used to be reachable only through a fully booted interpreter with a method loaded. [`pipelex/kernel/`](https://github.com/Pipelex/pipelex/tree/main/pipelex/kernel) holds that semantics as plain functions, so it has **one implementation with two kinds of caller**:

- the interpreter's operator classes (`PipeLLM`, `PipeExtract`, `PipeImgGen`, `PipeSearch`, `PipeCompose`, `PipeFunc`), which resolve blueprints, validate inputs, wrap errors and trace, then call the kernel;
- any **programmatic caller** embedding the kernel, which calls the same functions on a process with zero `.mthds` loaded.

Single-sourcing is the whole point. Two callers with two copies of "what an LLM step means" drift, and nothing tells you when they have.

---

## The boot contract

Every kernel call must be servable on `RuntimeBoot.make()` ([`pipelex/runtime_boot.py`](https://github.com/Pipelex/pipelex/blob/main/pipelex/runtime_boot.py)) — the **kernel-only** composition root, with no interpreter constructed and no library loaded.

```python
from pipelex.runtime_boot import RuntimeBoot
from pipelex.kernel.pipelex_kernel import PipelexKernel

RuntimeBoot.make()
kernel = PipelexKernel.make(user_id="my-service", storage_scope="my-service", read_scope=None)
```

That boot stands up the model deck, the content generator, the class registry, the reporting delegate and the plugin registries — the machinery inference needs. It does **not** stand up the library manager, the pipe router or the pipeline manager, because a kernel caller has no method to load.

**`user_id` and `storage_scope` are both required, with no default.** `user_id` is who the run is attributed to; `storage_scope` is the opaque prefix every byte the run writes lands under, composed by *you* from whatever your tenancy model is (`"<org>/<run>"`, `"<customer>/<job>"`, or a flat name for a single-tenant service). The kernel composes its own leaves onto it and never parses it, so it never learns what a tenant is: `assets/` for what you supplied, `generated/` for what the run produced, `results/` for the delivered envelope, and `payloads/` for transport spill. It is validated at construction — one to three path-safe segments — because the value becomes a storage key prefix and a `..` in it would escape the namespace. Neither field defaults, deliberately: a missing identity used to fall back to the tracing placeholder `"anonymous"`, which then became the key prefix, pointing every unauthenticated run at one shared namespace.

**`read_scope` is required too, and `None` is a value you pass, not a default.** It bounds what the run may read: every `pipelex-storage://` key a step reads must lie under it, compared segment by segment, and no step reads a bare path or a `file://` URI from the local disk. `https://` and `data:` URLs are untouched. A value can carry any URL its method or its model chose, so the check runs where values are read, in every content-generation leaf before the dry-run branch, and `shape_inputs` applies it to a table given as a CSV input, which is always a local file. The storage scope must lie under the read scope, since a run reads its own outputs back, and a mismatch is refused at construction. A multi-tenant host passes its tenant's prefix (the hosted platform passes the organization id); `None` is the explicit statement that the run is unscoped, which is the truth for a single-tenant service or a laptop. It has no default for the storage scope's reason: a host that forgot it would run unscoped, and an unscoped run reads every key the process's credentials reach. A refused read raises `UriReadRefusedError`, a caller-facing input error that names where the URL sat and never quotes it.

`needs_inference=False` boots keyless (every enabled backend and model loaded, no credential resolved, no model-deck validation) and sets the forced-DRY flag: every run the process initiates is coerced to `run_mode=DRY`, so the leaves mock instead of calling a provider. `PipelexKernel.make` applies that rule through the same `runtime_hub.resolve_run_mode_for_boot` the pipe tier uses — a second copy of the rule at a second factory is how the two would drift apart.

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
| `tests/unit/pipelex/test_kernel_layer_import_closure.py` | A kernel entry point *imports* clean |
| `tests/unit/pipelex/test_kernel_layer_exceptions_aggregate_gate.py` | No kernel module reaches the exceptions aggregate — imports and bare strings alike |
| `tests/unit/pipelex/kernel/test_kernel_boot_contract.py` | Every kernel entry point **runs** on a keyless boot, swept afterwards — except the deck-reading helpers (`resolve_*_setting`, `served_*_model`, `check_llm_setting_with_served_model`, `concrete_llm_model_handle`), which read the model deck (a separate question from this one) |

Only the last one can see a function-local interpreter import, and it is **per-function**: it catches one inside `run_search` only by calling `run_search`. Every new kernel entry point owes it an arm.

---

## What a programmatic caller imports

Module-level functions carry the semantics. `PipelexKernel` is a thin façade over the LLM pair, holding the per-run state a caller would otherwise thread through every call; every other operator is called directly.

Both façade calls take the concept and the output class the caller wants, defaulting to `Text` and `TextContent` when it wants neither. `llm_text` accepts them because a text step is not always a *native*-`Text` step: a method may declare its output as a concept refining `Text`, and a façade that hardcoded the native one would write a different concept into memory than the interpreter writes from the same authored declaration.

| Module | Entry points |
|---|---|
| `pipelex.kernel.pipelex_kernel` | `PipelexKernel.make`, `.llm_text`, `.llm_object`, `.make_step_metadata`, `.log_context` |
| `pipelex.kernel.llm_ops` | `resolve_llm_setting_for_text` / `_for_object`, `served_llm_model`, `check_llm_setting_with_served_model`, `concrete_llm_model_handle`, `derive_structure_prompt`, `generate_object_content`, `run_llm_text`, `run_llm_object` |
| `pipelex.kernel.templating_style_ops` | `resolve_templating_style` |
| `pipelex.kernel.extract_ops` | `resolve_extract_setting`, `build_extract_job_params`, `run_extract` |
| `pipelex.kernel.img_gen_ops` | `resolve_img_gen_setting`, `resolve_default_size`, `build_img_gen_job_params`, `run_img_gen` |
| `pipelex.kernel.search_ops` | `resolve_search_setting`, `run_search` |
| `pipelex.kernel.judgment_ops` | `judgment_setting_of_choice`, `served_judgment_model`, `resolve_judgment_setting`, `make_verdict_content`, `run_judgment` |
| `pipelex.kernel.compose_ops` | `build_compose_context`, `build_composed_content`, `run_compose_template` |
| `pipelex.kernel.func_ops` | `call_registered_function`, `run_func` |
| `pipelex.kernel.memory_ops` | `shape_inputs`, `store_result`, `extract_main_content` / `extract_named_content`, `extract_main_content_as_list` / `extract_named_content_as_list` |
| `pipelex.kernel.prompt_assembly` | `UserPromptContent`, `AssembledUserPrompt`, `assemble_user_prompt`, `PromptFiles` |
| `pipelex.kernel.llm_prompt_content` | `LlmPromptContent`, `assemble_llm_prompt` |
| `pipelex.kernel.img_gen_prompt` | `assemble_img_gen_prompt` |
| `pipelex.kernel.prompt_references` | `ImageReference` / `ImageReferenceKind`, `DocumentReference` / `DocumentReferenceKind` |
| `pipelex.kernel.*_results` | The typed result envelopes |

The two operator-specific `assemble_*` functions are there because `run_llm_text` and `run_img_gen` both take a *ready* prompt. A caller that could not build one would be holding an operator it cannot reach, which is what image generation was until `assemble_img_gen_prompt` existed: its only builder was an interpreter-layer blueprint. Both are thin over `pipelex.kernel.prompt_assembly`, the user-prompt assembly PipeLLM, PipeImgGen and PipeJudge share. It owns the part a caller must not re-derive: resolving `ImageReference` and `DocumentReference` out of working memory, numbering the files they name, substituting the `[Image N]` and `[Document N]` tokens for direct, list and dotted references, and handing the files over in the order their tokens number them, since a mismatch mislabels which file the prompt is describing and nothing downstream can detect it. `assemble_user_prompt` assembles one template into an `AssembledUserPrompt`, its text with its ordered images and documents; `PromptFiles` is the same numbering shared by several templates of one prompt, a PipeLLM's system and user prompts or a PipeImgGen's positive and negative ones, whose references are all registered before the first renders so their tokens number one sequence. The caller's `extra_params` are copied, never written to.

`served_llm_model` gives the spec of the LLM a handle resolves to on this boot, an alias to its target and a waterfall to its first served member as a run resolves them, or `None` when no backend serves one. `check_llm_setting_with_served_model` refuses an LLM setting the model it resolves to refuses, before anything is spent: it runs the request check the model's backend registered beside its worker factory, which is the check the worker itself runs before every call, against the job params the setting gives once the model's constraints apply, for a text or a structured output. For a built-in backend it raises an `LLMSettingRefusedError`, an `LLMCapabilityError` carrying the worker's reason with the model named by its deck handle rather than by the SDK, backend and provider model id the worker's own refusal names, so its message is shown to a caller even under strict error disclosure. An external plugin's refusal is raised as the plugin wrote it, and its message reaches a caller only when the plugin raised it as caller-facing copy. A backend that registered no check is held to the rule every worker shares, that a model whose spec declares `thinking_mode = "none"` takes no reasoning setting, and a model no backend serves, or whose backend's SDK is not installed, is left to the run. The interpreter's `PipeLLM` and `PipeStructure` call it when a method loads; a programmatic caller calls it before `run_llm_text` or `run_llm_object` to get the same refusal without a call.

`run_judgment` asks one question about the evidence of a prompt. It takes the step's evidence template as a `UserPromptContent`, the same carrier a PipeLLM's user prompt travels in, and assembles it through `assemble_user_prompt`, so the evidence is rendered, and its images and documents numbered into `[Image N]` and `[Document N]` tokens, exactly as a PipeLLM's prompt is; the text and the ordered files become the `JudgmentPrompt` the worker receives. The question arrives as the cogt question with its instructions still a template, rendered against memory as a `BASIC` template, and is sent as the job's only question, under one fixed key. Absence is the template's business: an optional input that holds no value renders as the template says, through `@?name` or a Jinja2 test, and nothing else is left out on the kernel's side. A refusal is a worker outcome like an answer, and `run_judgment`'s policy for it is to fail: one question has nowhere to leave its verdict absent, so it raises `JudgmentRefusedError`, a content error naming the step and the model. The `JudgmentResult` carries the prompt sent and the rendered question beside the verdict, which is what the operator records as its execution data. `make_verdict_content` turns the answer into the verdict native: a yes/no answer's probability decides the verdict against the step's threshold, inclusive, or against 0.5 when none is declared; an answer with no probability keeps the model's own verdict, and when a threshold was declared a live run logs a warning and its `JudgmentResult` reports `threshold_applied` as false. A rating takes the label of the level the answer names off the scale the question declared, since no backend reports one, a dry run included, and its distribution is keyed by the level index written as text. `judgment_setting_of_choice` gives the setting of the step's model, else of the deck's default, and raises `JudgmentModelMissingError` when neither names one, since the deck serves none by default. `served_judgment_model` gives the spec of the model a handle resolves to on this boot, or `None` when no backend serves one, a waterfall none of whose models is served included. `resolve_judgment_setting` then pins the setting to the handle the model resolves to; on a dry run, a model no backend serves on this boot keeps the deck's handle, since no judging worker is called.

**Every entry point that renders a template takes a required `templating_style`** — `run_llm_text`, `run_llm_object`, `derive_structure_prompt`, `assemble_user_prompt`, `assemble_llm_prompt`, `assemble_img_gen_prompt`, `run_search`, `run_judgment`, `run_compose_template`. It is not nullable, and that is the contract: the Jinja2 filters that tag and format a value have no default of their own, so a call that omitted the style would render a prompt in a shape nobody chose. `resolve_templating_style(authored=...)` is what produces one — pass what the caller authored, or `None` to take the runtime default.

There are **no re-exports**: `pipelex/kernel/__init__.py` holds doctrine and nothing else, and every symbol is imported from the module that defines it. For this package that is a layering property rather than a style one — a module that re-exports across layers is a layer boundary with the sign filed off.

Every kernel function is **fully keyword-only**, with zero entries in `subject_grants.toml`. Call sites name every argument.

---

## The memory boundary

`WorkingMemory` is threaded explicitly: a call takes it and returns it. The contract, which both kinds of caller must read the same way:

!!! warning "Treat the returned memory as the result"
    A kernel call may mutate the memory it was passed **and** returns it. Callers must use the returned one and must not rely on the two being the same object — inline execution aliases them today, and a serialization boundary will not.

`pipelex.kernel.memory_ops` holds the three ends of that boundary — shape in, write back, read out:

- **`shape_inputs`** — interpret raw values against the specs declared for them (Smart Inputs: a bare string becomes the declared concept, a dict validates against a structured one, a list shapes element-wise). It takes a `ConceptProviderAbstract` explicitly, because resolving concepts is what a loaded method's library is for and the kernel must stay callable without one. The interpreter hands over its concept library; a library-free caller supplies its own provider (the boot-contract test shows the smallest one that works — native concepts from `ConceptFactory`, compatibility from the declaration tier, structure classes from the class registry a boot fills, and an empty key enumeration, since a provider that builds its concepts on demand stores none under a key).
- **`store_result`** — the write-back every operator's ops end with, and the one place the memory contract is implemented.
- **`extract_main_content` / `extract_named_content`** — the typed read. Needed even though every result envelope already carries the produced content, because those fields are annotated with the base `StuffContent`: pass the class you asked for and get it back narrowed.
- **`extract_main_content_as_list` / `extract_named_content_as_list`** — the same typed read for a call that produced several objects. A multiple-output call stores one `ListContent`, which the single-content reads cannot narrow: the bare item class raises, and `ListContent[item_type]` is rejected by design. These verify every item against `item_type`, so the list comes back typed all the way down.

```python
memory = shape_inputs(inputs={"topic": "kernels"}, concept_provider=provider, input_specs=specs, read_scope=None)
result = await kernel.llm_object(memory=memory, output_class=Summary, concept=summary_concept, model=model, user="Summarize $topic", result="summary")
summary = extract_main_content(memory=result.memory, content_type=Summary)
```

Reach for the list pair whenever the call asked for several — `is_multiple_output=True` or `fixed_nb_output=n`:

```python
result = await kernel.llm_object(
    memory=memory, output_class=Summary, concept=summary_concept, model=model, user="Summarize $topic", result="summaries", is_multiple_output=True
)
summaries = extract_main_content_as_list(memory=result.memory, item_type=Summary).items
```

---

## Run-scoped state, and who owns the usage lifecycle

`PipelexKernel` holds run-scoped identity, plus the one seam that identity needs:

- **`job_metadata`** — the run-level metadata. **The two halves are now separate types, and a caller reading a field off this object must know which half it is in.** `JobMetadata.run_metadata` holds what is constant for the whole run — `user_id`, `pipeline_run_id`, `storage_scope`, `read_scope`, `request_id`, `extras` — and the rest of `JobMetadata` holds what changes per step (`pipe_code`, `pipe_run_id`, `otel_context`). So it is `kernel.job_metadata.run_metadata.pipeline_run_id`, not `kernel.job_metadata.pipeline_run_id`; there is deliberately no read-through accessor, so one fact has one spelling. `user_id`, `storage_scope`, `read_scope`, `request_id` and `extras` are supplied by the host at `PipelexKernel.make(...)` — the last of them opaque, so a multi-tenant host can attribute a kernel-driven run to its own entities without the runtime learning what they are. `request_id` is the inbound request the run serves, validated by `RunMetadata` exactly as on the pipeline entry points, and it is what a hosted deployment filters its logs on. The distinction this bullet already drew informally — run-level metadata, per-step copy — is what the split makes explicit, and it is why the per-step copy can carry the run half through untouched. It is not what a step runs under: every call mints a per-step copy through `make_step_metadata()`, carrying a fresh `pipe_run_id` and inheriting the trace context, so trace and usage attribution stay per-step. This mirrors the interpreter's pass-down-a-modified-copy pattern. `make_step_metadata(pipe_code=…)` names the pipe the step is running — mirroring what the interpreter stamps on its live and dry paths — so log correlation, usage accounting, and the per-step labelling a distributed backend derives see a named step. When no `pipe_code` is supplied the key is omitted from the update rather than passed as `None`, so a run-level `pipe_code` is never silently erased; the direct-call façade (`llm_text`/`llm_object`) stays deliberately anonymous, because the caller ran no pipe.
- **`cogt_run_params`** — the execution-mode contract (`run_mode`, and the DRY-only `is_mock_usage` sub-flag) that every cogt leaf reads off the assignment it is handed.
- **`step_id_source`** — where each step's `pipe_run_id` comes from, defaulting to a fresh `uuid4`, which is what every in-process run wants. It exists for a kernel hosted inside a replay-based executor, where ids minted from a non-replay-safe source take different values each re-execution; such a host injects its own replay-safe source via `PipelexKernel.make(step_id_source=…)`. It is a seam, not state — the kernel never inspects what it returns.
- **The run's own id** follows the same rule, once per run rather than once per step. `make` takes it from a `trace_context`'s `graph_id` when one is given, else from `pipeline_run_id=…`, else from a fresh `uuid4`. **A host inside a replay-based executor must pass one of the two**, because the `uuid4` default re-mints on every replay and the replayed run would then name itself differently from the run it replays. Such a host mints the id from its own replay-safe source (a workflow's deterministic random, or its workflow id) and passes the value; a value is enough here where the step id needs a callable, because the run id is minted exactly once.

Nothing derived from config or the model deck is cached on the instance — resolved settings and templating styles are computed per call, because cached derived state would shadow a later config or deck change and break per-call variation.

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
    kernel = PipelexKernel.make(user_id="my-service", storage_scope="my-service", read_scope=None, trace_context=trace_context)
    ...
    tokens_usages = UsageAggregator.aggregate(event_log.read_events(run_id))
finally:
    get_report_delegate().clear_event_log(context_key=trace_context.lookup_key)
```

Passing a `trace_context` adopts its `graph_id` as the run's `pipeline_run_id`, and passing a `pipeline_run_id` that differs from it raises `ValueError` rather than letting either win. The two are one identity: letting them diverge would scatter a single run's usage events across two ids, because the registered-context emit path stamps the event log's id while the runner fallback stamps the metadata's — and a read-back keyed on either would silently miss the other's.

`pipelex.tracing` holds both halves a caller needs (`make_event_log` for a configured backend, `UsageAggregator` for the read-back) and is kernel-layer, so none of this costs the boot contract. The records that come out are the same [`TokensUsage` wire records](./tokens-usage-wire-records.md) an `/execute` response carries — pinned by an integration test that runs the same step through both callers and compares them.

---

## The log context

A record emitted inside a `log.context` block carries the run's identifiers — `request_id`, `pipeline_run_id` and `pipe_run_id` — as fields a sink can filter on ([Logging](../tools/logging.md#the-run-scoped-context)). The interpreter binds them around a run and around each pipe; a program driving the kernel has no interpreter around it, so the kernel binds them itself, split the same way as the usage lifecycle above.

- **Each step binds itself.** Every kernel function that takes a `job_metadata` — `run_llm_text`, `run_llm_object`, `generate_object_content`, `run_extract`, `run_search`, `run_judgment` and `run_img_gen` — opens its body with `with job_metadata.log_context():`, so every line it emits, from prompt assembly to the memory write-back and any failure raised on the way, names the run and the step. A unit test sweeps `pipelex/kernel/` and fails on a function that takes a `job_metadata` without opening its body that way, so the rule holds for the next function added as well.
- **The host binds the run.** `PipelexKernel.log_context()` binds `request_id` and `pipeline_run_id` and no step, and a host wraps its run in it. The kernel cannot do this for the host, for the reason it cannot own the usage lifecycle: a kernel call has no run boundary to hang the binding on. Inside the host's block, each step's binding merges over the run's for the length of the call, so a line the host emits between two calls names the run, and a line emitted during one names the step as well.

```python
kernel = PipelexKernel.make(user_id="my-service", storage_scope="my-service", read_scope=None, request_id=request_id, pipeline_run_id=run_id)
with kernel.log_context():
    result = await kernel.llm_text(memory=memory, user="Summarize $topic", result="summary")
```

`JobMetadata.log_context()` is the one spelling of the binding, used by both layers and by the interpreter's `PipeRun.run`. Inside the interpreter the kernel's binding changes nothing: the metadata an operator hands the kernel carries the `pipe_run_id` that `live_run_pipe` minted and already bound, so the nested binding rebinds equal values. A test on `PipeLLM` pins that equality for the operator the other kernel-backed operators follow; none of them copies the metadata it hands down, and one that started minting its own id would re-attribute its lines to a pipe run nobody announced. `run_compose_template` and `run_func` take no `job_metadata`, so their lines carry the host's run-level binding and no step.

---

## What the kernel deliberately does not cover

Two arms of the interpreter stayed interpreter-side, both because moving them would cost more than the caller gains:

- **`PipeCompose`'s construct mode.** Its semantics are `StructuredContentComposer` over a `ConstructBlueprint`, and a blueprint is an MTHDS language artifact with a language-side consumer. A programmatic caller holds real Python and builds its structured object directly rather than describing the construction declaratively. The template path *is* fully extracted, and the one thing both paths share — the three-layer context ordering — is single-sourced in `build_compose_context`.
- **`PipeFunc`'s pluggable executor seam.** The protocol and its DTOs are typed on interpreter models (`PipeRunParams`, `LibraryCrate`), so the kernel cannot name them. What running a function *means* — registry lookup, async-vs-sync dispatch, content coercion — is single-sourced in `call_registered_function`, which both the in-process executor and the kernel's `run_func` ride. What stays outside is *where* the function runs, which is configured deployment machinery rather than operator semantics. So a kernel `run_func` always runs in this process.

Beyond those: controllers are out of scope entirely (`pipelex/pipe_controllers/` is the interpreter's), the kernel is not separately installable from PyPI, and "activity-shaped" is a design constraint on the call signatures rather than a distributed-execution deliverable.
