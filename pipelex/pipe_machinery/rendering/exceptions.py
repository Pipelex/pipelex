from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class OutputShapeUnavailableError(PipelexError, ValueError):
    """A pipe's output has no shape to render: it is ``Anything``, and no output it could produce can be determined.

    The request to render it asks for a form this pipe cannot give. It stays a ``ValueError`` for the callers that
    report it as a notice rather than a failure. The message names only the native concept.
    """

    error_code = CoreCode.REQUEST_UNSUPPORTED
