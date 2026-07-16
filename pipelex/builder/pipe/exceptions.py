from pipelex.base_exceptions import ErrorDomain, PipelexError


class PipeSpecError(PipelexError):
    """Raised when a pipe spec is malformed against its authoring contract.

    Covers the raw-shape rejections in ``parse_pipe_spec`` — a non-list
    ``steps`` / ``branches``, or an entry within them that is not a mapping —
    surfaced before the data reaches Pydantic validation. Always describes a
    fault in the caller's own input, so it classifies as ``INPUT`` and keeps its
    message under STRICT disclosure. The parallel of ``ConceptSpecError`` for the
    pipe authoring surface.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True
