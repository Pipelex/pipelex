from pydantic import BaseModel
from temporalio import activity

from pipelex.base_exceptions import ErrorReport
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.temporal.tprl.activity_error_boundary import convert_pipelex_errors


class DeliveryActivityArg(BaseModel):
    """Input for the act_deliver activity; ``error_report`` carries the worker-side classification on failure."""

    pipe_output: PipeOutput | None = None
    user_id: str
    pipeline_run_id: str
    delivery_assignment: DeliveryAssignment
    status: DeliveryStatus = DeliveryStatus.COMPLETED
    error_report: ErrorReport | None = None


@activity.defn(name="act_deliver")
@convert_pipelex_errors
async def act_deliver(arg: DeliveryActivityArg) -> None:
    """Temporal activity that executes the full delivery (storage + webhooks)."""
    executor = DeliveryExecutor()
    await executor.execute(
        pipe_output=arg.pipe_output,
        user_id=arg.user_id,
        pipeline_run_id=arg.pipeline_run_id,
        delivery_assignment=arg.delivery_assignment,
        status=arg.status,
        error_report=arg.error_report,
    )
