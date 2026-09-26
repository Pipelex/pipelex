from typing import Self

from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexError, iter_cause_chain
from pipelex.pipe_run.located_failure import build_located_failure_report, locate_failure_message
from pipelex.system.pipe_run_mode import PipeRunMode


class AsyncExecutionNotEnabledError(PipelexError):
    """Raised when a route that depends on asynchronous execution is hit on a
    deployment that does not have an async execution backend enabled.

    Backend-neutral on purpose, because it is the shared contract between the
    runner API — which maps it to an HTTP status (501) — and any async-execution
    backend plugin that raises it: the Temporal plugin today, other async backends
    (e.g. Mistral Workflows) as support lands. Nothing in this repo raises it. The
    class name, title, and detail therefore talk about *async execution* as a
    capability of the deployment, not about any specific backend brand.

    ``error_domain = CONFIG`` because the caller's request is well-formed; what
    is missing is server-side configuration. The pipelex-api layer maps this
    class to HTTP 501 (Not Implemented), which is more precise than the
    ``CONFIG`` -> 500 default and tells clients the failure is permanent under
    the current deployment rather than a transient runtime fault.
    """

    error_domain = ErrorDomain.CONFIG
    _declared_title = "Async execution not enabled"

    DEFAULT_MESSAGE = (
        "Asynchronous pipeline execution is not enabled on this deployment. "
        "Synchronous execution remains available; to enable async execution, the "
        "server operator must configure an async execution backend in the "
        "deployment's pipelex configuration."
    )

    @classmethod
    def with_default_message(cls) -> "AsyncExecutionNotEnabledError":
        """Construct with the canonical backend-neutral message.

        Raised by an async-execution backend plugin at its dispatch /
        client-acquisition boundary (e.g. the Temporal plugin) to refuse a request
        that needs async execution when no such backend is enabled.
        """
        return cls(cls.DEFAULT_MESSAGE)


class PipeRunParamsError(PipelexError):
    pass


class BatchParamsError(PipelexError):
    pass


class PipeJobError(PipelexError):
    pass


class DeliveryError(PipelexError):
    pass


class WebhookDeliveryError(DeliveryError):
    pass


class StorageDeliveryError(DeliveryError):
    pass


class DryRunError(PipelexError):
    """Raised when a dry run fails due to missing inputs or other validation issues."""


class DryRunGraphNotProducedError(DryRunError):
    """Raised when a graph-producing dry run completes but no ``GraphSpec`` was assembled onto the pipe output.

    The dry-run entrypoints (``dry_run_pipeline`` / ``dry_run_pipe_in_process``) exist to produce a
    graph, so a run that finishes without one is a contract violation on their side — not a
    validation failure of the bundle. Distinct from the bare ``PipelexError`` it replaces so that
    hosts logging only the exception type (e.g. pipelex-api's best-effort ``/validate`` graph step)
    get an unambiguous signal.
    """


class PipeRouterError(PipelexError):
    """A pipe failed while running: the failure, located at the pipe where it happened.

    The pipe router raises it around every failure of the pipe it runs, chained to the failure,
    with the pipe's code and a snapshot of its stack taken where it failed. A failure that already
    carries one keeps it as it rises through the routers of the controllers above, so the innermost
    location is the one reported. Its report is its root fault's, located (see
    `pipelex.pipe_run.located_failure`): a run whose pipe raised `StuffFactoryError` reports
    `StuffFactoryError`, with a message naming the pipe and its path, never `PipeRouterError`.
    """

    def __init__(
        self,
        message: str,
        run_mode: PipeRunMode,
        pipe_code: str,
        output_name: str | None,
        pipe_stack: list[str],
        missing_inputs: list[str] | None = None,
    ):
        self.run_mode = run_mode
        self.pipe_code = pipe_code
        self.output_name = output_name
        self.pipe_stack = list(pipe_stack)  # snapshot: the live stack unwinds after this error is raised
        self.missing_inputs = missing_inputs
        super().__init__(message)

    @classmethod
    def make_located(
        cls,
        *,
        failure: PipelexError,
        run_mode: PipeRunMode,
        pipe_code: str,
        output_name: str | None,
        pipe_stack: list[str],
    ) -> Self:
        """Locate `failure` at `pipe_code`; the caller raises the result `from failure`."""
        return cls(
            message=locate_failure_message(failure=failure, pipe_code=pipe_code, pipe_stack=pipe_stack),
            run_mode=run_mode,
            pipe_code=pipe_code,
            output_name=output_name,
            pipe_stack=pipe_stack,
        )

    @override
    def to_error_report(self) -> ErrorReport:
        return build_located_failure_report(
            wrapper=self,
            own_report=super().to_error_report(),
            pipe_code=self.pipe_code,
            pipe_stack=self.pipe_stack,
        )


def find_failure_location(*, error: BaseException) -> PipeRouterError | None:
    """Return the innermost `PipeRouterError` on `error`'s cause chain, `error` itself included.

    It names the pipe where the failure happened and that pipe's stack snapshot; `None` means the
    failure was never located, because it happened outside any routed pipe run. Like the root-fault
    walk, it stops at the first exception that is not a `PipelexError`: a foreign exception raised
    from an earlier located failure is a new failure, which the router locates where it happened.
    """
    location: PipeRouterError | None = None
    for node in iter_cause_chain(error):
        if not isinstance(node, PipelexError):
            break
        if isinstance(node, PipeRouterError):
            location = node
    return location
