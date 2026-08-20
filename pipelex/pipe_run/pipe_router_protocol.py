from abc import abstractmethod
from typing import Protocol

from pipelex.cogt.exceptions import CogtError
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.observer.observer_protocol import ObserverProtocol, PayloadKey, PayloadType
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_job import PipeJob


class PipeRouterProtocol(Protocol):
    observer: ObserverProtocol

    async def _before_run(
        self,
        pipe_job: PipeJob,
    ) -> None:
        payload: PayloadType = {
            PayloadKey.PIPELINE_RUN_ID: pipe_job.job_metadata.run_metadata.pipeline_run_id,
            PayloadKey.PIPE_JOB: pipe_job,
        }
        await self.observer.observe_before_run(payload)

    async def _after_successful_run(
        self,
        pipe_job: PipeJob,
        *,
        pipe_output: PipeOutput,
    ) -> None:
        payload: PayloadType = {
            PayloadKey.PIPELINE_RUN_ID: pipe_job.job_metadata.run_metadata.pipeline_run_id,
            PayloadKey.PIPE_JOB: pipe_job,
            PayloadKey.PIPE_OUTPUT: pipe_output,
        }
        await self.observer.observe_after_successful_run(payload)

    async def _after_failing_run(
        self,
        pipe_job: PipeJob,
        *,
        error: Exception,
    ) -> None:
        payload: PayloadType = {
            PayloadKey.PIPELINE_RUN_ID: pipe_job.job_metadata.run_metadata.pipeline_run_id,
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
        except (CogtError, PipeRunError) as exc:
            # Direct (non-Temporal) execution is a single pipeline-level attempt — there is no
            # retry here. This handler is error propagation, not retry: a PipeRunError wraps into
            # PipeRouterError (preserving the pipe location context); a raw CogtError is re-raised
            # as-is so its cause chain is preserved. Resilience is the Temporal track's job.
            await self._after_failing_run(pipe_job, error=exc)
            if isinstance(exc, PipeRunError):
                raise PipeRouterError(
                    message=exc.message,
                    run_mode=pipe_job.pipe_run_params.run_mode,
                    pipe_code=pipe_job.pipe.code,
                    output_name=pipe_job.output_name,
                    # run_pipe() has already popped the failed pipe's own frame; re-append
                    # its code so the reported stack still ends with the pipe that failed.
                    pipe_stack=[*pipe_job.pipe_run_params.pipe_stack, pipe_job.pipe.code],
                ) from exc
            raise

        await self._after_successful_run(pipe_job, pipe_output=pipe_output)

        return pipe_output

    async def run_batch_branch(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput:
        """Run ``pipe_job`` as one fan-out branch of a ``PipeBatch``.

        This is the ONE dispatch site in the pipe tree that carries "this dispatch is a
        per-item fan-out branch" as semantics rather than as a data shape: the branch job
        carries the branch pipe and the per-item memory, which is indistinguishable from any
        other dispatch. A distributed router MAY use that signal to isolate the branch (own
        retry, own history partition); every other dispatch it receives runs inline.

        The default body IS the behavior for in-process routers: a branch is just a run.
        Implementations only override this when isolation is something they can offer.
        """
        return await self.run(pipe_job)

    @abstractmethod
    async def _run_pipe_job(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput: ...
