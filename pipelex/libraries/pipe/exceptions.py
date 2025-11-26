from pipelex.base_exceptions import PipelexError


class PipeLibraryError(PipelexError):
    pass


class PipeNotFoundError(PipeLibraryError):
    pass
