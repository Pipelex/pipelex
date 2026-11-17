"""A `PipeLLM` step whose model's answer does not fit names the model and the concept the step resolved for the run.

The worker knows the model but is handed a schema class, never a concept, so the step fills the concept, on both its
text and object paths, a dynamic output's resolved concept included, and the model it resolved when nothing names one.
"""

from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.kernel.llm_ops import concrete_llm_model_handle, resolve_llm_setting_for_text
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.providers.google.google_exceptions import GoogleLLMWorkerError
from tests.helpers.schema_mismatch import (
    WORKER_MODEL,
    assert_names_model_and_concept,
    make_gemini_type_mismatch,
    make_job_metadata,
    make_rendered_schema_mismatch,
    make_validation_error,
)


def _make_pipe_llm(*, output: str) -> PipeLLM:
    blueprint = PipeLLMBlueprint(description="Write the parcel's summary", output=output, prompt="Summarize the parcel.")
    return PipeFactory[PipeLLM].make_from_blueprint(domain_code="schema_mismatch", pipe_code="summarize_parcel", blueprint=blueprint)


async def _failure_of_pipe_llm(*, pipe_llm: PipeLLM, pipe_run_params: PipeRunParams | None = None) -> PipelexError:
    with pytest.raises(PipelexError) as exc_info:
        await pipe_llm._live_run_operator_pipe(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
            job_metadata=make_job_metadata(),
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=pipe_run_params or PipeRunParamsFactory.make_run_params(),
        )
    return exc_info.value


class TestPipeLLMSchemaMismatch:
    @pytest.mark.asyncio
    async def test_the_object_path_names_the_concept(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """The worker's rendered failure names its model, and the step gives the concept its output declares."""
        load_empty_library()
        object_call = mocker.patch("pipelex.pipe_operators.llm.pipe_llm.run_llm_object", side_effect=make_rendered_schema_mismatch())

        failure = await _failure_of_pipe_llm(pipe_llm=_make_pipe_llm(output="native.Number"))

        object_call.assert_awaited_once()
        assert isinstance(failure, PipeRunError)
        assert_names_model_and_concept(failure=failure, model=WORKER_MODEL, concept="native.Number")

    @pytest.mark.asyncio
    async def test_the_text_path_names_the_concept_and_the_resolved_model(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """Pydantic's refusal carries no model: the step gives the one it resolved, with the concept."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.llm.pipe_llm.run_llm_text", side_effect=make_validation_error())

        failure = await _failure_of_pipe_llm(pipe_llm=_make_pipe_llm(output="native.Text"))

        resolved_model = concrete_llm_model_handle(resolve_llm_setting_for_text().model)
        assert_names_model_and_concept(failure=failure, model=resolved_model, concept="native.Text")

    @pytest.mark.asyncio
    async def test_gemini_s_type_check_passing_the_step_unwrapped_names_the_concept(
        self, load_empty_library: Callable[[], str], mocker: MockerFixture
    ) -> None:
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.llm.pipe_llm.run_llm_object", side_effect=make_gemini_type_mismatch())

        failure = await _failure_of_pipe_llm(pipe_llm=_make_pipe_llm(output="native.Number"))

        assert isinstance(failure, GoogleLLMWorkerError)
        assert_names_model_and_concept(failure=failure, model=WORKER_MODEL, concept="native.Number")

    @pytest.mark.asyncio
    async def test_a_dynamic_output_names_the_concept_of_the_run(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """The pipe declares `Dynamic`; the answer had to fit the concept this run resolved it to."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.llm.pipe_llm.run_llm_text", side_effect=make_rendered_schema_mismatch())
        mocker.patch("pipelex.pipe_operators.llm.pipe_llm.run_llm_object", side_effect=make_rendered_schema_mismatch())

        failure = await _failure_of_pipe_llm(
            pipe_llm=_make_pipe_llm(output="native.Dynamic"),
            pipe_run_params=PipeRunParamsFactory.make_run_params(dynamic_output_concept_ref="native.Number"),
        )

        assert_names_model_and_concept(failure=failure, model=WORKER_MODEL, concept="native.Number")
