from pipelex.core.pipe_errors import PipeDefinitionError


class PipeSpecError(PipeDefinitionError):
    pass


class PipeExtractSpecError(PipeSpecError):
    pass


class PipeParallelSpecError(PipeSpecError):
    pass
