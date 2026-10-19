from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class PipeSequenceValueError(PipelexError, ValueError):
    """A ``PipeSequence`` step batches over an item its batched pipe does not take as an input: the method's wiring.

    It stays a ``ValueError`` as well, for a pydantic validator that reaches it while it reads the sequence's inputs.
    """

    error_code = CoreCode.METHOD_WIRING_INVALID
