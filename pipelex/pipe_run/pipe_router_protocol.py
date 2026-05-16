import asyncio
from abc import abstractmethod
from typing import Protocol

from pipelex import log
from pipelex.cogt.exceptions import CogtError
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.observer.observer_protocol import ObserverProtocol, PayloadKey, PayloadType
from pipelex.pipe_run.exceptions import PipeRouterError, PipeRunError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.transient_retry import TransientRetrySettings


def _find_cogt_error_in_chain(exc: BaseException) -> CogtError | None:
    """Return the first CogtError found by walking the exception's ``__cause__`` chain.

    Operators wrap the worker's CogtError into a PipeRunError (and a nested pipe may add
    further layers); the transient-retry decision needs the underlying CogtError's category
    regardless of how many wrapper layers sit in between.
    """
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, CogtError):
            return current
        current = current.__cause__
    return None


class PipeRouterProtocol(Protocol):
    observer: ObserverProtocol
    # Resolved from `PipelineExecutionConfig` by each concrete router at construction time — the protocol
    # itself cannot read config without forming an import cycle (see `transient_retry.py`).
    transient_retry_settings: TransientRetrySettings

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

        retry_settings = self.transient_retry_settings
        retry_count = 0
        while True:
            try:
                pipe_output = await self._run_pipe_job(pipe_job)
                break
            except (CogtError, PipeRunError) as exc:
                # The transient-retry decision is driven by the underlying inference error's
                # category. The LLM operators (PipeLLM, PipeStructure) wrap the worker's
                # CogtError into a PipeRunError before it reaches here, so the retryable
                # CogtError is located by walking the full `__cause__` chain to any depth.
                cogt_error = _find_cogt_error_in_chain(exc)
                error_category = cogt_error.error_category if cogt_error is not None else None
                is_retryable = error_category is not None and error_category.is_retryable
                if is_retryable and retry_count < retry_settings.max_transient_retries:
                    retry_count += 1
                    wait_seconds = retry_settings.compute_wait(retry_count)
                    log.warning(
                        f"Transient inference error ({error_category}) running pipe '{pipe_job.pipe.code}' — "
                        f"retry {retry_count}/{retry_settings.max_transient_retries} in {wait_seconds:.2f}s: {exc}"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue
                # Non-retryable category, or the transient-retry budget is exhausted. A PipeRunError
                # still wraps into PipeRouterError (preserving the pipe location context); a raw
                # CogtError is re-raised as-is so its cause chain is preserved.
                await self._after_failing_run(pipe_job, exc)
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

        await self._after_successful_run(pipe_job, pipe_output)

        return pipe_output

    @abstractmethod
    async def _run_pipe_job(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput: ...
