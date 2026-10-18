from __future__ import annotations

from enum import StrEnum

from mthds.protocol.models import RunResultExecute, RunResultStart
from pydantic import Field

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.runtime_bridge.serialization import resolve_main_stuff_root_key


class RunState(StrEnum):
    """Run lifecycle state — a pipelex extension field on run responses (the protocol defines none)."""

    STARTED = "STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


CRATE_FINGERPRINT_DESCRIPTION = (
    "PIPELEX EXTENSION (not part of the MTHDS Protocol) — the fingerprint of the library crate the run's method was "
    "loaded into, the identity of its concepts and pipes, which changes with their meaning and not with their "
    "formatting or comments. Null when the run was built from no crate."
)


class PipelexRunResultExecute(RunResultExecute[PipeOutput]):
    """Pipelex's `/execute` response — the completed run.

    The protocol's `RunResultExecute` carries `pipeline_run_id` + `pipe_output`
    (both always present); `state`, `created_at`, `finished_at`,
    `main_stuff_name` and `crate_fingerprint` are pipelex extension fields,
    documented by this implementation's own API schema.
    """

    created_at: str
    state: RunState
    finished_at: str | None = None
    # A completed run always resolves its declared output: a value or a recorded absence. This names
    # the working-memory root key the value lives under — or, when the output resolved absent, the
    # declared slot the absence record is keyed by (consumers branch on the record).
    main_stuff_name: str
    crate_fingerprint: str | None = Field(default=None, description=CRATE_FINGERPRINT_DESCRIPTION)

    @classmethod
    def from_pipe_output(
        cls,
        pipe_output: PipeOutput,
        *,
        pipeline_run_id: str = "",
        created_at: str = "",
        state: RunState = RunState.COMPLETED,
        finished_at: str | None = None,
        crate_fingerprint: str | None = None,
    ) -> PipelexRunResultExecute:
        return cls(
            pipeline_run_id=pipeline_run_id,
            created_at=created_at,
            state=state,
            finished_at=finished_at,
            pipe_output=pipe_output,
            main_stuff_name=resolve_main_stuff_root_key(pipe_output=pipe_output),
            crate_fingerprint=crate_fingerprint,
        )


class PipelexRunResultStart(RunResultStart):
    """Pipelex's `/start` response — just the authoritative `pipeline_run_id`.

    The protocol's `RunResultStart` carries `pipeline_run_id` only; `state`,
    `created_at`, `finished_at`, `workflow_id` and `crate_fingerprint` are
    pipelex extension fields.
    """

    created_at: str
    state: RunState
    finished_at: str | None = None
    workflow_id: str | None = None
    crate_fingerprint: str | None = Field(default=None, description=CRATE_FINGERPRINT_DESCRIPTION)
