from pipelex.tools.exceptions import RootException


class DeepFlowError(RootException):
    pass


class WorkflowInputError(RootException):
    pass


class WorkflowExecutionError(DeepFlowError):
    pass


class ContentGenerationError(DeepFlowError):
    pass


class TemporalConfigError(ValueError, DeepFlowError):
    pass


class TemporalServerError(ValueError, DeepFlowError):
    pass
