from pipelex.core.pipe_errors import PipeDefinitionError


class PipeSpecError(PipeDefinitionError):
    pass


class PipeExtractSpecError(PipeSpecError):
    pass


class PipeParallelSpecError(PipeSpecError):
    pass


class PipeSequenceSpecError(PipeSpecError):
    pass


class PipeFuncSpecError(PipeSpecError):
    pass


class PipeImgGenSpecError(PipeSpecError):
    pass


class PipeComposeSpecError(PipeSpecError):
    pass


class PipeLLMSpecError(PipeSpecError):
    pass
