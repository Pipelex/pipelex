from typing import cast

import pytest
from pytest import FixtureRequest

from pipelex import pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_pipe_router, get_required_pipe
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.test_pipelines.pipe_controllers.pipe_parallel.pipe_parallel import ContentAnalysis, DocumentInput, LengthAnalysis


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeParallelDocumentAnalysis:
    @pytest.mark.parametrize(
        "document_text",
        [
            "This is a short document about artificial intelligence and machine learning.",
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
            "The quick brown fox jumps over the lazy dog. This pangram contains every letter of the alphabet.",
        ],
    )
    async def test_pipe_parallel_document_analysis(
        self,
        request: FixtureRequest,
        pipe_run_mode: PipeRunMode,
        document_text: str,
    ):
        """Test that PipeParallel processes document analysis in parallel."""
        # Create input data
        document_input = DocumentInput(text=document_text)
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make(
                concept_code="DocumentInput",
                domain="test_pipe_parallel",
                description="test_pipe_parallel.DocumentInput",
                structure_class_name="DocumentInput",
            ),
            content=document_input,
            name="document",
        )

        # Create Working Memory
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff)

        # Run the pipe
        pipe_output = await get_pipe_router().run(
            pipe_job=PipeJobFactory.make_pipe_job(
                pipe=get_required_pipe(pipe_code="parallel_document_analysis"),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                working_memory=working_memory,
                job_metadata=JobMetadata(job_name=request.node.originalname),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            ),
        )

        # Log output and generate report
        pretty_print(pipe_output, title="PipeParallel document analysis test")

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        # Check that both parallel results are available in working memory
        length_result_stuff = pipe_output.working_memory.get_optional_stuff("length_result")
        content_result_stuff = pipe_output.working_memory.get_optional_stuff("content_result")
        assert length_result_stuff is not None
        assert content_result_stuff is not None

        # Verify the combined output structure
        combined_analysis = pipe_output.main_stuff.content
        assert hasattr(combined_analysis, "length_result")
        assert hasattr(combined_analysis, "content_result")

        # Verify that both analyses contain meaningful content
        length_analysis = cast("LengthAnalysis", length_result_stuff.content)
        content_analysis = cast("ContentAnalysis", content_result_stuff.content)

        assert isinstance(length_analysis.analysis, str)
        assert isinstance(content_analysis.analysis, str)
        assert len(length_analysis.analysis) > 0
        assert len(content_analysis.analysis) > 0
