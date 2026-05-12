from pipelex.base_exceptions import PipelexError


class TemporalFlowError(PipelexError):
    pass


class WorkflowInputError(TemporalFlowError):
    pass


class WorkflowExecutionError(TemporalFlowError):
    pass


class ContentGenerationError(TemporalFlowError):
    pass


class TemporalConfigError(ValueError, TemporalFlowError):
    pass


class TemporalServerError(TemporalFlowError):
    pass


class WorkerScopeConfigError(TemporalConfigError):
    pass


class WorkerProfileConfigError(TemporalConfigError):
    pass


class WorkerTaskQueueUnknownError(TemporalConfigError):
    pass


class SearchAttributeRegistrationError(TemporalConfigError):
    """Raised at worker boot when the namespace is reachable but missing a
    configured custom search attribute. The error message includes both the
    ``pipelex setup-temporal-namespace`` invocation and the equivalent raw
    ``temporal operator search-attribute create`` command so operators on
    either side of the fence can fix the gap.
    """
