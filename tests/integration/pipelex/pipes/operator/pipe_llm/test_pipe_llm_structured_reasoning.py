"""A PipeLLM with a structured output and a reasoning effort, run for real.

This is the shape every deck reasoning preset takes on a structured pipe: no `model_to_structure`, so the
object is generated with the text model setting, its reasoning effort included. Every worker used to refuse
that call outright, so the presets named for careful reasoning failed on any structured output.
"""

from pathlib import Path
from typing import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex import pretty_print
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import ReasoningEffort
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept, get_pipe_router, get_required_entry_pipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.runtime_hub import get_report_delegate
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLMStructuredReasoning:
    async def test_a_structured_output_is_generated_with_the_reasoning_effort(
        self,
        mocker: MockerFixture,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_llm")])
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text="Which is larger: 0.9 or 0.11?"),
                name="question",
            ),
        )
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=get_required_entry_pipe(pipe_code="test_structured_reasoning.compare_numbers"),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=working_memory,
        )
        report_spy = mocker.spy(get_report_delegate(), "report_inference_job")

        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        pretty_print(pipe_output.main_stuff, title="Structured output with a reasoning effort")
        assert pipe_output.main_stuff.concept.code == "ComparisonVerdict"
        if pipe_run_mode.is_live:
            verdict = pipe_output.main_stuff.content
            assert isinstance(getattr(verdict, "larger_number", None), str)
            reasons = getattr(verdict, "reasons", None)
            assert isinstance(reasons, list)
            assert reasons
            (llm_job,) = [call.kwargs["inference_job"] for call in report_spy.call_args_list if isinstance(call.kwargs.get("inference_job"), LLMJob)]
            assert llm_job.job_params.reasoning_effort == ReasoningEffort.LOW
