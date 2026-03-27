"""Shared test helpers for Temporal LibraryCrate integration tests."""

import uuid

from temporalio.client import Client as TemporalClient

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter


async def execute_workflow(
    pipe_job: PipeJob,
    temporal_client: TemporalClient,
    task_queue: str,
) -> PipeOutput:
    """Execute WfPipeRouter and return PipeOutput."""
    workflow_id = str(uuid.uuid4())
    pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
        workflow=WfPipeRouter.run,
        arg=pipe_job,
        id=workflow_id,
        task_queue=task_queue,
    )
    return pipe_output


def assert_stuff_names(pipe_output: PipeOutput, expected_names: list[str]) -> None:
    """Assert that all expected stuffs exist in the output with non-None content."""
    working_memory = pipe_output.working_memory
    assert working_memory is not None
    for stuff_name in expected_names:
        assert working_memory.is_stuff_exists(stuff_name), f"Expected stuff '{stuff_name}' missing from output"
        stuff = working_memory.get_stuff(stuff_name)
        assert stuff.content is not None, f"Stuff '{stuff_name}' has no content"


def assert_text_stuff_names(pipe_output: PipeOutput, expected_names: list[str]) -> None:
    """Assert that all expected stuffs exist and contain TextContent."""
    assert_stuff_names(pipe_output, expected_names)
    working_memory = pipe_output.working_memory
    assert working_memory is not None
    for stuff_name in expected_names:
        stuff = working_memory.get_stuff(stuff_name)
        assert isinstance(stuff.content, TextContent), f"Expected TextContent for '{stuff_name}', got {type(stuff.content).__name__}"


def assert_structured_fields(pipe_output: PipeOutput, stuff_name: str, expected_fields: list[str]) -> None:
    """Assert that a stuff's content is StructuredContent with the expected fields."""
    working_memory = pipe_output.working_memory
    assert working_memory is not None
    stuff = working_memory.get_stuff(stuff_name)
    assert isinstance(stuff.content, StructuredContent), f"Expected StructuredContent for '{stuff_name}', got {type(stuff.content).__name__}"
    for field in expected_fields:
        assert hasattr(stuff.content, field), f"StructuredContent for '{stuff_name}' missing field '{field}'"
