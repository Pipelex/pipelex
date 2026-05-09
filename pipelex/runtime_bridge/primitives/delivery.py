"""Framework-agnostic delivery execution (storage + webhook).

Wraps ``DeliveryExecutor.execute`` so host-runtime activities (Temporal /
Mistral) can keep their decorators thin while sharing the same body.
"""

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus
from pipelex.pipe_run.delivery_executor import DeliveryExecutor


async def execute_delivery(
    pipe_output: PipeOutput | None,
    user_id: str,
    pipeline_run_id: str,
    delivery_assignment: DeliveryAssignment,
    status: DeliveryStatus = DeliveryStatus.COMPLETED,
) -> None:
    """Execute the full delivery (storage + webhooks)."""
    executor = DeliveryExecutor()
    await executor.execute(
        pipe_output=pipe_output,
        user_id=user_id,
        pipeline_run_id=pipeline_run_id,
        delivery_assignment=delivery_assignment,
        status=status,
    )
