from typing import Protocol

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.exceptions import DryRunMissingInputsError, PipeRouterError, PipeRunError
from pipelex.observer.observer_protocol import ObserverProtocol, PayloadKey, PayloadType
from pipelex.pipe_run.pipe_job import PipeJob


class PipeRouterProtocol(Protocol):
    observer: ObserverProtocol

    async def _before_run(
        self,
        pipe_job: PipeJob,
    ) -> None:
        payload: PayloadType = {
            PayloadKey.PIPELINE_RUN_ID: pipe_job.job_metadata.pipeline_run_id,
            PayloadKey.PIPE_JOB: pipe_job,
        }
        await self.observer.observe_before_run(payload)

    async def _after_successful_run(
        self,
        pipe_job: PipeJob,
        pipe_output: PipeOutput,
    ) -> None:
        payload: PayloadType = {
            PayloadKey.PIPELINE_RUN_ID: pipe_job.job_metadata.pipeline_run_id,
            PayloadKey.PIPE_JOB: pipe_job,
            PayloadKey.PIPE_OUTPUT: pipe_output,
        }
        await self.observer.observe_after_successful_run(payload)

    async def _after_failing_run(
        self,
        pipe_job: PipeJob,
        error: Exception,
    ) -> None:
        payload: PayloadType = {
            PayloadKey.PIPELINE_RUN_ID: pipe_job.job_metadata.pipeline_run_id,
            PayloadKey.PIPE_JOB: pipe_job,
            PayloadKey.ERROR: error,
        }
        await self.observer.observe_after_failing_run(payload)

    async def run(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput:
        await self._before_run(pipe_job)

        try:
            pipe_output = await self._run_pipe_job(pipe_job)
        except DryRunMissingInputsError as exc:
            await self._after_failing_run(pipe_job, exc)
            raise PipeRouterError(
                message=exc.message,
                run_mode=pipe_job.pipe_run_params.run_mode,
                pipe_code=pipe_job.pipe.code,
                output_name=pipe_job.output_name,
                pipe_stack=pipe_job.pipe_run_params.pipe_stack,
                missing_inputs=exc.missing_inputs,
            ) from exc
        except PipeRunError as exc:
            await self._after_failing_run(pipe_job, exc)
            raise PipeRouterError(
                message=exc.message,
                run_mode=pipe_job.pipe_run_params.run_mode,
                pipe_code=pipe_job.pipe.code,
                output_name=pipe_job.output_name,
                pipe_stack=pipe_job.pipe_run_params.pipe_stack,
            ) from exc

        await self._after_successful_run(pipe_job, pipe_output)

        return pipe_output

    async def _run_pipe_job(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput: ...
