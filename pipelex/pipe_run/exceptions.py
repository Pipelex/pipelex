from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode


class AsyncExecutionNotEnabledError(PipelexError):
    """Raised when a route that depends on asynchronous execution is hit on a
    deployment that does not have an async execution backend enabled.

    Backend-neutral on purpose: the same condition can be produced today by a
    Temporal-backed runner finding ``[temporal] is_enabled = false`` and will be
    produced by other async backends (e.g. Mistral Workflows) as support lands.
    The class name, title, and detail therefore talk about *async execution* as
    a capability of the deployment, not about any specific backend brand.

    ``error_domain = CONFIG`` because the caller's request is well-formed; what
    is missing is server-side configuration. The pipelex-api layer maps this
    class to HTTP 501 (Not Implemented), which is more precise than the
    ``CONFIG`` -> 500 default and tells clients the failure is permanent under
    the current deployment rather than a transient runtime fault.
    """

    error_domain = ErrorDomain.CONFIG
    _declared_title = "Async execution not enabled"


class PipeRunParamsError(PipelexError):
    pass


class BatchParamsError(PipelexError):
    pass


class PipeRunError(PipelexError):
    def __init__(self, message: str, run_mode: PipeRunMode, pipe_code: str):
        self.run_mode = run_mode
        self.pipe_code = pipe_code
        super().__init__(message)


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
