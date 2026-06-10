from __future__ import annotations

from mthds.client.pipeline import MAIN_STUFF_NAME, RunResult, RunState, StartAck

from pipelex.core.pipes.pipe_output import PipeOutput


class PipelexRunResult(RunResult[PipeOutput]):
    @classmethod
    def from_pipe_output(
        cls,
        pipe_output: PipeOutput,
        pipeline_run_id: str = "",
        created_at: str = "",
        state: RunState = RunState.COMPLETED,
        finished_at: str | None = None,
    ) -> PipelexRunResult:
        return cls(
            pipeline_run_id=pipeline_run_id,
            created_at=created_at,
            state=state,
            finished_at=finished_at,
            pipe_output=pipe_output,
            main_stuff_name=pipe_output.working_memory.aliases.get(MAIN_STUFF_NAME, MAIN_STUFF_NAME),
        )


class PipelexStartAck(StartAck[PipeOutput]):
    workflow_id: str | None = None
