from pipelex.base_exceptions import ErrorDomain, PipelexError


class PipeLLMFactoryError(PipelexError):
    """Raised when a ``PipeLLM``'s prompt template, or the system prompt it declares or inherits from its domain, does not parse.

    Raised only while the pipe is built from its blueprint, about that blueprint, so it is the author's to fix
    (``input``) and bundle validation reports it as an item located on the pipe. Its messages name only the
    author's own pipe, concepts and template text, so they are caller-facing copy kept under STRICT disclosure.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True
