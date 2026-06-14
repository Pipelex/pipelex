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


class DryRunMockBuildError(PipelexError):
    """Raised when building a leaf mock object fails (polyfactory build or model validation).

    The leaf mock builds objects via polyfactory from the schema-reconstructed class. A build failure
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
