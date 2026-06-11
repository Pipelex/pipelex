from __future__ import annotations

from mthds.protocol.models import RunResultExecute, RunResultStart

from pipelex.core.memory.working_memory import MAIN_STUFF_NAME
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.types import StrEnum


class RunState(StrEnum):
    """Run lifecycle state — a pipelex extension field on run responses (the protocol defines none)."""

    STARTED = "STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class PipelexRunResultExecute(RunResultExecute[PipeOutput]):
    """Pipelex's `/execute` response — the completed run.

    The protocol's `RunResultExecute` carries `pipeline_run_id` + `pipe_output`
    (both always present); `state`, `created_at`, `finished_at`, and
    `main_stuff_name` are pipelex extension fields, documented by this
    implementation's own API schema.
    """

    created_at: str
    state: RunState
    finished_at: str | None = None
    main_stuff_name: str | None = None

    @classmethod
    def from_pipe_output(
        cls,
        pipe_output: PipeOutput,
        pipeline_run_id: str = "",
        created_at: str = "",
        state: RunState = RunState.COMPLETED,
        finished_at: str | None = None,
    ) -> PipelexRunResultExecute:
        return cls(
            pipeline_run_id=pipeline_run_id,
            created_at=created_at,
            state=state,
            finished_at=finished_at,
            pipe_output=pipe_output,
            main_stuff_name=pipe_output.working_memory.aliases.get(MAIN_STUFF_NAME, MAIN_STUFF_NAME),
        )


class PipelexRunResultStart(RunResultStart):
    """Pipelex's `/start` response — just the authoritative `pipeline_run_id`.

    The protocol's `RunResultStart` carries `pipeline_run_id` only; `state`,
    `created_at`, `finished_at`, and `workflow_id` are pipelex extension fields.
    """

    created_at: str
    state: RunState
    finished_at: str | None = None
    workflow_id: str | None = None
