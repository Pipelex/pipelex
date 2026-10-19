from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError


class PipeExtractFactoryError(PipelexError):
    """Raised when a ``PipeExtract``'s input is neither an image nor a document.

    Raised only while the pipe is built from its blueprint, about that blueprint, so it is the method's to fix
    (``method.schema_violation``) and bundle validation reports it as an item located on the pipe. Its messages
    name only the author's own pipe, concepts and template text, so they are caller-facing copy kept under STRICT
    disclosure.
    """

    error_code = CoreCode.METHOD_SCHEMA_VIOLATION
    _authors_caller_facing_message = True
