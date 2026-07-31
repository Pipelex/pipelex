from pipelex.base_exceptions import ErrorDomain, PipelexError, SecurityError


class NeitherUrlNorDataError(PipelexError):
    pass


class UnsafeSchemaError(SecurityError):
    pass


class DryRunObjectFidelityError(PipelexError):
    """Raised when a dry-run synthetic object fails re-validation against its original class.

    The dry object leaf mock builds its instance from the **schema-reconstructed** class (the leaf
    carries only the JSON schema, not the original class). ``ContentGenerator.make_object`` then
    re-validates that data against the **original** class. Invariants the JSON-schema round-trip cannot
    capture — custom ``@field_validator`` / ``@model_validator`` logic, or format / pattern hints encoded
    via ``json_schema_extra`` that datamodel-code-generator drops — are absent from the reconstructed
    class, so polyfactory can fill a value the reconstructed class accepts but the original rejects. This
    turns an opaque mid-run ``pydantic.ValidationError`` into a clear, actionable message that names the
    class and the remedy. Scoped to the dry path only: a LIVE provider's invalid output keeps its existing
    ``ValidationError`` behavior.
    """

    # The caller's output concept enforces an invariant the schema round-trip drops; they can fix it by
    # declaring `examples` / `mock_format` on the offending fields — caller-fixable input, not a
    # server-side fault.
    error_domain = ErrorDomain.INPUT
    # The message is pure caller-facing guidance (names the caller's own output concept class and the
    # field-level remedy) with no internal paths or secrets, so it should survive STRICT disclosure intact.
    _authors_caller_facing_message = True

    @classmethod
    def for_object_class(cls, object_class_name: str) -> "DryRunObjectFidelityError":
        """Build the fidelity error for a named output object class (e.g. ``"InvoiceLine"``)."""
        return cls(
            f"The dry-run leaf mock built a synthetic '{object_class_name}' that failed re-validation against "
            "the original class: the mock is generated from the JSON schema, which can drop invariants the class "
            "enforces (custom validators, json_schema_extra format/pattern hints). Declare `examples` or "
            "`mock_format` on the constrained fields so the mock factory produces valid values."
        )


class OutputStructureSchemaError(PipelexError):
    """Raised when an output structure class cannot produce the JSON schema a structured leaf needs.

    Every structured leaf ultimately describes the caller's output class to a provider as JSON Schema, so
    a class pydantic cannot describe cannot drive one — an ``arbitrary_types_allowed`` field, or an opaque
    type carrying only ``__get_pydantic_core_schema__``, makes ``model_json_schema()`` raise.

    The dry run has to be the place that says so. Polyfactory will happily mock such a class, so nothing
    else on the dry path notices, and pydantic's own ``PydanticInvalidForJsonSchema`` is a bare
    ``RuntimeError``: raised live, inside the worker, it carries no model attribution, no remedy and no
    error identity. Surfacing it here turns a mid-run crash into a ``pipelex validate`` failure that names
    the class.
    """

    # The caller's output concept uses a type pydantic cannot describe as JSON Schema; they fix it by
    # changing the field or teaching the type `__get_pydantic_json_schema__` — caller-fixable input.
    error_domain = ErrorDomain.INPUT
    # The message names the caller's own output concept class and the remedy, with no internal paths or
    # secrets, so it should survive STRICT disclosure intact.
    _authors_caller_facing_message = True

    @classmethod
    def for_object_class(cls, *, object_class_name: str, reason: str) -> "OutputStructureSchemaError":
        """Build the schema error for a named output object class (e.g. ``"InvoiceLine"``)."""
        return cls(
            f"The output structure '{object_class_name}' cannot produce a JSON schema, so it cannot be used as a "
            f"structured output: {reason}. Every structured leaf describes your output class to the provider as "
            "JSON Schema. Replace the field whose type pydantic cannot describe, or give that type a "
            "`__get_pydantic_json_schema__`."
        )


class DryRunMockBuildError(PipelexError):
    """Raised when building a leaf mock object fails (polyfactory build or model validation).

    The leaf mock builds objects via polyfactory from whichever class the leaf resolved: the caller's
    real class in-process, the schema-reconstructed one on a worker. In-process is the common trigger,
    because the real class carries every invariant the schema round-trip would have dropped — so a
    constraint polyfactory cannot satisfy fails here rather than surviving into
    :class:`DryRunObjectFidelityError`. A build failure
    here is deterministic — retrying it (e.g. Temporal activity retries) can never succeed — so it is
    surfaced as a typed ``PipelexError``, which the activity error boundary converts to a terminal
    ``ApplicationError``. The message names the class and the remedy: declare ``examples`` or
    ``mock_format`` on fields whose constraints polyfactory cannot satisfy from the schema alone.
    """

    # The caller's output concept has field constraints the mock factory cannot satisfy; fixable by
    # declaring `examples` / `mock_format` on those fields — caller-fixable input, not a server fault.
    error_domain = ErrorDomain.INPUT
    # The message is pure caller-facing guidance (names the caller's own output concept class and the
    # field-level remedy) with no internal paths or secrets, so it should survive STRICT disclosure intact.
    _authors_caller_facing_message = True

    @classmethod
    def for_object_class(cls, object_class_name: str) -> "DryRunMockBuildError":
        """Build the mock-build error for a named output object class (e.g. ``"InvoiceLine"``)."""
        return cls(
            f"Failed to build a mock '{object_class_name}' for the dry/mocked inference leaf: polyfactory "
            "could not produce an instance that satisfies the class constraints. Declare `examples` or "
            "`mock_format` on the constrained fields so the mock factory produces valid values."
        )
