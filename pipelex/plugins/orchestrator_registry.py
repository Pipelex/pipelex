from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pipelex.runtime_bridge.orchestration_mode import OrchestrationMode

if TYPE_CHECKING:
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunOutput


@runtime_checkable
class OrchestratorProtocol(Protocol):
    """How a pipe job runs under one orchestration mode.

    An orchestrator plugin registers one of these per ``orchestration_mode`` token it
    serves (``"direct"`` in core; ``"temporal"`` from our Temporal plugin,
    ``"mistral-workflows"`` from our Mistral Workflows plugin). The runtime bridge
    dispatches by token through the ``OrchestratorRegistry`` instead of branching on a
    ``match``.

    The wait-semantics axis (``DeliveryMode`` on the wire input) is expressed here as
    which method the endpoint calls, so each return type is truthful on its own:

    - ``execute`` is the BLOCKING arm — it awaits completion and returns the completed-run
      ``PipelexPipeRunOutput`` (which therefore always carries a main stuff).
    - ``start`` is the FIRE_AND_FORGET arm — it genuinely enqueues the job and returns
      a ``PipelexPipeDispatchAck`` (ids only; nothing has run yet).

    ``supports_fire_and_forget`` is the capability the runner reads *before* dispatch:
    ``/start`` rejects (honestly, with a 4xx) when the resolved mode's orchestrator
    cannot do genuine async, rather than silently running blocking and acking. An
    orchestrator with ``supports_fire_and_forget = False`` implements ``start`` by
    raising — the gate keeps it unreachable.

    The method files a job reads travel by reference: its ``library_crate`` names each method
    tree by its digest and carries none of its files, which this process's libraries hold for
    the request (``LOCAL_METHOD_FILES``), served from the bytes a request submitted or from the
    directory a tree was listed from, which may be a temporary directory the runner deletes. An
    orchestrator that runs the job out of process, on a worker reading another store, copies
    every tree the job's crate names into that store before its ``execute`` or ``start``
    returns, since the runner may drop the library and the files as soon as it does:
    ``read_stored_trees(tree_digests=pipe_job.library_crate.tree_digests(), read_scope=...)``
    (``pipelex.core.method_trees.method_files``) reads each one as a store keeps it, its listing
    under the tree's digest and its files under their hashes, checked. An orchestrator running
    the job in this process, to its end before its ``execute`` returns, copies nothing; one that
    keeps a job running after its ``start`` returned copies the trees as an out-of-process one
    does, wherever the job runs, since the library holding them is gone by then.
    """

    supports_fire_and_forget: bool

    async def execute(
        self,
        *,
        pipe_job: "PipeJob",
        delivery_assignment: "DeliveryAssignment | None",
    ) -> "PipelexPipeRunOutput": ...

    async def start(
        self,
        *,
        pipe_job: "PipeJob",
        delivery_assignment: "DeliveryAssignment | None",
    ) -> "PipelexPipeDispatchAck": ...


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
