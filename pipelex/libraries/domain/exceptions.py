from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class DomainLibraryError(PipelexError):
    """A domain the library is asked for or asked to remove that it does not hold, which no caller reaches but by a bug."""

    error_code = CoreCode.RUNTIME_UNEXPECTED
