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
