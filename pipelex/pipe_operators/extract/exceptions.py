from pipelex.base_exceptions import ErrorDomain, PipelexError


class PipeExtractFactoryError(PipelexError):
    """Raised when a ``PipeExtract``'s input is neither an image nor a document.

    Raised only while the pipe is built from its blueprint, about that blueprint, so it is the author's to fix
    (``input``) and bundle validation reports it as an item located on the pipe. Its messages name only the
    author's own pipe, concepts and template text, so they are caller-facing copy kept under STRICT disclosure.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True
