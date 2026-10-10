"""The fields a handled exception rides a log line as, when the line carries no traceback.

A line about an exception names the exception's class and its text in two fields, and never splices the exception
into its message: the message stays the same on every emission, so a log store groups and counts it, while the fields
say what went wrong this time and get the redaction's field treatment, control characters escaped included. No
traceback rides along: at WARNING and below a handled, expected failure is not a bug in Pipelex's frames, and at ERROR
an exception that is re-raised has its traceback written by whoever catches it.

A pydantic ``ValidationError`` is written as its locations and reasons only: its own text quotes every value it
refused, which is payload, a run's inputs or a model's response, and no log line carries payload. A reason is pydantic's
own message, kept only when pydantic wrote all of it: a custom validator's message is the validator's text, which can
quote the value it rejected, so such an error is written as its location and its error type, ``date: value_error``.

``error.type`` is the OpenTelemetry semantic-convention key for the class of error an operation ended with.
``error.message`` is the key the conventions gave an error's text before deprecating the general attribute in favour
of domain-specific ones; it is kept here as ``error.type``'s companion because the ``exception.*`` keys belong to the
sinks, which write them for a record that carries the exception itself and prefix a field spelling one.
"""

from typing import cast, get_args

from pydantic import ValidationError
from pydantic_core import ErrorDetails, PydanticKnownError
from pydantic_core.core_schema import ErrorType

#: The class of the handled exception, by its name.
ERROR_TYPE_FIELD = "error.type"

#: The handled exception's text.
ERROR_MESSAGE_FIELD = "error.message"


#: The built-in error types whose message embeds the text of an exception that code other than pydantic raised: a
#: validator's ``ValueError`` or ``assertion``, or what an attribute, an iterator or a mapping of the input raised.
FOREIGN_TEXT_ERROR_TYPES = frozenset({"value_error", "assertion_error", "get_attribute_error", "iteration_error", "mapping_type"})

#: Every error type pydantic itself knows how to word.
_PYDANTIC_ERROR_TYPES: frozenset[str] = frozenset(get_args(ErrorType))


def _pydantic_own_reason(*, error: ErrorDetails) -> str | None:
    """The error's message when pydantic wrote all of it, or ``None`` when any of it is a validator's own text.

    A type pydantic does not know is a ``PydanticCustomError``'s, whose message the validator wrote. A known type is
    kept only when its message is exactly the one pydantic renders for it, which a ``PydanticCustomError`` reusing a
    built-in type's name with a message of its own is not, and when its template embeds no other code's text.
    """
    error_type = error["type"]
    if error_type in FOREIGN_TEXT_ERROR_TYPES or error_type not in _PYDANTIC_ERROR_TYPES:
        # A foreign text, or a type pydantic does not know and so a `PydanticCustomError`'s, worded by the validator.
        return None
    try:
        own_message = PydanticKnownError(cast("ErrorType", error_type), error.get("ctx")).message()
    except (KeyError, TypeError, ValueError):
        # Not with the context its template needs: the message is not pydantic's.
        return None
    if own_message != error["msg"]:
        return None
    return own_message


def _validation_error_text(*, validation_error: ValidationError) -> str:
    """Each error of a ``ValidationError`` as its location and its reason, never the input it refused.

    The reason is pydantic's own message, or the error's type where a validator wrote the message, since a validator's
    text can quote the very value it rejected.
    """
    located_reasons: list[str] = []
    for error in validation_error.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in error["loc"])
        reason = _pydantic_own_reason(error=error) or error["type"]
        located_reasons.append(f"{location}: {reason}" if location else reason)
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
        ``ValidationError`` being its locations and reasons, without the values it refused and without a custom
        validator's message, which is written as its error type.
    """
    return {ERROR_TYPE_FIELD: type(exc).__name__, ERROR_MESSAGE_FIELD: _exception_text(exc=exc) if text is None else text}
