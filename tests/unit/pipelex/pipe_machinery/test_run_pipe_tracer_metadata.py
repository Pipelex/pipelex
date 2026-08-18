"""Verify that PipeAbstract.run_pipe forwards pipe metadata to the graph tracer."""

from typing import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_machinery.pipe_abstract import InputPresenceScan
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from tests.unit.pipelex.graph.conftest import make_trace_context


@pytest.mark.asyncio(loop_scope="class")
class TestRunPipeForwardsTracerMetadata:
    async def test_run_pipe_passes_description_and_domain_code_to_tracer(
        self,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()

        blueprint = PipeLLMBlueprint(
            description="Greet the user with a friendly hello.",
            output="native.Text",
            prompt="Say hello.",
        )
        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="greeting_domain",
            pipe_code="say_hello",
            blueprint=blueprint,
        )

        main_stuff = Stuff(
            stuff_code="main-code",
            stuff_name="main_stuff",
            concept=Concept(
                code="Text",
                domain_code="native",
                description="Plain text",
                structure_class_name="TextContent",
            ),
            content=TextContent(text="hello"),
        )
        expected_output = mocker.MagicMock()
        expected_output.working_memory.get_main_stuff.return_value = main_stuff
        expected_output.working_memory.resolve_main_stuff.return_value = main_stuff
        mocker.patch.object(PipeLLM, "_live_run_operator_pipe", mocker.AsyncMock(return_value=expected_output))
        empty_presence_scan = InputPresenceScan(missing_names=[], forced_absent=[], liftable=[])
        mocker.patch.object(PipeLLM, "validate_before_run", mocker.AsyncMock(return_value=empty_presence_scan))
        mocker.patch.object(PipeLLM, "validate_after_run", mocker.AsyncMock(return_value=None))

        on_pipe_start_mock = mocker.MagicMock(return_value=(None, None))
        mock_manager = mocker.MagicMock()
        mock_manager.on_pipe_start = on_pipe_start_mock
        mocker.patch(
            "pipelex.pipe_machinery.pipe_abstract.GraphTracerManager.get_instance",
            return_value=mock_manager,
        )

        job_metadata = JobMetadata(
            storage_scope="test/scope",
            user_id="pytest",
            pipeline_run_id="test-run-meta",
            trace_context=make_trace_context(graph_id="test-run-meta"),
        )

        await pipe.run_pipe(
            job_metadata=job_metadata,
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
        )

        on_pipe_start_mock.assert_called_once()
        call_kwargs = on_pipe_start_mock.call_args.kwargs
        assert call_kwargs["description"] == "Greet the user with a friendly hello."
        assert call_kwargs["domain_code"] == "greeting_domain"
