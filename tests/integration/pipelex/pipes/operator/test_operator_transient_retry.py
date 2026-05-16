from pathlib import Path
from typing import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_native_concept, get_pipe_library, get_pipe_router, get_required_pipe
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.pipe_run.exceptions import PipeRouterError, PipeRunError
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.asyncio(loop_scope="class")
class TestOperatorTransientRetry:
    async def test_pipe_llm_transient_failure_is_retried(
        self,
        job_metadata: JobMetadata,
        load_test_library: Callable[[list[Path]], None],
        mocker: MockerFixture,
    ) -> None:
        """A TRANSIENT worker failure inside PipeLLM reaches the PipeRouter retry loop.

        PipeLLM wraps the worker's LLMCompletionError into a PipeRunError before it
        reaches the router, so this exercises the cause-chain retry path.
        """
        load_test_library([Path("tests/integration/pipelex/cli/agent_cli")])
        mocker.patch("pipelex.pipe_run.pipe_router_protocol.asyncio.sleep")

        transient_error = LLMCompletionError("LLM provider connection reset", error_category=InferenceErrorCategory.TRANSIENT)
        worker_mock = mocker.patch.object(ContentGenerator, "make_llm_text", side_effect=transient_error)

        router = get_pipe_router()
        max_retries = router.transient_retry_settings.max_transient_retries
        assert max_retries > 0, "this test needs a non-zero retry budget to be meaningful"

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=get_required_pipe(pipe_code="greet"),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
            working_memory=WorkingMemoryFactory.make_empty(),
            job_metadata=job_metadata,
        )

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(pipe_job=pipe_job)

        # The router calls the worker once, then retries it max_transient_retries times.
        assert worker_mock.call_count == 1 + max_retries
        # Option B keeps the operator/router wrapping intact: PipeRouterError -> PipeRunError -> worker error.
        pipe_run_error = exc_info.value.__cause__
        assert isinstance(pipe_run_error, PipeRunError)
        assert isinstance(pipe_run_error.__cause__, LLMCompletionError)

    async def test_pipe_structure_transient_failure_is_retried(
        self,
        job_metadata: JobMetadata,
        load_test_library: Callable[[list[Path]], None],
        mocker: MockerFixture,
    ) -> None:
        """A TRANSIENT worker failure inside PipeStructure is retried the same way as PipeLLM."""
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_structure")])
        mocker.patch("pipelex.pipe_run.pipe_router_protocol.asyncio.sleep")

        transient_error = LLMCompletionError("LLM provider connection reset", error_category=InferenceErrorCategory.TRANSIENT)
        worker_mock = mocker.patch.object(ContentGenerator, "make_object", side_effect=transient_error)

        blueprint = PipeStructureBlueprint(
            description="Structure a draft text into a SimpleResult",
            inputs={"draft_text": NativeConceptCode.TEXT},
            output="SimpleResult",
        )
        pipe = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code="test_pipe_structure",
            pipe_code="adhoc_for_test_transient_retry",
            blueprint=blueprint,
            concept_codes_from_the_same_domain=["SimpleResult"],
        )
        get_pipe_library().add_new_pipe(pipe)

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text="A book titled 'The Pipelex Way' with a score of 9."),
                name="draft_text",
            ),
        )
        router = get_pipe_router()
        max_retries = router.transient_retry_settings.max_transient_retries
        assert max_retries > 0, "this test needs a non-zero retry budget to be meaningful"

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
            working_memory=working_memory,
            job_metadata=job_metadata,
        )

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(pipe_job=pipe_job)

        assert worker_mock.call_count == 1 + max_retries
        pipe_run_error = exc_info.value.__cause__
        assert isinstance(pipe_run_error, PipeRunError)
        assert isinstance(pipe_run_error.__cause__, LLMCompletionError)
