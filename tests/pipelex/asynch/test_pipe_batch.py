# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import pytest
from pytest import FixtureRequest

from pipelex import pretty_print
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.stuff_content import ListContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_report_delegate
from pipelex.job_history import job_history
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeBatch:
    async def test_pipe_batch_basic(
        self,
        request: FixtureRequest,
        pipe_router: PipeRouterProtocol,
    ):
        job_history.activate()

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
        pipe_output: PipeOutput = await pipe_router.run_pipe_code(
            pipe_code="test_pipe_batch",
            pipe_run_params=PipeRunParams(),
            working_memory=working_memory,
        )

        # Log output and generate report
        pretty_print(pipe_output, title="Processing output for invoice")
        get_report_delegate().general_report()

        # Basic assertions
        assert pipe_output is not None
        assert pipe_output.working_memory is not None
        assert pipe_output.main_stuff is not None

        job_history.print_mermaid_flowchart_url()
