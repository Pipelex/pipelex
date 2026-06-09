from pydantic import BaseModel

from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
from pipelex.pipe_run.pipe_job import PipeJob


class PipeRunArg(BaseModel):
    """Workflow input for WfPipeRun: bundles PipeJob + delivery assignment for Temporal serialization."""

    pipe_job: PipeJob
    delivery_assignment: DeliveryAssignment | None = None

    def prepare_for_temporal(self) -> "PipeRunArg":
        return self.model_copy(update={"pipe_job": self.pipe_job.prepare_for_temporal()})
