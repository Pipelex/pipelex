from pydantic import BaseModel
from temporalio import activity

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.delivery_executor import DeliveryExecutor


class DeliveryActivityArg(BaseModel):
    """Input for the act_deliver activity."""

    pipe_output: PipeOutput | None = None
    pipeline_run_id: str
    delivery_assignment: DeliveryAssignment
    status: DeliveryStatus = DeliveryStatus.COMPLETED


@activity.defn(name="act_deliver")
async def act_deliver(arg: DeliveryActivityArg) -> None:
    """Temporal activity that executes the full delivery (storage + webhooks)."""
    executor = DeliveryExecutor()
    await executor.execute(
        pipe_output=arg.pipe_output,
        pipeline_run_id=arg.pipeline_run_id,
        delivery_assignment=arg.delivery_assignment,
        status=arg.status,
    )
