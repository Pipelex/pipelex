"""Integration test for the ``is_mock_inference`` hard guard for web search.

Web search has no leaf-level mock. It now goes through the same ``cogt/content_generation`` seam as
LLM/img-gen/extract: ``PipeSearch`` calls the content generator, whose direct impl runs the
framework-agnostic ``search_generate`` leaf. Under ``--mock-inference`` (``run_mode=LIVE`` +
``CogtRunParams.is_mock_inference``) the live path runs, so the guard lives at the top of that leaf
(``search_gen_sourced_answer``) and must fail loud before the search worker is built.
``MockInferenceUnsupportedError`` is a plain ``PipelexError`` (not a model-availability error and not a
``CogtError``), so neither ``PipeOperator._live_run_pipe`` nor the router re-wraps it — it propagates
unchanged.
"""

from typing import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.exceptions import MockInferenceUnsupportedError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.hub import get_pipe_library, get_pipe_router
from pipelex.pipe_operators.search.pipe_search import PipeSearch
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.asyncio(loop_scope="class")
class TestPipeSearchMockInferenceGuard:
    async def test_mock_inference_raises_before_building_search_worker(
        self,
        job_metadata: JobMetadata,
        load_empty_library: Callable[[], None],
        mocker: MockerFixture,
    ) -> None:
        """A LIVE PipeSearch run with is_mock_inference=True raises the guard before any provider call."""
        load_empty_library()

        worker_factory_spy = mocker.patch("pipelex.cogt.content_generation.search_generate.SearchWorkerFactory.make_search_worker")

        pipe = PipeFactory[PipeSearch].make_from_blueprint(
            domain_code="generic",
            pipe_code="adhoc_for_test_search_mock_inference_guard",
            blueprint=PipeSearchBlueprint(
                description="Search mock-inference guard test",
                output=NativeConceptCode.SEARCH_RESULT,
                prompt="Search for recent technology news.",
            ),
        )
        get_pipe_library().add_new_pipe(pipe)

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE, is_mock_inference=True),
            job_metadata=job_metadata,
        )

        with pytest.raises(MockInferenceUnsupportedError):
            await get_pipe_router().run(pipe_job=pipe_job)

        worker_factory_spy.assert_not_called()  # no provider call -> no spend
