from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode

if TYPE_CHECKING:
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.runtime_bridge.payloads import PipelexPipeRunOutput


@runtime_checkable
class OrchestratorProtocol(Protocol):
    """How a pipe job runs under one execution mode.

    An orchestrator plugin registers one of these per ``PipelexExecutionMode`` it
    serves (DIRECT in core; TEMPORAL_* / MISTRAL_NATIVE from their own plugins).
    The runtime bridge dispatches by mode through the ``OrchestratorRegistry``
    instead of branching on a ``match`` (wired in Phase 3).
    """

    async def run(self, *, pipe_job: "PipeJob", delivery_assignment: "DeliveryAssignment | None") -> "PipelexPipeRunOutput": ...


class OrchestratorRegistry:
    """Read view over the orchestrators contributed by discovered plugins.

    Keyed by ``PipelexExecutionMode``. Built once at boot from the registrar's
    accumulated orchestrators and stored on the hub.
    """

    def __init__(self, orchestrators: dict[PipelexExecutionMode, OrchestratorProtocol]):
        self._orchestrators: dict[PipelexExecutionMode, OrchestratorProtocol] = dict(orchestrators)

    def get_optional(self, *, mode: PipelexExecutionMode) -> OrchestratorProtocol | None:
        return self._orchestrators.get(mode)

    def has(self, *, mode: PipelexExecutionMode) -> bool:
        return mode in self._orchestrators

    @property
    def modes(self) -> list[PipelexExecutionMode]:
        return list(self._orchestrators)
