"""The observer's per-pipe events name the run they came from.

`pipe_run` and `pipe_complete` are the runtime's per-pipe drill-down beside the
platform's one-number-per-run `run_started`, so they have to land on the same
person and the same groups as the run's spans. The observer holds the whole
`PipeJob`, so the forward is the one thing that can be missing — and a missing
forward is silent: the event still fires, just under the process identity.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.observer.observer_protocol import PayloadKey
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.telemetry.events import EventName
from pipelex.system.telemetry.observer_telemetry import ObserverTelemetry

_RUN_METADATA = RunMetadata(
    user_id="user-42",
    pipeline_run_id="run-1",
    storage_scope="tenant/run-1",
    analytics_groups={"organization": "org_acme"},
)


def _payload(*, mocker: MockerFixture) -> dict[str, Any]:
    pipe_job = mocker.MagicMock(name="pipe_job")
    pipe_job.pipe_type = "PipeLLM"
    pipe_job.job_metadata = JobMetadata(run_metadata=_RUN_METADATA)
    return {PayloadKey.PIPELINE_RUN_ID: "run-1", PayloadKey.PIPE_JOB: pipe_job}


@pytest.mark.asyncio
class TestObserverTelemetryIdentity:
    async def test_pipe_run_names_the_run(self, mocker: MockerFixture) -> None:
        telemetry_manager = mocker.MagicMock()
        observer = ObserverTelemetry(telemetry_manager=telemetry_manager)

        await observer.observe_before_run(_payload(mocker=mocker))

        call = telemetry_manager.track_event.call_args
        assert call.kwargs["event_name"] == EventName.PIPE_RUN
        assert call.kwargs["run_metadata"] is _RUN_METADATA

    async def test_a_successful_pipe_complete_names_the_run(self, mocker: MockerFixture) -> None:
        telemetry_manager = mocker.MagicMock()
        observer = ObserverTelemetry(telemetry_manager=telemetry_manager)

        await observer.observe_after_successful_run(_payload(mocker=mocker))

        assert telemetry_manager.track_event.call_args.kwargs["run_metadata"] is _RUN_METADATA

    async def test_a_failing_pipe_complete_names_the_run(self, mocker: MockerFixture) -> None:
        telemetry_manager = mocker.MagicMock()
        observer = ObserverTelemetry(telemetry_manager=telemetry_manager)

        await observer.observe_after_failing_run(_payload(mocker=mocker))

        assert telemetry_manager.track_event.call_args.kwargs["run_metadata"] is _RUN_METADATA
