from pipelex.core.pipe_errors import PipeDefinitionError


class PipeSpecException(PipeDefinitionError):
    pass


class PipeExtractSpecError(PipeSpecException):
    pass


class PipeParallelSpecError(PipeSpecException):
    pass


class PipeSequenceSpecError(PipeSpecException):
    pass


class PipeFuncSpecError(PipeSpecException):
    pass


class PipeImgGenSpecError(PipeSpecException):
    pass


class PipeComposeSpecError(PipeSpecException):
    pass


class PipeLLMSpecError(PipeSpecException):
    pass
