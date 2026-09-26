from abc import abstractmethod
from typing import Protocol

from pipelex.base_exceptions import PipelexError
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.observer.observer_protocol import ObserverProtocol, PayloadKey, PayloadType
from pipelex.pipe_run.exceptions import PipeRouterError, find_failure_location
from pipelex.pipe_run.located_failure import make_unexpected_failure
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
        except Exception as exc:
            # Case (2), unbounded code: a pipe's run reaches user functions, plugin routers and
            # provider SDKs. Nothing is swallowed: every failure is re-raised, located.
            #
            # Direct (non-Temporal) execution is a single pipeline-level attempt — there is no
            # retry here. This handler is error propagation, not retry, and it is the one place a
            # pipe's failure gets its location: whatever the pipe's run raised leaves as a
            # PipeRouterError naming this pipe and its stack, chained to the failure, whose report
            # is the failure's root fault. Resilience is the Temporal track's job.
            await self._after_failing_run(pipe_job, error=exc)
            if find_failure_location(error=exc) is not None:
                # A router below already located it: the innermost location is the one reported.
                raise
            failure = self._as_pipelex_failure(error=exc)
            if failure is None:
                raise
            raise PipeRouterError.make_located(
                failure=failure,
                run_mode=pipe_job.pipe_run_params.run_mode,
                pipe_code=pipe_job.pipe.code,
                output_name=pipe_job.output_name,
                # run_pipe() has already popped the failed pipe's own frame; re-append
                # its code so the reported stack still ends with the pipe that failed.
                pipe_stack=[*pipe_job.pipe_run_params.pipe_stack, pipe_job.pipe.code],
            ) from failure

        await self._after_successful_run(pipe_job, pipe_output=pipe_output)

        return pipe_output

    def _as_pipelex_failure(self, *, error: Exception) -> PipelexError | None:
        """Return the `PipelexError` this router locates for `error`, or `None` to let `error` through untouched.

        A `PipelexError` stands for itself, and that includes one carrying a report recovered
        across a transport boundary, whose report then becomes the located failure's root fault.
        Any other exception is foreign to Pipelex: it is wrapped into a `PipelexUnexpectedError`
        that names its class and is never caller-facing, so it no longer escapes the runner raw.

        A host router overrides this for the exceptions its own transport raises. It converts a
        transport failure that carries a recovered report into a `PipelexError` carrying that
        report, chained to the transport failure, so the pipe is located with the leaf's identity;
        and it returns `None` for a control-flow exception its runtime must see unchanged, such as
        a cancellation.
        """
        if isinstance(error, PipelexError):
            return error
        return make_unexpected_failure(error=error)

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
