"""Focused tests for the execution seams ``acquire_library`` / ``prepare_pipe_job``.

These pin the seams as standalone, reusable building blocks (the shape Phase 2's
``BundleValidator`` will compose): ``acquire_library`` loads a bundle into a fresh
library and owns its load-failure teardown; ``prepare_pipe_job`` builds an
equivalent :class:`PipeJob` against an already-open library.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.hub import (
    get_current_library_id_or_none,
    get_library_manager,
    get_required_pipe,
    teardown_current_library,
)
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline import execution_seams as execution_seams_module
from pipelex.pipeline.execution_seams import acquire_library, prepare_pipe_job
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.system.telemetry.otel_constants import OTelConstants

_SEAMS_DOMAIN = "seams_test"
_SEAMS_MTHDS = f"""
domain = "{_SEAMS_DOMAIN}"
description = "Minimal bundle for execution-seams tests"
main_pipe = "echo_topic"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to build a PipeJob"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


def _dry_mock_config() -> PipelineExecutionConfig:
    return get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
        generate_graph=False,
        mock_inputs=True,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestExecutionSeams:
    async def test_acquire_library_loads_bundle_and_returns_main_pipe(self) -> None:
        library_manager = get_library_manager()
        library_id = "seams_acquire_ok_lib"
        returned_id, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_SEAMS_MTHDS])
        try:
            assert returned_id == library_id
            # main_pipe is returned domain-qualified.
            assert qualified_main_pipe is not None
            assert qualified_main_pipe == f"{_SEAMS_DOMAIN}.echo_topic"
            # Library is left open + current; the loaded pipe is resolvable.
            assert get_current_library_id_or_none() == library_id
            assert get_required_pipe(pipe_code=qualified_main_pipe).code == "echo_topic"
        finally:
            library_manager.teardown(library_id=library_id)
            teardown_current_library()

    async def test_acquire_library_tears_down_on_load_failure(self, mocker: MockerFixture) -> None:
        # A failure during the load window (simulated by resolve_library_dirs raising,
        # mirroring the validate_bundle lifecycle tests) must tear the just-opened
        # library down — no leak — and restore the caller's outer current-library
        # (whatever it was, including None) rather than stranding it.
        library_manager = get_library_manager()
        teardown_spy = mocker.spy(library_manager, "teardown")
        mocker.patch.object(
            execution_seams_module,
            "resolve_library_dirs",
            side_effect=TypeError("simulated load failure in acquire_library"),
        )
        teardown_before = teardown_spy.call_count
        prev_library_id = get_current_library_id_or_none()

        with pytest.raises(TypeError):
            acquire_library(library_id="seams_acquire_fail_lib", mthds_contents=[_SEAMS_MTHDS])

        # The just-opened library is torn down exactly once...
        assert teardown_spy.call_count == teardown_before + 1
        assert teardown_spy.call_args_list[-1].kwargs["library_id"] == "seams_acquire_fail_lib"
        # ...and the caller's outer current-library is restored, not left holding the failed one.
        assert get_current_library_id_or_none() == prev_library_id

    async def test_prepare_pipe_job_builds_equivalent_job_against_open_library(self) -> None:
        library_manager = get_library_manager()
        library_id = "seams_prepare_lib"
        _, qualified_main_pipe = acquire_library(library_id=library_id, mthds_contents=[_SEAMS_MTHDS])
        try:
            assert qualified_main_pipe is not None
            pipe = get_required_pipe(pipe_code=qualified_main_pipe)
            pipe_job = await prepare_pipe_job(
                pipe=pipe,
                library_id=library_id,
                execution_config=_dry_mock_config(),
                pipe_run_mode=PipeRunMode.DRY,
                pipeline_run_id="seams-prepare-run-id",
                user_id=OTelConstants.DEFAULT_USER_ID,
            )
            assert pipe_job.pipe.code == "echo_topic"
            assert pipe_job.pipe_run_params.run_mode.is_dry
            assert pipe_job.job_metadata.pipeline_run_id == "seams-prepare-run-id"
            assert pipe_job.library_crate is not None
            # Mock input materialized for the pipe's needed input.
            assert "subject" in pipe_job.get_working_memory().root
        finally:
            library_manager.teardown(library_id=library_id)
            teardown_current_library()
