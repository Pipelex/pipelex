from pipelex.base_exceptions import ErrorDomain, PipelexError


class ConceptSpecError(PipelexError):
    """Raised when a concept spec is malformed against its authoring contract.

    Covers both the raw-shape rejections in ``parse_concept_spec`` (a non-mapping
    ``structure``, a field value that is neither a description string nor a
    field-spec mapping) and the spec-level rule failures raised inside
    ``ConceptSpec`` validators. Always describes a fault in the caller's own
    input, so it classifies as ``INPUT`` and keeps its message under STRICT
    disclosure.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True
