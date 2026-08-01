"""The kernel façade: per-run state, so a caller does not thread it through every call.

The semantics live in the module-level ops functions beside this one; the interpreter's operator
classes call those directly, because they already hold everything the façade would supply. This
class exists for the *other* caller — the programmatic one, embedding the runtime — and it holds
exactly two things, both of them run-scoped identity:

- ``job_metadata`` — the **run-level** metadata. It is not what a step runs under: each call mints
  a per-step copy via :meth:`make_step_metadata`, mirroring the interpreter's pass-down-a-modified-copy
  pattern, so trace and usage attribution stay per-step.
- ``cogt_run_params`` — the execution-mode contract (``run_mode``, ``is_mock_usage``) every cogt
  leaf reads off the assignment it is handed.

What it deliberately does **not** hold is anything derived from config or the model deck — resolved
LLM settings, prompting style. Those are computed per call and never cached here, exactly as
``pipe_llm.py`` derives them per run today: cached derived state is hidden shared state, it makes a
later config or deck change invisible to a live kernel, and it breaks per-call variation.
"""

from typing import Self
from uuid import uuid4

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.llm_ops import (
    derive_templating_style,
    resolve_llm_setting_for_object,
    resolve_llm_setting_for_text,
    run_llm_object,
    run_llm_text,
)
from pipelex.kernel.llm_prompt_content import LlmPromptContent
from pipelex.kernel.llm_results import LlmObjectResult, LlmTextResult
from pipelex.runtime_hub import resolve_run_mode_for_boot
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


class MethodKernel:
    """Façade over the module-level kernel ops; holds per-run state."""

    def __init__(self, *, job_metadata: JobMetadata, cogt_run_params: CogtRunParams) -> None:
        self.job_metadata = job_metadata
        self.cogt_run_params = cogt_run_params

    @classmethod
    def make(cls, *, run_mode: PipeRunMode = PipeRunMode.LIVE, user_id: str) -> Self:
        """Mint a kernel for one run: a fresh run id, and the execution-mode contract for it.

        This is a run-params factory, so it owes the same keyless-boot contract as the pipe tier's:
        a process booted with ``needs_inference=False`` forces every run it initiates to DRY, and a
        kernel that skipped that would spend real money on the exact boot this package documents as
        its target. Applied through the shared ``resolve_run_mode_for_boot`` — a second copy of the
        rule at a second factory is how the two would drift.
        """
        return cls(
            job_metadata=JobMetadata(user_id=user_id, pipeline_run_id=str(uuid4())),
            cogt_run_params=CogtRunParams(run_mode=resolve_run_mode_for_boot(requested=run_mode)),
        )

    def make_step_metadata(self) -> JobMetadata:
        """A per-step copy of the run-level metadata, carrying its own ``pipe_run_id``.

        ``otel_context`` is passed explicitly as ``None`` rather than left to inherit, which is the
        contract ``copy_with_update`` states: the field is computed fresh per step by whoever opens
        the span, and a kernel call opens none. Span and trace-context wiring for a kernel-driven
        run is a separate concern from minting the identity, and is not wired here.
        """
        return self.job_metadata.copy_with_update(otel_context=None, pipe_run_id=str(uuid4()))

    async def llm_text(
        self,
        *,
        memory: WorkingMemory,
        model: LLMModelChoice,
        user: str,
        system: str | None = None,
        result: str,
    ) -> LlmTextResult:
        """The semantics of an LLM step with a Text output.

        `user` and `system` are Jinja2 templates rendered against `memory`; the result carries the
        returned memory plus the rendered prompts and the resolved setting. Images and documents
        enter a prompt through references, which this convenience form has none of — build an
        `LlmPromptContent` and call `run_llm_text` directly for those.
        """
        llm_setting = resolve_llm_setting_for_text(llm_choice=model)
        return await run_llm_text(
            memory=memory,
            prompt_content=LlmPromptContent.make_from_text(user=user, system=system),
            llm_setting=llm_setting,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            output_class=TextContent,
            job_metadata=self.make_step_metadata(),
            cogt_run_params=self.cogt_run_params,
            templating_style=derive_templating_style(llm_setting=llm_setting),
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
        result: str,
        is_multiple_output: bool = False,
        fixed_nb_output: int | None = None,
    ) -> LlmObjectResult:
        """The semantics of an LLM step with a structured output.

        The concrete pydantic class is handed over directly — no registry lookup, and no runtime
        schema-to-class reconstruction, because the class exists. The structure prompt is derived
        from `output_class` by default; pass `structure_prompt` to override it. As with `llm_text`,
        prompts carrying image or document references go through `run_llm_object` directly.
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
            templating_style=derive_templating_style(llm_setting=llm_setting),
            result_name=result,
        )
