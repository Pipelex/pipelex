"""Unit tests for pipe run_pipe method validating inputs before execution.

Tests that run_pipe raises PipeRunInputsError when required inputs are missing from working memory.
"""

from typing import Callable

import pytest

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.exceptions import PipeRunInputsError
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.method_hub import get_concept_library
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata


@pytest.mark.asyncio(loop_scope="class")
class TestPipeValidateBeforeRun:
    """Tests for run_pipe calling validate_before_run."""

    async def test_run_pipe_missing_single_input_raises_error(
        self,
        job_metadata: JobMetadata,
        load_empty_library: Callable[[], None],
    ):
        """Test that run_pipe raises PipeRunInputsError when a required input is missing."""
        load_empty_library()

        blueprint = PipeLLMBlueprint(
            description="Test pipe with single required input",
            inputs={"topic": "native.Text"},
            output="native.Text",
            prompt="Write about $topic",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="test_pipe_missing_input",
            blueprint=blueprint,
        )

        working_memory = WorkingMemoryFactory.make_empty()
        pipe_run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE)

        with pytest.raises(PipeRunInputsError) as exc_info:
            await pipe_llm.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )

        assert exc_info.value.missing_inputs is not None
        assert "topic" in exc_info.value.missing_inputs

    async def test_run_pipe_missing_multiple_inputs_raises_error(
        self,
        job_metadata: JobMetadata,
        load_empty_library: Callable[[], None],
    ):
        """Test that run_pipe reports all missing inputs."""
        load_empty_library()

        blueprint = PipeLLMBlueprint(
            description="Test pipe with multiple required inputs",
            inputs={"topic": "native.Text", "style": "native.Text"},
            output="native.Text",
            prompt="Write about $topic in $style style",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="test_pipe_missing_multiple_inputs",
            blueprint=blueprint,
        )

        working_memory = WorkingMemoryFactory.make_empty()
        pipe_run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE)

        with pytest.raises(PipeRunInputsError) as exc_info:
            await pipe_llm.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )

        assert exc_info.value.missing_inputs is not None
        assert "topic" in exc_info.value.missing_inputs
        assert "style" in exc_info.value.missing_inputs

    async def test_run_pipe_partial_inputs_raises_error_for_missing(
        self,
        job_metadata: JobMetadata,
        load_empty_library: Callable[[], None],
    ):
        """Test that run_pipe raises error only for missing inputs when some are provided."""
        load_empty_library()

        blueprint = PipeLLMBlueprint(
            description="Test pipe with multiple required inputs",
            inputs={"topic": "native.Text", "style": "native.Text"},
            output="native.Text",
            prompt="Write about $topic in $style style",
        )

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="test_pipe_partial_inputs",
            blueprint=blueprint,
        )

        # Provide only one input
        working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(
            pipeline_inputs={"topic": "Python programming"}, concept_provider=get_concept_library()
        )
        pipe_run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE)

        with pytest.raises(PipeRunInputsError) as exc_info:
            await pipe_llm.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )

        assert exc_info.value.missing_inputs is not None
        assert "style" in exc_info.value.missing_inputs
        assert "topic" not in exc_info.value.missing_inputs
