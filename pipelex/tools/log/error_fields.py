"""The fields a handled exception rides a log line as, when the line carries no traceback.

A line about an exception names the exception's class and its text in two fields, and never splices the exception
into its message: the message stays the same on every emission, so a log store groups and counts it, while the fields
say what went wrong this time and get the redaction's field treatment, control characters escaped included. No
traceback rides along: at WARNING and below a handled, expected failure is not a bug in Pipelex's frames, and at ERROR
an exception that is re-raised has its traceback written by whoever catches it.

A pydantic ``ValidationError`` is written as its locations and reasons only: its own text quotes every value it
refused, which is payload, a run's inputs or a model's response, and no log line carries payload. A reason is pydantic's
own message, kept only when nothing in it came from the input: pydantic wrote all of it, and every value its template
fills in comes from the schema, a bound, the expected values or a discriminator's name. Otherwise the error is written as
its location and its error type, ``date: value_error``: a custom validator's message is the validator's text, which can
quote the value it rejected, and several of pydantic's own templates quote the input too, an unknown tag of a
discriminated union, the character a UUID could not parse, a parser's own complaint. An ``extra_forbidden`` error's last
location component is the key the caller sent, which is input by definition, so its location stops at its parent.

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


#: The keys of a pydantic error's context whose values come from the schema, never from the input: the bounds a field
#: declares, the values, tags, schemes or version it expects, a discriminator's name, a pattern, and the class or the kind
#: of collection it validates into. A context holding any other key, the input's own tag, its length, or a parser's or
#: a validator's ``error`` text, which can quote the input, keeps its message off the line.
SCHEMA_CONTEXT_KEYS = frozenset(
    {
        "gt",
        "ge",
        "lt",
        "le",
        "multiple_of",
        "min_length",
        "max_length",
        "max_digits",
        "decimal_places",
        "whole_digits",
        "expected",
        "expected_tags",
        "expected_schemes",
        "expected_version",
        "discriminator",
        "pattern",
        "class_name",
        "class",
        "field_type",
        "method_name",
        "tz_expected",
        "encoding",
    }
)

#: The error type of a key the model forbids, whose last location component is that key, as the caller sent it.
EXTRA_FORBIDDEN_ERROR_TYPE = "extra_forbidden"

#: Every error type pydantic itself knows how to word.
_PYDANTIC_ERROR_TYPES: frozenset[str] = frozenset(get_args(ErrorType))


def _pydantic_own_reason(*, error: ErrorDetails) -> str | None:
    """The error's message when nothing in it came from the input, or ``None`` when any of it may have.

    A type pydantic does not know is a ``PydanticCustomError``'s, whose message the validator wrote. A known type is
    kept only when every key of its context is in ``SCHEMA_CONTEXT_KEYS``, so that its template is filled from the
    schema alone, and when its message is exactly the one pydantic renders for it, which a ``PydanticCustomError``
    reusing a built-in type's name with a message of its own is not.
    """
    error_type = error["type"]
    if error_type not in _PYDANTIC_ERROR_TYPES:
        # A type pydantic does not know, and so a `PydanticCustomError`'s, worded by the validator.
        return None
    context = error.get("ctx")
    if context is not None and not SCHEMA_CONTEXT_KEYS.issuperset(context):
        # A value of the context may come from the input, or be a validator's or a parser's own text.
        return None
    try:
        own_message = PydanticKnownError(cast("ErrorType", error_type), context).message()
    except (KeyError, TypeError, ValueError):
        # Not with the context its template needs: the message is not pydantic's.
        return None
    if own_message != error["msg"]:
        return None
    return own_message


def _validation_error_text(*, validation_error: ValidationError) -> str:
    """Each error of a ``ValidationError`` as its location and its reason, never the input it refused.

    The reason is pydantic's own message, or the error's type where the message may hold something of the input, since
    a validator's text, or one of pydantic's templates, can quote the very value it rejected. A forbidden key's location
    stops at its parent, the key being the caller's own text.
    """
    located_reasons: list[str] = []
    for error in validation_error.errors(include_url=False, include_input=False):
        location_parts = error["loc"][:-1] if error["type"] == EXTRA_FORBIDDEN_ERROR_TYPE else error["loc"]
        location = ".".join(str(part) for part in location_parts)
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
        ``ValidationError`` being its locations and reasons, without the values it refused, without a forbidden key's
        name, and without any message that may quote the input, a custom validator's or one of pydantic's own, which
        is written as its error type.
    """
    return {ERROR_TYPE_FIELD: type(exc).__name__, ERROR_MESSAGE_FIELD: _exception_text(exc=exc) if text is None else text}
