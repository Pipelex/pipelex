from pipelex.base_exceptions import ErrorDomain, PipelexError, SecurityError


class NeitherUrlNorDataError(PipelexError):
    pass


class UnsafeSchemaError(SecurityError):
    pass


class MockInferenceUnsupportedError(PipelexError):
    """Raised when ``--mock-inference`` reaches an inference operation that has no leaf-level mock.

    ``--mock-inference`` is honored only at the LLM leaf, which returns synthetic text/objects with
    reportable usage and never calls a provider. Image generation, document extraction, and web search
    have no such leaf mock yet, so under ``--mock-inference`` they would dispatch to the **real** provider
    and spend real money — the exact opposite of what the flag promises. This guard fails loud at those
    leaves instead of silently spending. Full no-spend coverage of every operator is available today via
    ``--dry-run``; per-operator leaf mocks land later (``wip/dry-run-refactor/followup-leaf-run-mode-mock.md``,
    via ``run_mode=DRY``).
    """

    # The caller picked an unsupported flag/operation combination they can fix (drop --mock-inference
    # for this pipe, or use --dry-run) — caller-fixable input, not a server-side fault.
    error_domain = ErrorDomain.INPUT
    # The message is pure caller-facing guidance (names the operation, points at --dry-run) with no
    # internal paths or secrets, so it should survive STRICT disclosure intact.
    _authors_caller_facing_message = True

    @classmethod
    def for_operation(cls, operation: str) -> "MockInferenceUnsupportedError":
        """Build the guard error for a named inference operation (e.g. ``"image generation (PipeImgGen)"``)."""
        return cls(
            f"--mock-inference does not support {operation}: it has no leaf-level mock, so the run would "
            "call the real provider and spend. Use --dry-run for full no-spend coverage."
        )


class MockInferenceObjectFidelityError(PipelexError):
    """Raised when a ``--mock-inference`` synthetic object fails re-validation against its original class.

    The object leaf mock builds its instance from the **schema-reconstructed** class (the leaf carries
    only the JSON schema, not the original class). ``ContentGenerator.make_object`` then re-validates that
    data against the **original** class. Invariants the JSON-schema round-trip cannot capture — custom
    ``@field_validator`` / ``@model_validator`` logic, or format / pattern hints encoded via
    ``json_schema_extra`` that datamodel-code-generator drops — are absent from the reconstructed class, so
    polyfactory can fill a value the reconstructed class accepts but the original rejects. This turns an
    opaque mid-run ``pydantic.ValidationError`` into a clear, actionable message that names the class and
    points at the no-spend alternative. Scoped to the mock path only: a LIVE provider's invalid output keeps
    its existing ``ValidationError`` behavior. The durable fix (build against the original class in-process)
    lands with the leaf run-mode follow-up (``wip/dry-run-refactor/followup-leaf-run-mode-mock.md`` §8).
    """

    # The caller picked --mock-inference for a pipe whose output concept enforces an invariant the schema
    # round-trip drops; they can fix it by using --dry-run (full-fidelity mock) for this pipe — caller-fixable
    # input, not a server-side fault.
    error_domain = ErrorDomain.INPUT
    # The message is pure caller-facing guidance (names the caller's own output concept class, points at
    # --dry-run) with no internal paths or secrets, so it should survive STRICT disclosure intact.
    _authors_caller_facing_message = True

    @classmethod
    def for_object_class(cls, object_class_name: str) -> "MockInferenceObjectFidelityError":
        """Build the fidelity error for a named output object class (e.g. ``"InvoiceLine"``)."""
        return cls(
            f"--mock-inference built a synthetic '{object_class_name}' that failed re-validation against the "
            "original class: the mock is generated from the JSON schema, which can drop invariants the class "
            "enforces (custom validators, json_schema_extra format/pattern hints). Use --dry-run for "
            "full-fidelity mock objects (it builds the original class directly)."
        )
