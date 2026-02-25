from pipelex.base_exceptions import PipelexError


class ContentGenerationError(PipelexError):
    pass


class NeitherUrlNorDataError(ContentGenerationError):
    pass
