"""The kernel façade: per-run state, so a caller does not thread it through every call.

The semantics live in the module-level ops functions beside this one; the interpreter's operator
classes call those directly, because they already hold everything the façade would supply. This
class exists for the *other* caller — the programmatic one, embedding the kernel — and it holds
only run-scoped identity plus the one seam that identity needs:

- ``job_metadata`` — the **run-level** metadata. It is not what a step runs under: each call mints
  a per-step copy via :meth:`make_step_metadata`, mirroring the interpreter's pass-down-a-modified-copy
  pattern, so trace and usage attribution stay per-step.
- ``cogt_run_params`` — the execution-mode contract (``run_mode``, ``is_mock_usage``) every cogt
  leaf reads off the assignment it is handed.
- ``step_id_source`` — where a step's ``pipe_run_id`` comes from, defaulting to ``uuid4``. A caller
  hosting the kernel inside a replay-based executor injects a replay-safe source; see
  :meth:`make`. It is a seam, not state — the kernel never inspects what it returns.

What it deliberately does **not** hold is anything derived from config or the model deck — resolved
LLM settings, prompting style. Those are computed per call and never cached here, exactly as
``pipe_llm.py`` derives them per run today: cached derived state is hidden shared state, it makes a
later config or deck change invisible to a live kernel, and it breaks per-call variation.

**Who owns the usage/trace lifecycle for a kernel-driven run: the caller, not the kernel.** The
interpreter's run machinery opens a graph tracer, builds the event log, registers it on the report
delegate and closes all three in a ``finally`` — because it has a run boundary to hang that on. A
kernel call has no such boundary: it is one step, and a caller may make one or a thousand. So the
kernel takes a ``TraceContext`` as an argument and does exactly one thing with it — stamp it onto
every step's :class:`JobMetadata`, which is what the cogt leaf reads to decide whether and where to
emit a usage event. Opening the event log, registering it (``get_report_delegate().set_event_log``),
reading the events back and clearing the registration stay the caller's, and they are the whole of
what stands between a kernel run and the interpreter's cost reporting. ``pipelex/tracing/`` holds
both halves a caller needs (``make_event_log``, ``UsageAggregator``) and is kernel-layer, so none of
this costs the boot contract. See ``docs/under-the-hood/pipelex-kernel.md``.
"""

from collections.abc import Callable
from typing import Any, Self
from uuid import uuid4

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams, check_mock_usage_requires_dry
from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.llm_ops import (
    resolve_llm_setting_for_object,
    resolve_llm_setting_for_text,
    run_llm_object,
    run_llm_text,
)
from pipelex.kernel.llm_prompt_content import LlmPromptContent
from pipelex.kernel.llm_results import LlmObjectResult, LlmTextResult
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.runtime_hub import resolve_run_mode_for_boot
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.trace_context import TraceContext
from pipelex.tools.templating.templating_style import TemplatingStyle


def _mint_step_id() -> str:
    """The default per-step id source: a fresh uuid4, which is what every in-process run wants."""
    return str(uuid4())


