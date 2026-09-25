"""``pipeline_run_setup`` hands the run's identity to the two telemetry emissions it makes.

The trace-start event and ``pipeline_execute`` are the only telemetry this seam
emits, and both used to report under the process identity — the trace-start under
the configured id or the gateway hash, and the event under whichever the stream
resolved. Both now name the run, which is what makes a trace and its spans land
on one person instead of two.

It also pins WHERE the trace-start is emitted. It sits below ``prepare_pipe_job``
because that seam builds the run's ``RunMetadata``, and the event has to be
attributed to the same object its spans will be rather than a second one
assembled from the same parameters. Asserting only that the call happened would
pass with it back above, unattributed.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.pipeline import pipeline_run_setup as pipeline_run_setup_module
from pipelex.pipeline.pipeline_run_setup import pipeline_run_setup
from pipelex.system.telemetry.events import EventName

_MINIMAL_MTHDS = """
domain = "prs_telemetry_identity"
description = "Minimal bundle for the pipeline_run_setup telemetry identity test"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = { type = "text", description = "Topic name" }

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to set up a PipeJob"
inputs = { subject = "Text" }
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


async def _run_setup(*, mocker: MockerFixture) -> Any:
    """Run the seam with a stubbed telemetry manager and a tracer present, and return it."""
    telemetry_manager = mocker.MagicMock()
    mocker.patch.object(pipeline_run_setup_module, "get_telemetry_manager", return_value=telemetry_manager)
    # The trace-start is gated on a tracer existing; the test environment has none.
    mocker.patch.object(pipeline_run_setup_module, "get_otel_tracer", return_value=mocker.MagicMock())

    execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False)
    await pipeline_run_setup(
        storage_scope="test/scope",
        user_id="user-42",
        execution_config=execution_config,
        mthds_contents=[_MINIMAL_MTHDS],
        pipe_code="echo_topic",
        inputs={"subject": "a subject"},
        extras={"organization": "org_acme"},
    )
    return telemetry_manager


@pytest.mark.asyncio(loop_scope="class")
class TestPipelineRunSetupTelemetryIdentity:
    async def test_the_trace_start_is_handed_the_runs_metadata(self, mocker: MockerFixture) -> None:
        telemetry_manager = await _run_setup(mocker=mocker)

        telemetry_manager.handle_trace_start.assert_called_once()
        run_metadata = telemetry_manager.handle_trace_start.call_args.kwargs["run_metadata"]
        assert run_metadata.user_id == "user-42"
        assert run_metadata.extras == {"organization": "org_acme"}

    async def test_the_pipeline_execute_event_is_handed_the_runs_metadata(self, mocker: MockerFixture) -> None:
        telemetry_manager = await _run_setup(mocker=mocker)

        execute_calls = [call for call in telemetry_manager.track_event.call_args_list if call.kwargs.get("event_name") == EventName.PIPELINE_EXECUTE]
        assert len(execute_calls) == 1
        run_metadata = execute_calls[0].kwargs["run_metadata"]
        assert run_metadata.user_id == "user-42"
        assert run_metadata.extras == {"organization": "org_acme"}
