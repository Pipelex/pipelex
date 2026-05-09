"""Temporal activity wrapper for delivery (storage + webhook).

Thin ``@activity.defn`` wrapper around the framework-agnostic core in
``pipelex.runtime_bridge.primitives.delivery``.
"""

from pydantic import BaseModel
from temporalio import activity

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.runtime_bridge.primitives.delivery import execute_delivery


class DeliveryActivityArg(BaseModel):
    """Input for the act_deliver activity."""

    pipe_output: PipeOutput | None = None
    user_id: str
    pipeline_run_id: str
    delivery_assignment: DeliveryAssignment
    status: DeliveryStatus = DeliveryStatus.COMPLETED


@activity.defn(name="act_deliver")
async def act_deliver(arg: DeliveryActivityArg) -> None:
    await execute_delivery(
        pipe_output=arg.pipe_output,
        user_id=arg.user_id,
        pipeline_run_id=arg.pipeline_run_id,
        delivery_assignment=arg.delivery_assignment,
        status=arg.status,
    )
