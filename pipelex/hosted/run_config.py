"""Where a run executes, and the `[run]` configuration section that sets the default."""

from enum import StrEnum

from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel


class RunExecution(StrEnum):
    """Where a method runs: on this machine with your own inference, or on the hosted Pipelex API."""

    LOCAL = "local"
    HOSTED = "hosted"

    @property
    def is_hosted(self) -> bool:
        match self:
            case RunExecution.LOCAL:
                return False
            case RunExecution.HOSTED:
                return True

    @classmethod
    def from_hosted_flag(cls, *, hosted: bool | None) -> "RunExecution | None":
        """The execution a `--hosted/--local` flag pair requests: `None` when neither was given."""
        if hosted is None:
            return None
        if hosted:
            return RunExecution.HOSTED
        return RunExecution.LOCAL


class RunConfig(ConfigModel):
    """The run commands' defaults.

    ``execution`` is where a run executes when the command names neither ``--hosted`` nor ``--local``:
    ``local`` runs on this machine with the backends in ``.pipelex/inference/``, ``hosted`` runs on the
    hosted Pipelex API with the key in ``PIPELEX_API_KEY``.
    """

    execution: RunExecution = Field(strict=False)
