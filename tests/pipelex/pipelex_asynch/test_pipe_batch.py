import pytest

from pipelex import pretty_print
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuff_content import ListContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_pipe_router, get_pipeline_tracker, get_report_delegate


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeBatch:
    async def test_pipe_batch_basic(self):
        # Create Stuff objects
        invoice_list_stuff = StuffFactory.make_stuff(
            concept_code="test_pipe_batch.TestPipeBatchItem",
            content=ListContent(
                items=[
                    TextContent(text="data_1"),
                    TextContent(text="data_2"),
                ]
            ),
            name="test_pipe_batch_item",
        )

        # Create Working Memory
        working_memory = WorkingMemoryFactory.make_from_single_stuff(invoice_list_stuff)

        # Run the pipe
        pipe_output: PipeOutput = await get_pipe_router().run_pipe_code(
            pipe_code="test_pipe_batch",
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
            working_memory=working_memory,
        )

        # Log output and generate report
        pretty_print(pipe_output, title="Processing output for invoice")
        get_report_delegate().generate_report()

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        get_pipeline_tracker().output_flowchart()
