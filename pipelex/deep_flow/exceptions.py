from pipelex.base_exceptions import PipelexError


class DeepFlowError(PipelexError):
    pass


class WorkflowInputError(PipelexError):
    pass


class WorkflowExecutionError(DeepFlowError):
    pass


class ContentGenerationError(DeepFlowError):
    pass


class TemporalConfigError(ValueError, DeepFlowError):
    pass


class TemporalServerError(ValueError, DeepFlowError):
    pass
