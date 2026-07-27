from typing import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, SearchJobFailureError, SearchModelNotFoundError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.interpreter_hub import get_pipe_library, get_pipe_router
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_operators.search.pipe_search import PipeSearch
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata


@pytest.mark.asyncio(loop_scope="class")
class TestPipeSearchModelNotFoundReroute:
    async def test_search_model_not_found_reroutes_to_model_availability_error(
        self,
        job_metadata: JobMetadata,
        load_empty_library: Callable[[], None],
        mocker: MockerFixture,
    ) -> None:
        """A provider 404 raised as SearchModelNotFoundError from the search worker escapes the
        search operator's generic-error handling, reaches `except ModelNotFoundError` in
        PipeOperator._live_run_pipe, and surfaces as PipeOperatorModelAvailabilityError.
        """
        load_empty_library()

        not_found_error = SearchModelNotFoundError(
            message="Search model 'search-not-a-real-model' not found",
            model_handle="search-not-a-real-model",
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(kind=UserActionKind.CHANGE_MODEL, detail="pick an available model"),
        )
        fake_worker = mocker.MagicMock()
        fake_worker.search_sourced_answer = mocker.AsyncMock(side_effect=not_found_error)
        mocker.patch(
            "pipelex.cogt.content_generation.search_generate.SearchWorkerFactory.make_search_worker",
            return_value=fake_worker,
        )

        pipe = PipeFactory[PipeSearch].make_from_blueprint(
            domain_code="generic",
            pipe_code="adhoc_for_test_search_model_not_found_reroute",
            blueprint=PipeSearchBlueprint(
                description="Search model-not-found reroute test",
                output=NativeConceptCode.SEARCH_RESULT,
                prompt="Search for recent technology news.",
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
        assert availability_error.model_handle == "search-not-a-real-model"
        assert availability_error.fallback_list is None
        assert availability_error.pipe_type == "PipeSearch"
        assert availability_error.pipe_code == "adhoc_for_test_search_model_not_found_reroute"
        assert isinstance(availability_error.__cause__, SearchModelNotFoundError)
        # The reroute hinges on this: SearchModelNotFoundError is a sibling of SearchJobFailureError —
        # they share no inheritance, so the model-not-found case takes the specialized class and reroutes,
        # while every other SDK error stays on SearchJobFailureError and surfaces as a hard failure.
        assert not isinstance(availability_error.__cause__, SearchJobFailureError)
        assert availability_error.__cause__.error_category is InferenceErrorCategory.CONFIGURATION
        assert availability_error.__cause__.error_category.is_retryable is False
