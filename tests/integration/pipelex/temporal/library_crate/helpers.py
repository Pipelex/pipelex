"""Shared test helpers for Temporal LibraryCrate integration tests."""

import uuid
from typing import Any

from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager
from temporalio.client import Client as TemporalClient

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_current_library, get_library_manager, set_current_library, teardown_current_library
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.tprl_pipe.hydration import hydrate_working_memory
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter


def rehydrate_pipe_output(pipe_output: PipeOutput, pipe_job: PipeJob | None = None) -> PipeOutput:
    """Rehydrate a deferred PipeOutput received from a Temporal workflow.

    When pipe_job is provided and contains a library_crate, mirrors the
    rehydration that WfPipeRouter performs: creates a temporary library from
    the crate, loads dynamic classes into a scoped registry, hydrates
    WorkingMemory, then tears down the temporary library. This ensures each
    output is hydrated with the correct class registry, even when multiple
    concurrent workflows define conflicting concept names.

    When pipe_job is None, falls back to hydrating with whatever class
    registry is currently active (legacy behavior for single-library tests).
    """
    if pipe_output.working_memory_raw is None:
        return pipe_output

    library_crate = pipe_job.library_crate if pipe_job is not None else None
    if library_crate is None:
        pipe_output.working_memory = hydrate_working_memory(pipe_output.working_memory_raw)
        pipe_output.working_memory_raw = None
        return pipe_output

    # Mirror WfPipeRouter: create per-rehydration library with scoped registry
    library_manager = get_library_manager()
    rehydration_library_id = f"rehydrate_{uuid.uuid4().hex[:8]}"
    _lib_id, rehydration_library = library_manager.open_library(library_id=rehydration_library_id)

    global_registry = KajsonManager.get_class_registry()
    scoped_registry = ClassRegistry()
    if isinstance(global_registry, ClassRegistry):
        scoped_registry.register_classes_dict(dict(global_registry.root))
    rehydration_library.set_class_registry(scoped_registry)

    prev_library_id = _get_current_library_id_or_none()
    set_current_library(library_id=rehydration_library_id)
    try:
        library_manager.load_from_crate(library_id=rehydration_library_id, crate=library_crate)
        pipe_output.working_memory = hydrate_working_memory(pipe_output.working_memory_raw)
        pipe_output.working_memory_raw = None
    finally:
        library_manager.teardown(library_id=rehydration_library_id)
        if prev_library_id is not None:
            set_current_library(library_id=prev_library_id)
        else:
            teardown_current_library()

    return pipe_output


def _get_current_library_id_or_none() -> str | None:
    """Get the current library_id without raising if none is set."""
    try:
        return get_current_library()
    except RuntimeError:
        return None


async def execute_workflow(
    pipe_job: PipeJob,
    temporal_client: TemporalClient,
    task_queue: str,
    **kwargs: Any,
) -> PipeOutput:
    """Execute WfPipeRouter and return PipeOutput, rehydrating if needed."""
    workflow_id = str(uuid.uuid4())
    pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
        workflow=WfPipeRouter.run,
        arg=pipe_job,
        id=workflow_id,
        task_queue=task_queue,
        **kwargs,
    )
    return rehydrate_pipe_output(pipe_output, pipe_job)


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
