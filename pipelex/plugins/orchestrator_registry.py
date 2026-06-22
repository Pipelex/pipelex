from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pipelex.runtime_bridge.delivery_mode import DeliveryMode
from pipelex.runtime_bridge.orchestration_mode import OrchestrationMode

if TYPE_CHECKING:
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.runtime_bridge.payloads import PipelexPipeRunOutput


@runtime_checkable
class OrchestratorProtocol(Protocol):
    """How a pipe job runs under one orchestration mode.

    An orchestrator plugin registers one of these per ``orchestration_mode`` token it
    serves (``"direct"`` in core; ``"temporal"`` from ``pipelex-temporal``,
    ``"mistralai-workflows"`` from ``pipelex-mistralai-workflows``). The runtime bridge
    dispatches by token through the ``OrchestratorRegistry`` instead of branching on a
    ``match``.

    ``run`` takes the endpoint-chosen ``delivery`` (the wait-semantics axis) and honors
    it per the orchestrator's nature: an in-process orchestrator always blocks; a
    distributed one awaits completion for ``BLOCKING`` and returns a workflow id for
    ``FIRE_AND_FORGET``.

    ``supports_fire_and_forget`` is the capability the runner reads *before* dispatch:
    ``/start`` rejects (honestly, with a 4xx) when the resolved mode's orchestrator
    cannot do genuine async, rather than silently running blocking and acking.
    """

    supports_fire_and_forget: bool

    async def run(
        self,
        *,
        pipe_job: "PipeJob",
        delivery_assignment: "DeliveryAssignment | None",
        delivery: DeliveryMode,
    ) -> "PipelexPipeRunOutput": ...


class OrchestratorRegistry:
    """Read view over the orchestrators contributed by discovered plugins.

    Keyed by the open ``OrchestrationMode`` token (a ``str``). Built once at boot from
    the registrar's accumulated orchestrators and stored on the hub.
    """

    def __init__(self, orchestrators: dict[OrchestrationMode, OrchestratorProtocol]):
        self._orchestrators: dict[OrchestrationMode, OrchestratorProtocol] = dict(orchestrators)

    def get_optional(self, *, mode: OrchestrationMode) -> OrchestratorProtocol | None:
        return self._orchestrators.get(mode)

    def has(self, *, mode: OrchestrationMode) -> bool:
        return mode in self._orchestrators

    @property
    def modes(self) -> list[OrchestrationMode]:
        return list(self._orchestrators)
