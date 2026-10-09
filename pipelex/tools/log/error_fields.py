"""The fields a handled exception rides a log line as, when the line carries no traceback.

A line at WARNING or below about an exception the code expected and recovered from names the exception's class and
its text in two fields, and never splices the exception into its message: the message stays the same on every
emission, so a log store groups and counts it, while the fields say what went wrong this time and get the redaction's
field treatment, control characters escaped included. No traceback rides along: a handled, expected failure is not a
bug in Pipelex's frames, and only ``error`` and ``critical`` take ``include_exception``.

``error.type`` is the OpenTelemetry semantic-convention key for the class of error an operation ended with.
``error.message`` is the key the conventions gave an error's text before deprecating the general attribute in favour
of domain-specific ones; it is kept here as ``error.type``'s companion because the ``exception.*`` keys belong to the
sinks, which write them for a record that carries the exception itself and prefix a field spelling one.
"""

#: The class of the handled exception, by its name.
ERROR_TYPE_FIELD = "error.type"

#: The handled exception's text.
ERROR_MESSAGE_FIELD = "error.message"


def error_fields(*, exc: BaseException, text: str | None = None) -> dict[str, str]:
    """The ``error.type`` and ``error.message`` fields of a handled exception, to spread into a call's ``fields``.

    Args:
        exc: The exception the line is about.
        text: The text to carry instead of ``str(exc)``, for a line whose diagnosis is the exception's cause chain
            rather than its own text.

    Returns:
        ``{"error.type": <the exception's class name>, "error.message": <its text>}``.
    """
    return {ERROR_TYPE_FIELD: type(exc).__name__, ERROR_MESSAGE_FIELD: str(exc) if text is None else text}
