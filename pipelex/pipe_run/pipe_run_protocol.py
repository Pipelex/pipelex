from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob


class PipeRunProtocol(Protocol):
    """Protocol for executing a pipe job and delivering the output.

    Wraps pipe execution (via PipeRouter) with delivery of the output
    to storage providers, webhooks, or other targets.
    """

    @abstractmethod
    async def run(
        self,
        pipe_job: PipeJob,
        *,
        delivery_assignment: DeliveryAssignment | None = None,
    ) -> PipeOutput:
        """Execute a pipe job and, if `delivery_assignment` is provided, deliver the output.

        When `delivery_assignment` is None, no storage or webhook delivery happens.
        Pass `DeliveryAssignment(storage=StorageTarget())` for default storage-only delivery.
        """
        ...
