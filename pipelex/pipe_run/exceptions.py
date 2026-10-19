from typing import Any, ClassVar, Self

from mthds.protocol.problem.models import ProblemItem, ProblemLocation
from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexError, iter_cause_chain
from pipelex.core.exceptions import DryRunFailureErrorData
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, InheritsCause
from pipelex.errors.error_codes import ErrorCode, error_code_spec, first_fault_code
from pipelex.errors.problem import PipelexProblem, ProblemView, make_location, make_problem_item
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.errors.security_event import security_target_kind
from pipelex.pipe_run.located_failure import failure_location_of, locate_failure_message, located_problem, located_root_fault
from pipelex.system.pipe_run_mode import PipeRunMode


class AsyncExecutionNotEnabledError(PipelexError):
    """Raised when a route that depends on asynchronous execution is hit on a
    deployment that does not have an async execution backend enabled.

    Backend-neutral on purpose, because it is the shared contract between the
    runner API — which maps it to an HTTP status (501) — and any async-execution
    backend plugin that raises it: the Temporal plugin today, other async backends
    (e.g. Mistral Workflows) as support lands. In this repo, the local runtime's
    ``PipelexMTHDSProtocol.start`` raises it, since it runs nothing asynchronously.
    The class name, title, and detail therefore talk about *async execution* as a
    capability of the deployment, not about any specific backend brand.

    Its code is ``runtime.unsupported``: the caller's request is well-formed, and what is missing is a
    capability of this deployment, permanent under it, so the caller's useful step is the synchronous route.
    """

    error_code = CoreCode.RUNTIME_UNSUPPORTED

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

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"capability": "asynchronous execution"}


class PipeRunParamsError(PipelexError):
    """A pipe's declaration and the run's params cannot settle a value the pipe needs, such as an image count."""

    error_code = CoreCode.METHOD_SCHEMA_VIOLATION


class PipeJobError(PipelexError):
    """Our own serialized run state could not be rebuilt, or a completed run broke an invariant of ours.

    It declares its own code rather than taking its cause's: a concept-library error raised while rehydrating
    a run's memory is a fault of the transport, not of the method's concepts.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED


class DeliveryError(PipelexError):
    """Base of the failures to deliver a finished run's results."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class WebhookDeliveryError(DeliveryError):
    """A webhook announcing a run's outcome could not be delivered."""

    error_code = PipelexErrorCode.WEBHOOK_DELIVERY_FAILED


class StorageDeliveryError(DeliveryError):
    """A finished run's results could not be stored; it takes its cause's code, else storage being unavailable."""

    error_code = InheritsCause(fallback=PipelexErrorCode.STORAGE_UNAVAILABLE)


class DryRunError(PipelexError):
    """Raised when a dry run fails. The validation sweep raises it with one failure per pipe whose dry run
    failed, located at the innermost failing pipe that is not allowed to fail, so a controller that failed
    because a pipe it runs failed is reported once, at that pipe. Each failure carries its own code, and bundle
    validation reports each as its own ``dry_run`` item, with the error type ``DryRunError``, the pipe's code,
    domain and source, and the sentence the failure's code renders for a caller.

    With failures, its code is the one the answer takes among theirs (``first_fault_code``), a security refusal's
    before any other, so that a refusal a security rule made is answered under its code wherever it sits among the
    failures; its parameters are those of the failure that code is taken from, its pipe included, so that the problem's
    sentence renders whole, and its problem carries one item per failure; a validation answers it as an invalid verdict
    only when one of them is the method's and none is a security refusal. Raised elsewhere it may carry no failures, and
    then it takes the code of its cause, the failure it reports.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = InheritsCause(fallback=CoreCode.RUNTIME_UNEXPECTED)

    def __init__(self, message: str, *, failures: list[DryRunFailureErrorData] | None = None):
        self.failures = failures or []
        super().__init__(message)

    def _code_failure(self) -> DryRunFailureErrorData | None:
        """The failure whose code this error carries: the first whose code ``first_fault_code`` takes, among its security refusals if any."""
        codes = self.security_failure_codes or [failure.code for failure in self.failures]
        code = first_fault_code(codes=codes)
        for failure in self.failures:
            if failure.code == code:
                return failure
        return None

    @property
    def security_failure_codes(self) -> list[ErrorCode]:
        """The codes of its failures that a security rule refused, in the order the sweep found them."""
        return [failure.code for failure in self.failures if security_target_kind(code=failure.code) is not None]

    @property
    @override
    def own_error_code(self) -> ErrorCode | None:
        code_failure = self._code_failure()
        return code_failure.code if code_failure is not None else super().own_error_code

    @override
    def problem_params(self) -> dict[str, Any]:
        code_failure = self._code_failure()
        if code_failure is None:
            return {}
        params = dict(code_failure.params or {})
        if code_failure.pipe_code is not None:
            params.setdefault("pipe", code_failure.pipe_code)
        return params

    @override
    def problem_items(self) -> list[ProblemItem] | None:
        items: list[ProblemItem] = []
        for failure in self.failures:
            spec = error_code_spec(failure.code)
            params = dict(failure.params or {})
            if failure.pipe_code is not None and "pipe" in spec.param_names:
                params.setdefault("pipe", failure.pipe_code)
            location = make_location(pipe=failure.pipe_code, file=failure.source)
            items.append(make_problem_item(code=failure.code, params=params or None, location=location))
        return items or None


class DryRunGraphNotProducedError(DryRunError):
    """Raised when a graph-producing dry run completes but no ``GraphSpec`` was assembled onto the pipe output.

    The dry-run entrypoints (``dry_run_pipeline`` / ``dry_run_pipe_in_process``) exist to produce a
    graph, so a run that finishes without one is a contract violation on their side — not a
    validation failure of the bundle. Distinct from the bare ``PipelexError`` it replaces so that
    hosts logging only the exception type (e.g. pipelex-api's best-effort ``/validate`` graph step)
    get an unambiguous signal. Bundle validation lets it through rather than turning it into a ``dry_run``
    item, since the bundle is not at fault.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED


class PipeRouterError(PipelexError):
    """A pipe failed while running: the failure, located at the pipe where it happened.

    The pipe router raises it around every failure of the pipe it runs, chained to the failure,
    with the pipe's code and a snapshot of its stack taken where it failed. A failure that already
    carries one keeps it as it rises through the routers of the controllers above, so the innermost
    location is the one reported. Its problem is its root fault's, located (see
    `pipelex.pipe_run.located_failure`): a run whose pipe raised `StuffFactoryError` reports
    `StuffFactoryError`'s code and diagnostics, with a location naming the pipe and its path, never
    `PipeRouterError`.
    """

    error_code = InheritsCause(fallback=CoreCode.RUNTIME_UNEXPECTED)

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
    def to_problem(
        self,
        *,
        view: ProblemView,
        request_id: str | None = None,
        pipeline_run_id: str | None = None,
        failure_location: ProblemLocation | None = None,
    ) -> PipelexProblem:
        location = failure_location or failure_location_of(pipe_code=self.pipe_code, pipe_stack=self.pipe_stack)
        root_fault = located_root_fault(wrapper=self)
        if root_fault is None:
            return super().to_problem(view=view, request_id=request_id, pipeline_run_id=pipeline_run_id, failure_location=location)
        return located_problem(
            wrapper=self, root_fault=root_fault, view=view, request_id=request_id, pipeline_run_id=pipeline_run_id, failure_location=location
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
