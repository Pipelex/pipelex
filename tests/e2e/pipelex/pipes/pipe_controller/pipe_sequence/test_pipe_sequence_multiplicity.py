"""Test pipe sequence functionality with output multiplicity and advanced features."""

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexRunner


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio
class TestPipeSequenceMultiplicity:
    async def test_creative_ideation_sequence_with_multiplicity(self, pipe_run_mode: PipeRunMode):
        """Test creative ideation sequence with nb_output and batching."""
        # Create test input
        topic_stuff = StuffFactory.make_stuff(
            name="topic",
            concept=ConceptFactory.make(
                concept_code="CreativeTopic",
                domain_code="creative_ideation",
                description="creative_ideation.CreativeTopic",
                structure_class_name="CreativeTopic",
            ),
            content=TextContent(text="Sustainable transportation solutions for urban areas"),
        )

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs([topic_stuff])

        # Execute the pipeline
        runner = PipelexRunner(
            library_dirs=["tests/integration/pipelex/pipes/controller/pipe_sequence/"],
            pipe_run_mode=pipe_run_mode,
        )
        response = await runner.execute_pipeline(
            pipe_code="creative_ideation_sequence",
            inputs=working_memory,
        )
        pipe_output = response.pipe_output

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None
        assert pipe_output.main_stuff.concept.code == "BestIdea"
        assert pipe_output.main_stuff.concept.domain_code == "creative_ideation"
