"""The fields a handled exception rides a log line as, when the line carries no traceback.

A line about an exception names the exception's class and its text in two fields, and never splices the exception
into its message: the message stays the same on every emission, so a log store groups and counts it, while the fields
say what went wrong this time and get the redaction's field treatment, control characters escaped included. No
traceback rides along: at WARNING and below a handled, expected failure is not a bug in Pipelex's frames, and at ERROR
an exception that is re-raised has its traceback written by whoever catches it.

A pydantic ``ValidationError`` is written as its locations and reasons only: its own text quotes every value it
refused, which is payload, a run's inputs or a model's response, and no log line carries payload.

``error.type`` is the OpenTelemetry semantic-convention key for the class of error an operation ended with.
``error.message`` is the key the conventions gave an error's text before deprecating the general attribute in favour
of domain-specific ones; it is kept here as ``error.type``'s companion because the ``exception.*`` keys belong to the
sinks, which write them for a record that carries the exception itself and prefix a field spelling one.
"""

from pydantic import ValidationError

#: The class of the handled exception, by its name.
ERROR_TYPE_FIELD = "error.type"

#: The handled exception's text.
ERROR_MESSAGE_FIELD = "error.message"


def _validation_error_text(*, validation_error: ValidationError) -> str:
    """Each error of a ``ValidationError`` as its location and its reason, never the input it refused."""
    located_reasons: list[str] = []
    for error in validation_error.errors(include_url=False, include_input=False, include_context=False):
        location = ".".join(str(part) for part in error["loc"])
        located_reasons.append(f"{location}: {error['msg']}" if location else error["msg"])
    return "; ".join(located_reasons) or validation_error.title


def _exception_text(*, exc: BaseException) -> str:
    """The text a handled exception is logged with: its own, except a ``ValidationError``'s, which quotes payload."""
    if isinstance(exc, ValidationError):
        return _validation_error_text(validation_error=exc)
    return str(exc)


def error_fields(*, exc: BaseException, text: str | None = None) -> dict[str, str]:
    """The ``error.type`` and ``error.message`` fields of a handled exception, to spread into a call's ``fields``.

    Args:
        exc: The exception the line is about.
        text: The text to carry instead of the exception's own, for a line whose diagnosis is the exception's cause
            chain rather than its own text.

    Returns:
        ``{"error.type": <the exception's class name>, "error.message": <its text>}``, the text of a pydantic
        ``ValidationError`` being its locations and reasons, without the values it refused.
    """
    return {ERROR_TYPE_FIELD: type(exc).__name__, ERROR_MESSAGE_FIELD: _exception_text(exc=exc) if text is None else text}
