from abc import abstractmethod
from typing import Protocol

from pipelex.base_exceptions import PipelexError
from pipelex.core.pipes.declared_item_count_scope import scoped_dry_run_mock_budget
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.errors.unexpected_failure import make_unexpected_failure
from pipelex.observer.observer_protocol import ObserverProtocol, PayloadKey, PayloadType
from pipelex.pipe_run.exceptions import PipeRouterError, find_failure_location
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
            # The run spends the budget of mock items its setup opened for the mock inputs, carried on its job, unless a
            # scope around it already counts, such as a validation's: a run's setup and its pipes build within one budget.
            with scoped_dry_run_mock_budget(tally=pipe_job.dry_run_mock_tally):
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
            if find_failure_location(error=failure) is not None:
                # The host rebuilt the location its transport carried: it is not located again, and the
                # chain it built down to the recovered report is kept (a `from exc` would cut it off).
                raise failure from failure.__cause__
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

        A `PipelexError` stands for itself, and that includes one carrying a problem recovered
        across a transport boundary, whose problem then becomes the located failure's root fault.
        Any other exception is foreign to Pipelex: it is wrapped into a `PipelexUnexpectedError`
        that names its class, whose message only an operator reads, so it no longer escapes the runner raw.

        A host router overrides this for the exceptions its own transport raises, and returns `None`
        for a control-flow exception its runtime must see unchanged, such as a cancellation. A
        transport failure carrying a recovered problem is converted according to what the far side
        packed, which must never be a problem that is already located, since this router would
        locate it again:

        - the root fault's own problem alone (`find_root_fault(...).to_problem(view=ProblemView.OPERATOR)`): return a
          `PipelexError` carrying it, and this router locates it at the pipe it ran;
        - that problem together with the location the far side found (`find_failure_location(...)`,
          its `pipe_code` and `pipe_stack`): return `PipeRouterError.make_located(...)` over a
          `PipelexError` carrying the problem, chained to it. It already names its pipe, so this
          router raises it untouched, and the problem reads exactly as the local run's.

        A `PipelexError` carrying a recovered problem overrides `recovered_problem()` to return it, and its `to_problem`
        reports it projected to the view asked for (`pipelex.errors.problem.recovered_problem_in_view`), with the
        location it is given.
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

    def check_batch_fits(
        self,
        *,
        pipe_code: str,
        input_list_label: str,
        item_count: int,
        first_branch_job: PipeJob,
    ) -> None:
        """Let the router refuse a ``PipeBatch`` it cannot run, before any of its branches starts.

        ``PipeBatch`` calls it once per batch, when it knows how many items its list holds and before it records its
        fan-out or starts a branch, and never for an empty list. A durable router, whose run keeps a history its engine
        bounds, may estimate there what the whole batch would write into that history from ``first_branch_job`` and
        ``item_count``, and refuse by raising
        :class:`~pipelex.pipe_controllers.exceptions.PipeBatchTooWideError`, so that a batch which cannot finish is
        refused before its first item is billed rather than ended halfway by its engine. The refusal fails the
        ``PipeBatch`` itself, located at it as any failure of its run is.

        The default body IS the behavior for in-process routers, which keep no such history: every batch fits, so
        they answer yes without looking. It is called in a dry run too, whose job's ``pipe_run_params.run_mode`` says
        so, for a router that would check only live runs.

        Args:
            pipe_code: The code of the ``PipeBatch``.
            input_list_label: The list the batch runs over, named as its author wrote it (``BatchParams.input_list_label``),
                never by the private name a sequence may bind a dotted ``batch_over`` under.
            item_count: How many items the list holds, at least one.
            first_branch_job: The very job the batch's first branch will dispatch through :meth:`run_batch_branch`.
                It is the job that runs, not a copy, so the router reads it and never changes it.
        """
        # Every batch fits an in-process router, which reads none of what it is given; the body is not empty, so the type
        # checkers read a default that does nothing rather than an abstract method.
        del pipe_code, input_list_label, item_count, first_branch_job

    @abstractmethod
    async def _run_pipe_job(
        self,
        pipe_job: PipeJob,
    ) -> PipeOutput: ...
