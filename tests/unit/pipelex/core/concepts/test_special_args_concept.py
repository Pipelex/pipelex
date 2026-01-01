from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import (
    ConceptStructureBlueprint,
    ConceptStructureBlueprintFieldType,
)
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff_factory import StuffContentFactory, StuffFactory
from pipelex.hub import get_concept_library, get_pipe_router
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestSpecialArgsConcept:
    async def test_create_concept_with_content_field(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_empty_library: Callable[[], None],
    ):
        """Test creating a concept with a 'content' field and running a pipe that uses it."""
        load_empty_library()
        domain_code = "test"
        concept_library = get_concept_library()

        # Create a ConceptBlueprint with a structure containing "content"
        concept_blueprint = ConceptBlueprint(
            description="A concept with content field",
            structure={
                "content": ConceptStructureBlueprint(
                    description="The main content",
                    type=ConceptStructureBlueprintFieldType.TEXT,
                ),
            },
        )

        # Make a Concept using ConceptFactory
        concept = ConceptFactory.make_from_blueprint(
            domain_code=domain_code,
            concept_code="ContentConcept",
            blueprint_or_string_description=concept_blueprint,
        )

        concept_library.add_new_concept(concept)
        # Verify the concept was created
        assert concept.code == "ContentConcept"
        assert concept.domain_code == domain_code
        assert concept.description == "A concept with content field"

        # Create a PipeLLM that uses the content field
        pipe_llm_blueprint = PipeLLMBlueprint(
            description="A pipe that reads the content",
            inputs={"my_input": "ContentConcept"},
            output="native.Text",
            prompt="read the content, @my_input.content",
        )

        # Make a PipeLLM using PipeFactory
        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_pipe",
            blueprint=pipe_llm_blueprint,
            concept_codes_from_the_same_domain=[concept.code],
        )

        # Verify the pipe was created
        assert pipe_llm.code == "test_pipe"
        assert pipe_llm.domain_code == domain_code

        # Create content for the concept
        content = StuffContentFactory.make_stuff_content_from_concept_required(
            concept=concept,
            value={"content": "This is my content to read"},
        )

        # Create a stuff with the content
        stuff = StuffFactory.make_stuff(
            concept=concept,
            content=content,
            name="my_input",
        )

        # Create working memory with the stuff
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Create and run the pipe job
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe_llm,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=working_memory,
        )

        # Run the pipe
        output = await get_pipe_router().run(pipe_job=pipe_job)

        # Verify output was generated
        pretty_print(output, title="Pipe output")
        assert output is not None
