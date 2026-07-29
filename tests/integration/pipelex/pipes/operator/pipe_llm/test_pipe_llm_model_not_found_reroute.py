from pathlib import Path
from typing import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.interpreter_hub import get_pipe_library, get_pipe_router
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLMModelNotFoundReroute:
    async def test_llm_model_not_found_reroutes_to_model_availability_error(
        self,
        job_metadata: JobMetadata,
        load_test_library: Callable[[list[Path]], None],
        mocker: MockerFixture,
    ) -> None:
        """A provider 404 raised as LLMModelNotFoundError from the content generator escapes PipeLLM's
        `except LLMCompletionError`, reaches `except ModelNotFoundError` in PipeOperator._live_run_pipe,
        and surfaces from the router as PipeOperatorModelAvailabilityError carrying the model_handle.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_llm")])

        not_found_error = LLMModelNotFoundError(
            message="LLM model 'gpt-not-a-real-model' not found",
            model_handle="gpt-not-a-real-model",
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(kind=UserActionKind.CHANGE_MODEL, detail="pick an available model"),
        )
        fake_content_generator = mocker.MagicMock()
        fake_content_generator.make_llm_text = mocker.AsyncMock(side_effect=not_found_error)
        mocker.patch("pipelex.pipe_operators.llm.pipe_llm.get_content_generator", return_value=fake_content_generator)

        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="documents",
            pipe_code="adhoc_for_test_llm_model_not_found_reroute",
            blueprint=PipeLLMBlueprint(
                description="LLM model-not-found reroute test",
                output=NativeConceptCode.TEXT,
                prompt="Say hello.",
            ),
        )
        get_pipe_library().add_new_pipe(pipe)

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
            job_metadata=job_metadata,
        )

        with pytest.raises(PipeOperatorModelAvailabilityError) as exc_info:
            await get_pipe_router().run(pipe_job=pipe_job)

        availability_error = exc_info.value
        assert availability_error.model_handle == "gpt-not-a-real-model"
        assert availability_error.fallback_list is None
        assert availability_error.pipe_type == "PipeLLM"
        assert availability_error.pipe_code == "adhoc_for_test_llm_model_not_found_reroute"
        assert isinstance(availability_error.__cause__, LLMModelNotFoundError)
        # The reroute hinges on this: LLMModelNotFoundError is a sibling of LLMCompletionError,
        # so PipeLLM's `except LLMCompletionError` does not swallow it into a PipeRunError.
        assert not isinstance(availability_error.__cause__, LLMCompletionError)
        assert availability_error.__cause__.error_category is InferenceErrorCategory.CONFIGURATION
        assert availability_error.__cause__.error_category.is_retryable is False
