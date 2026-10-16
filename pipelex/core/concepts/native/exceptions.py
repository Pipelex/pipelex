from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class NativeConceptDefinitionError(PipelexError):
    """A native concept asked for a definition it lacks: every caller checks nativeness first, so it is an invariant."""

    error_code = CoreCode.RUNTIME_UNEXPECTED
