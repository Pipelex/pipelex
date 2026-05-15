from typing_extensions import override

from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.observer.observer_protocol import ObserverNoOp, ObserverProtocol
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipe_run.transient_retry import TransientRetrySettings


def make_transient_retry_settings() -> TransientRetrySettings:
    """Build the transient-retry policy from the current `PipelineExecutionConfig`.

    Concrete routers call this at construction time: `PipeRouterProtocol` cannot read config itself
    without forming an import cycle (see `transient_retry.py`).
    """
    execution_config = get_config().pipelex.pipeline_execution_config
    return TransientRetrySettings(
        max_transient_retries=execution_config.max_transient_retries,
        base_wait=execution_config.transient_retry_base_wait,
        max_wait=execution_config.transient_retry_max_wait,
        backoff_multiplier=execution_config.transient_retry_backoff_multiplier,
    )


class PipeRouter(PipeRouterProtocol):
    def __init__(self, observer: ObserverProtocol | None = None):
        self.observer = observer or ObserverNoOp()
        self.transient_retry_settings = make_transient_retry_settings()

    @override
    async def _run_pipe_job(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput:
        return await pipe_job.pipe.run_pipe(
            job_metadata=pipe_job.job_metadata,
            working_memory=pipe_job.get_working_memory(),
            output_name=pipe_job.output_name,
            pipe_run_params=pipe_job.pipe_run_params,
            library_crate=pipe_job.library_crate,
        )
