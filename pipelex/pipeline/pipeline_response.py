from __future__ import annotations

from mthds.client.pipeline import MAIN_STUFF_NAME, PipelineExecuteResponse, PipelineStartResponse, PipelineState

from pipelex.core.pipes.pipe_output import PipeOutput


class PipelexPipelineExecuteResponse(PipelineExecuteResponse[PipeOutput]):
    @classmethod
    def from_pipe_output(
        cls,
        pipe_output: PipeOutput,
        pipeline_run_id: str = "",
        created_at: str = "",
        pipeline_state: PipelineState = PipelineState.COMPLETED,
        finished_at: str | None = None,
    ) -> PipelexPipelineExecuteResponse:
        return cls(
            pipeline_run_id=pipeline_run_id,
            created_at=created_at,
            pipeline_state=pipeline_state,
            finished_at=finished_at,
            pipe_output=pipe_output,
            main_stuff_name=pipe_output.working_memory.aliases.get(MAIN_STUFF_NAME, MAIN_STUFF_NAME),
        )


class PipelexPipelineStartResponse(PipelineStartResponse[PipeOutput]):
    pass
