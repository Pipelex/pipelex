"""Temporal activity wrapper for delivery (storage + webhook).

Thin ``@activity.defn`` wrapper around the framework-agnostic core in
``pipelex.runtime_bridge.primitives.delivery``.
"""

from pydantic import BaseModel
from temporalio import activity

from pipelex.base_exceptions import ErrorReport
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.runtime_bridge.primitives.delivery import execute_delivery
from pipelex.temporal.tprl.activity_error_boundary import convert_pipelex_errors


class DeliveryActivityArg(BaseModel):
    """Input for the act_deliver activity; ``error_report`` carries the worker-side classification on failure.

    ``request_id`` carries the originating ``JobMetadata.request_id`` so the delivery
    phase's logs (storage / webhook) can be correlated with the workflow logs and the
    inbound API request that started the run.
    """

    pipe_output: PipeOutput | None = None
    user_id: str
    pipeline_run_id: str
    delivery_assignment: DeliveryAssignment
    status: DeliveryStatus = DeliveryStatus.COMPLETED
    error_report: ErrorReport | None = None
    request_id: str | None = None


@activity.defn(name="act_deliver")
@convert_pipelex_errors
async def act_deliver(arg: DeliveryActivityArg) -> None:
    await execute_delivery(
        pipe_output=arg.pipe_output,
        user_id=arg.user_id,
        pipeline_run_id=arg.pipeline_run_id,
        delivery_assignment=arg.delivery_assignment,
        status=arg.status,
        error_report=arg.error_report,
        request_id=arg.request_id,
    )
