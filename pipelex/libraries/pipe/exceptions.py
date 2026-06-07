from pipelex.libraries.exceptions import LibraryError


class PipeLibraryError(LibraryError):
    pass


class PipeNotFoundError(PipeLibraryError):
    pass
