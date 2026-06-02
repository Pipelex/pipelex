"""Library-lifecycle guarantee for :meth:`PipelexRunner.execute_pipeline`.

Pins that a *successful* run RESTORES the caller's outer current-library instead of
clobbering it to ``None``.

``pipeline_run_setup`` leaves the run library open and current on success (teardown is
the caller's job — pinned by ``test_pipeline_run_setup_characterization.py``).
``execute_pipeline``'s ``finally`` then tears the run library down, and must restore the
outer binding the caller held before the run — mirroring ``pipeline_run_setup``'s own
error-path restore. Without that, a run started inside an outer-library context leaves the
next operation with "No current library set" (or silently falling back to the global class
registry).

These cases run fully dry (``PipeRunMode.DRY`` + ``mock_inputs``) so no inference happens.
"""

from collections.abc import Callable

import pytest

from pipelex.config import get_config
from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
)
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.runner import PipelexRunner
from pipelex.system.configuration.configs import PipelineExecutionConfig

_RUNNER_LIFECYCLE_DOMAIN = "runner_lifecycle"
_RUNNER_LIFECYCLE_MTHDS = f"""
domain = "{_RUNNER_LIFECYCLE_DOMAIN}"
description = "Minimal bundle for runner library-lifecycle tests"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to exercise the runner library lifecycle"
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
class TestRunnerLibraryLifecycle:
    async def test_success_restores_outer_current_library(self, load_empty_library: Callable[[], str]) -> None:
        # A run started inside an outer-library context must leave that outer library current after a
        # SUCCESSFUL run. We pass no library_id, so the run uses its own auto-generated library id;
        # execute_pipeline's finally tears that run library down and must RESTORE the outer binding
        # rather than clear it to None.
        outer_library_id = load_empty_library()
        try:
            runner = PipelexRunner(
                pipe_run_mode=PipeRunMode.DRY,
                execution_config=_dry_mock_config(),
            )
            await runner.execute_pipeline(
                pipe_code="echo_topic",
                mthds_contents=[_RUNNER_LIFECYCLE_MTHDS],
            )
            # Restored to the outer id, not clobbered to None.
            assert get_current_library_id_or_none() == outer_library_id
        finally:
            clear_current_library()

    async def test_success_clears_when_no_outer_library(self) -> None:
        # With no outer current-library, a successful run leaves no current library — the no-outer
        # branch still clears (set_current_library cannot take None). Clearing first makes this
        # deterministic under xdist's per-worker shared current-library state.
        clear_current_library()
        runner = PipelexRunner(
            pipe_run_mode=PipeRunMode.DRY,
            execution_config=_dry_mock_config(),
        )
        await runner.execute_pipeline(
            pipe_code="echo_topic",
            mthds_contents=[_RUNNER_LIFECYCLE_MTHDS],
        )
        assert get_current_library_id_or_none() is None
