from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class KitError(PipelexError):
    """Raised when the kit's agent rules cannot be assembled.

    Developer tooling: reached only from `pipelex-dev kit`.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED


class KitIndexLoadingError(PipelexError):
    """Raised when the kit's index of agent rules cannot be loaded.

    Developer tooling: reached only from `pipelex-dev kit` and the rules sync check.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED
