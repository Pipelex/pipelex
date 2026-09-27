from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typing_extensions import override

from pipelex.interpreter_hub import get_pipe_run
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from tests.integration.pipelex.pipeline.test_data import ExecuteRequestIdTestData

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob


class _RecordingPipeRun(PipeRunProtocol):
    """Record the job `execute` hands over, then run it as the process's own `PipeRun` would."""

    def __init__(self) -> None:
        self.pipe_jobs: list[PipeJob] = []

    @override
    async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        self.pipe_jobs.append(pipe_job)
        return await get_pipe_run().run(pipe_job, delivery_assignment=delivery_assignment)


@pytest.mark.asyncio(loop_scope="class")
class TestExecuteRequestId:
    async def test_request_id_rides_the_job_handed_to_the_pipe_run(self) -> None:
        """The host's inbound request id reaches the run metadata a distributed worker binds its log context from."""
        pipe_run = _RecordingPipeRun()
        runner = PipelexMTHDSProtocol(pipe_run=pipe_run)

        await runner.execute(
            pipe_code="restate",
            mthds_contents=[ExecuteRequestIdTestData.COMPOSE_MTHDS],
            inputs={"topic": "cats"},
            request_id=ExecuteRequestIdTestData.REQUEST_ID,
        )

        assert len(pipe_run.pipe_jobs) == 1
        assert pipe_run.pipe_jobs[0].job_metadata.run_metadata.request_id == ExecuteRequestIdTestData.REQUEST_ID

    async def test_omitted_request_id_leaves_none(self) -> None:
        pipe_run = _RecordingPipeRun()
        runner = PipelexMTHDSProtocol(pipe_run=pipe_run)

        await runner.execute(pipe_code="restate", mthds_contents=[ExecuteRequestIdTestData.COMPOSE_MTHDS], inputs={"topic": "cats"})

        assert len(pipe_run.pipe_jobs) == 1
        assert pipe_run.pipe_jobs[0].job_metadata.run_metadata.request_id is None

    @pytest.mark.parametrize("bad_request_id", ["forged\nline", "", "x" * 129])
    async def test_malformed_request_id_is_the_hosts_bug_refused_before_the_run(self, bad_request_id: str) -> None:
        """Refused as a `ValueError`, not relabelled as the caller's invalid input, and no job is set up."""
        pipe_run = _RecordingPipeRun()
        runner = PipelexMTHDSProtocol(pipe_run=pipe_run)

        with pytest.raises(ValueError, match="Invalid request_id") as exc_info:
            await runner.execute(
                pipe_code="restate",
                mthds_contents=[ExecuteRequestIdTestData.COMPOSE_MTHDS],
                inputs={"topic": "cats"},
                request_id=bad_request_id,
            )

        assert type(exc_info.value) is ValueError
        assert pipe_run.pipe_jobs == []
