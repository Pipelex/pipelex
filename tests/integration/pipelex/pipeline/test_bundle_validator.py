"""Integration tests for BundleValidator's real composition (Phase 2).

Unlike the unit suite (which mocks the seams + the run primitive), these run a real pipe DRY
through the composed stack — ``prepare_pipe_job`` + a direct in-process ``PipeRun`` + the real
report registry + real telemetry — to pin the contracts mocks cannot: that a real DRY run
classifies SUCCESS, that the per-sweep registry is closed in ``finally`` (so the constant
``DRY_RUN_UNTITLED`` id does not collide on a second sweep), and that the sweep emits exactly one
``PIPE_DRY_RUN`` event with no stray runner ``PIPELINE_EXECUTE`` / ``PIPELINE_COMPLETE`` events.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.hub import (
    get_library_manager,
    get_required_pipe,
    get_telemetry_manager,
    teardown_current_library,
)
from pipelex.pipeline.bundle_validator import BundleValidator
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.system.telemetry.events import EventName

_BV_DOMAIN = "bundle_validator_test"
_BV_MTHDS = f"""
domain = "{_BV_DOMAIN}"
description = "Minimal bundle for BundleValidator integration tests"
main_pipe = "echo_topic"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to dry-run through BundleValidator"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestBundleValidatorIntegration:
    async def test_validate_pipes_success_real_path(self) -> None:
        library_manager = get_library_manager()
        library_id = "bv_success_lib"
        _, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_BV_MTHDS])
        try:
            assert qualified_main_pipe is not None
            pipe = get_required_pipe(pipe_code=qualified_main_pipe)
            results = await BundleValidator().validate_pipes([pipe], library_id=library_id)
            assert results[pipe.pipe_ref].status.is_success
            assert results[pipe.pipe_ref].pipe_ref == f"{_BV_DOMAIN}.echo_topic"
        finally:
            library_manager.teardown(library_id=library_id)
            teardown_current_library()

    async def test_two_consecutive_sweeps_no_registry_collision(self) -> None:
        # The sweep opens a report registry keyed by the constant DRY_RUN_UNTITLED id. Without
        # close_registry in `finally`, the second sweep's open_registry would raise "already exists"
        # against the REAL report delegate — this asserts the close-in-finally actually fires.
        library_manager = get_library_manager()
        library_id = "bv_two_sweeps_lib"
        _, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_BV_MTHDS])
        try:
            assert qualified_main_pipe is not None
            pipe = get_required_pipe(pipe_code=qualified_main_pipe)
            validator = BundleValidator()
            first = await validator.validate_pipes([pipe], library_id=library_id)
            second = await validator.validate_pipes([pipe], library_id=library_id)
            assert first[pipe.pipe_ref].status.is_success
            assert second[pipe.pipe_ref].status.is_success
        finally:
            library_manager.teardown(library_id=library_id)
            teardown_current_library()

    async def test_one_pipe_dry_run_event_and_no_stray_pipeline_events(self, mocker: MockerFixture) -> None:
        library_manager = get_library_manager()
        library_id = "bv_telemetry_lib"
        _, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_BV_MTHDS])
        try:
            assert qualified_main_pipe is not None
            pipe = get_required_pipe(pipe_code=qualified_main_pipe)
            track_event_spy = mocker.spy(get_telemetry_manager(), "track_event")
            await BundleValidator().validate_pipes([pipe], library_id=library_id)

            emitted_events = [call.kwargs.get("event_name") for call in track_event_spy.call_args_list]
            assert emitted_events.count(EventName.PIPE_DRY_RUN) == 1
            # The sweep never goes through the runner wrapper, so its per-run events must not fire.
            assert EventName.PIPELINE_EXECUTE not in emitted_events
            assert EventName.PIPELINE_COMPLETE not in emitted_events
        finally:
            library_manager.teardown(library_id=library_id)
            teardown_current_library()
