from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.core.exceptions import DryRunFailureErrorData
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
    """Raised when a dry run fails. The validation sweep raises it with one failure per pipe whose dry run
    failed, located at the innermost failing pipe that is not allowed to fail, so a controller that failed
    because a pipe it runs failed is reported once, at that pipe. Bundle validation reports each failure as its own ``dry_run``
    item, with the error type ``DryRunError``, the pipe's code, domain and source, and a message that
    keeps the failure's own text only when that text is caller-facing and otherwise names the failure's
    title.

    Raised elsewhere it may carry no failures, and validation then reports it as one item.
    """

    def __init__(self, message: str, *, failures: list[DryRunFailureErrorData] | None = None):
        self.failures = failures or []
        super().__init__(message)


class DryRunGraphNotProducedError(DryRunError):
    """Raised when a graph-producing dry run completes but no ``GraphSpec`` was assembled onto the pipe output.

    The dry-run entrypoints (``dry_run_pipeline`` / ``dry_run_pipe_in_process``) exist to produce a
    graph, so a run that finishes without one is a contract violation on their side — not a
    validation failure of the bundle. Distinct from the bare ``PipelexError`` it replaces so that
    hosts logging only the exception type (e.g. pipelex-api's best-effort ``/validate`` graph step)
    get an unambiguous signal.
    """


class PipeRouterError(PipelexError):
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
