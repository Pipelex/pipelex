from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexError
from pipelex.system.configuration.exceptions import TemporalConfigError


class TemporalFlowError(PipelexError):
    pass


class UnrecoverableWorkflowFailureError(TemporalFlowError):
    """Synthesized when a Temporal workflow failure carries no recoverable ``ErrorReport``.

    ``recover_error_report`` is total — every ``BaseException`` produces an
    ``ErrorReport``. When the failure has no embedded report (a non-Pipelex
    worker exception, a Temporal infra error, a heartbeat timeout), we
    synthesize this exception and return its ``to_error_report()``. That
    gives consumers a uniform shape with a
    stable identity (``error_type`` / ``title`` / ``type_uri``) and the
    ``RUNTIME`` classification, plus the most informative message we could
    recover from the failure chain.
    """

    error_domain = ErrorDomain.RUNTIME
    _declared_title = "Unrecoverable workflow failure"


class WorkflowInputError(TemporalFlowError):
    pass


class WorkflowExecutionError(TemporalFlowError):
    """A Temporal workflow failure observed on the submitter side.

    When the failure crossed the activity -> workflow -> submitter boundary
    carrying a structured ``ErrorReport`` (packed into ``ApplicationError.details``
    by the activity bridge), the submitter recovers it and passes it as
    ``error_report``. ``to_error_report()`` then surfaces the original
    classification — ``error_category`` / ``retryable`` / ``model`` / ``provider``
    / ``user_action`` / ``provider_metadata`` — that the Temporal serialization
    boundary would otherwise drop, leaving only a generic ``RUNTIME`` error.

    When no report was recovered (``error_report=None`` — a non-Pipelex failure,
    or a ``WorkflowAlreadyStartedError`` / ``RPCError``), ``to_error_report()``
    falls through to the base ``__cause__``-chain enrichment.
    """

    def __init__(self, message: str, error_report: ErrorReport | None = None):
        super().__init__(message)
        self.error_report = error_report

    @override
    def to_error_report(self) -> ErrorReport:
        # A recovered report already carries the worker-side classification in
        # full; return it verbatim. Upstream wrappers (``PipelineExecutionError``)
        # re-apply their own ``error_type`` / ``message`` via cause-chain
        # enrichment. With no recovered report, fall through to the base
        # behavior, which ends with ``_enrich_error_report_from_cause``.
        if self.error_report is not None:
            return self.error_report
        return super().to_error_report()


class ContentGenerationError(TemporalFlowError):
    pass


class TemporalServerError(TemporalFlowError):
    pass


class WorkerScopeConfigError(TemporalConfigError):
    pass


class WorkerProfileConfigError(TemporalConfigError):
    pass


class SearchAttributeRegistrationError(TemporalConfigError):
    """Raised at worker boot when the namespace is reachable but missing a
    configured custom search attribute. The error message includes both the
    ``pipelex-temporal setup-namespace`` invocation and the equivalent raw
    ``temporal operator search-attribute create`` command so operators on
    either side of the fence can fix the gap.
    """
