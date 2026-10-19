from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class ModuleFileError(PipelexError):
    """Exception raised for errors related to module file operations."""

    error_code = CoreCode.RUNTIME_UNEXPECTED