class PipelexKernel:
    """Façade over the module-level kernel ops; holds per-run state."""

    def __init__(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        step_id_source: Callable[[], str] | None = None,
    ) -> None:
        self.job_metadata = job_metadata
        self.cogt_run_params = cogt_run_params
        self.step_id_source = step_id_source or _mint_step_id

    @classmethod
    def make(
        cls,
        *,
        run_mode: PipeRunMode = PipeRunMode.LIVE,
        user_id: str,
        storage_scope: str,
        is_mock_usage: bool = False,
        trace_context: TraceContext | None = None,
        step_id_source: Callable[[], str] | None = None,
    ) -> Self:
        """Mint a kernel for one run: a run id, the execution-mode contract, and optional tracing.

        This is a run-params factory, so it owes the same keyless-boot contract as the pipe tier's:
        a process booted with ``needs_inference=False`` forces every run it initiates to DRY, and a
        kernel that skipped that would spend real money on the exact boot this package documents as
        its target. Applied through the shared ``resolve_run_mode_for_boot`` — a second copy of the
        rule at a second factory is how the two would drift. And, like the pipe tier's factory, the
        REQUESTED mode is validated before that coercion: ``is_mock_usage`` is a DRY-only sub-flag,
        so an illegal LIVE request must fail loud on every boot rather than be silently legalised by
        a keyless process forcing it to DRY.

        ``trace_context`` is what makes cost/usage reporting reach parity with an interpreter run:
        the cogt leaf emits a usage event only when the metadata it is handed carries one. Passing it
        adopts its ``graph_id`` as this run's ``pipeline_run_id`` rather than minting a fresh id —
        the two are one identity, and letting them diverge would scatter a single run's usage events
        across two ids (the registered-context emit path stamps the event log's id, the runner
        fallback stamps the metadata's), so the read-back would silently miss half of them.

        ``step_id_source`` overrides where each step's ``pipe_run_id`` comes from; it defaults to a
        fresh ``uuid4``, which is what every in-process run wants. It exists for a kernel hosted
        inside a **replay-based** executor, where identifiers minted from a non-replay-safe source
        take different values each time the host re-executes the code. Such a host injects its own
        replay-safe source here; the kernel stays ignorant of it, which is the point of this tier —
        nothing about a durable backend reaches the runtime or the code it runs.
        """
        check_mock_usage_requires_dry(run_mode=run_mode, is_mock_usage=is_mock_usage)
        return cls(
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(
                    user_id=user_id,
                    storage_scope=storage_scope,
                    pipeline_run_id=trace_context.graph_id if trace_context is not None else str(uuid4()),
                ),
                trace_context=trace_context,
            ),
            cogt_run_params=CogtRunParams(run_mode=resolve_run_mode_for_boot(requested=run_mode), is_mock_usage=is_mock_usage),
            step_id_source=step_id_source,
        )

    def make_step_metadata(self, *, pipe_code: str | None = None) -> JobMetadata:
        """A per-step copy of the run-level metadata, carrying its own ``pipe_run_id``.

        ``otel_context`` is passed explicitly as ``None`` rather than left to inherit, which is the
        contract ``copy_with_update`` states: the field is computed fresh per step by whoever opens
        the span, and a kernel call opens none. ``trace_context`` is left to inherit, which is the
        same method's other contract and the reason usage events from every step of a kernel run
        attribute to the one context the caller supplied.

        ``pipe_code`` names the pipe this step is running, mirroring what the interpreter stamps in
        ``pipe_abstract``'s run paths. Anything that attributes work by it — log correlation, usage
        accounting, the per-step labelling a distributed backend derives from the metadata — sees an
        anonymous step without it.

        ⚠ It is **omitted from the update rather than passed as ``None``** when the caller supplies
        none. ``copy_with_update`` applies whatever it is handed, so an unconditional pass would
        overwrite a run-level ``pipe_code`` with ``None`` — turning an optional enrichment into a
        silent erasure for every caller that never asked for it.

        **The façade's own callers below stay anonymous, and that is the honest answer rather than
        an oversight**: ``llm_text`` and ``llm_object`` are the direct-call form, where there is no
        pipe because the caller did not run one. Do not "finish the job" by inventing a name there.
        """
        updates: dict[str, Any] = {"pipe_run_id": self.step_id_source()}
        if pipe_code is not None:
            updates["pipe_code"] = pipe_code
        return self.job_metadata.copy_with_update(otel_context=None, **updates)

    async def llm_text(
        self,
        *,
        memory: WorkingMemory,
        model: LLMModelChoice | None = None,
        user: str,
        system: str | None = None,
        concept: Concept | None = None,
        output_class: type[StuffContent] | None = None,
        templating_style: TemplatingStyle | None = None,
        result: str,
    ) -> LlmTextResult:
        """The semantics of an LLM step with a Text output.

        `user` and `system` are Jinja2 templates rendered against `memory`; the result carries the
        returned memory plus the rendered prompts and the resolved setting. Images and documents
        enter a prompt through references, which this convenience form has none of — build an
        `LlmPromptContent` and call `run_llm_text` directly for those.

        `concept`, `output_class` and `model` are optional and default to what this method used to
        hardcode — native `Text`, `TextContent`, and the deck's own choice. They are parameters
        because the op beneath takes them and the interpreter passes all three: a caller producing a
        concept that *refines* native `Text` must be able to store the declared concept and its
        generated class, or the memory it hands back differs from an interpreted run's for the same
        step and anything reading the result back raises `StuffContentTypeError`. Omitting `model`
        is the ordinary authored case, not an edge one — it defers to the deck exactly as a `$preset`
        does. `llm_object` below has taken all three from the start; this is the same convenience.

        `templating_style` is the same authoring decision a `PipeLLM` declares; omitting it takes the
        runtime default, exactly as an authored pipe that declares nothing does.
        """
        llm_setting = resolve_llm_setting_for_text(llm_choice=model)
        return await run_llm_text(
            memory=memory,
            prompt_content=LlmPromptContent.make_from_text(user=user, system=system),
            llm_setting=llm_setting,
            concept=concept or ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            output_class=output_class or TextContent,
            job_metadata=self.make_step_metadata(),
            cogt_run_params=self.cogt_run_params,
            templating_style=resolve_templating_style(authored=templating_style),
            result_name=result,
        )

    async def llm_object(
        self,
        *,
        memory: WorkingMemory,
        output_class: type[StuffContent],
        concept: Concept,
        model: LLMModelChoice,
        user: str,
        system: str | None = None,
        structure_prompt: str | None = None,
        templating_style: TemplatingStyle | None = None,
        result: str,
        is_multiple_output: bool = False,
        fixed_nb_output: int | None = None,
    ) -> LlmObjectResult:
        """The semantics of an LLM step with a structured output.

        The concrete pydantic class is handed over directly — no registry lookup, and no runtime
        schema-to-class reconstruction, because the class exists. The structure prompt is derived
        from `output_class` by default; pass `structure_prompt` to override it. As with `llm_text`,
        prompts carrying image or document references go through `run_llm_object` directly.

        `templating_style` is the same authoring decision a `PipeLLM` declares; omitting it takes the
        runtime default, exactly as an authored pipe that declares nothing does.
        """
        llm_setting = resolve_llm_setting_for_object(llm_choice=model)
        return await run_llm_object(
            memory=memory,
            prompt_content=LlmPromptContent.make_from_text(user=user, system=system),
            llm_setting=llm_setting,
            concept=concept,
            output_class=output_class,
            job_metadata=self.make_step_metadata(),
            cogt_run_params=self.cogt_run_params,
            structure_prompt=structure_prompt,
            is_multiple_output=is_multiple_output,
            fixed_nb_output=fixed_nb_output,
            templating_style=resolve_templating_style(authored=templating_style),
            result_name=result,
        )
