"""Integration test for dotted-path batch_over resolution in SubPipe.run_pipe()."""

from pathlib import Path
from typing import Callable

import pytest

from pipelex import log, pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_required_pipe
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_run.pipe_run_params import BatchParams, PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestDottedBatchOver:
    async def test_dotted_batch_resolves_nested_list(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ):
        """Test that SubPipe.run_pipe() resolves a dotted-path batch_over and iterates over the nested list.

        Hand-crafts working memory with a SearchResultContent containing DocumentContent sources,
        then runs SubPipe with batch_params pointing to "search_result.sources". Verifies:
        - The dotted path is resolved to the nested list
        - PipeBatch executes one branch per list item
        - The synthetic flat name is cleaned up afterward
        """
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_batch_dotted_path")])

        # Build a SearchResultContent with 3 DocumentContent sources
        search_content = SearchResultContent(
            answer="Mock search answer about testing",
            sources=[
                DocumentContent(url="https://example.com/doc1", title="Document 1"),
                DocumentContent(url="https://example.com/doc2", title="Document 2"),
                DocumentContent(url="https://example.com/doc3", title="Document 3"),
            ],
        )

        # Create Stuff wrapping the SearchResultContent
        search_result_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.SEARCH_RESULT),
            content=search_content,
            name="search_result",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=search_result_stuff)

        # Build SubPipe with dotted-path batch_params
        sub_pipe = SubPipe(
            pipe_code="process_document",
            output_name="processed_docs",
            batch_params=BatchParams(
                input_list_stuff_name="search_result.sources",
                input_item_stuff_name="document",
            ),
        )

        # Get the branch pipe to verify it exists
        branch_pipe = get_required_pipe(pipe_code="process_document")
        log.info(f"Branch pipe: {branch_pipe.code}, inputs: {branch_pipe.inputs}")

        # Run SubPipe
        pipe_output = await sub_pipe.run_pipe(
            calling_pipe_code="test_sequence",
            working_memory=working_memory,
            job_metadata=job_metadata,
            sub_pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
        )

        # Verify output
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        pretty_print(pipe_output, title="SubPipe dotted batch output")

        # Verify synthetic flat name was cleaned up
        final_memory = pipe_output.working_memory
        assert final_memory.get_optional_stuff("search_result__sources") is None, (
            "Synthetic flat name 'search_result__sources' should be cleaned up after batch processing"
        )

        # Original search_result should still be in working memory
        original = final_memory.get_optional_stuff("search_result")
        assert original is not None, "search_result should remain in working memory"

        # Output should be a list with one processed item per source document
        output_list = pipe_output.main_stuff_as_list(item_type=TextContent)
        assert len(output_list.items) == 3, f"Expected 3 processed items (one per source), got {len(output_list.items)}"

        log.info(f"Dotted-path batch resolved and processed {len(output_list.items)} items successfully")
