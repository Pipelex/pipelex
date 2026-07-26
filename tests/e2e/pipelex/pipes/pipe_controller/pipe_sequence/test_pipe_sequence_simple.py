"""Test simple pipe sequence functionality without batching."""

from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.method_hub import get_required_pipe
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio
class TestPipeSequenceSimple:
    async def test_simple_text_sequence(self, job_metadata: JobMetadata, pipe_run_mode: PipeRunMode, load_test_library: Callable[[list[Path]], None]):
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_sequence/")])
        """Test simple text processing sequence without batching."""
        # Create test input
        raw_text_stuff = StuffFactory.make_stuff(
            name="raw_text",
            concept=ConceptFactory.make(
                concept_code="RawText",
                domain_code="simple_text_processing",
                description="simple_text_processing.RawText",
                structure_class_name="TextContent",
            ),
            content=TextContent(text="This is  some  messy    text with bad spacing."),
        )

        # Create working memory with the required input for dry run
        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs([raw_text_stuff])

        pipe = get_required_pipe(pipe_code="simple_text_sequence")
        pipe_output = await pipe.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        pretty_print(pipe_output)
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None
        assert pipe_output.main_stuff.concept.code == "SummaryText"
        assert pipe_output.main_stuff.concept.domain_code == "simple_text_processing"
