"""The fields a handled exception rides a log line as, when the line carries no traceback.

A line about an exception names the exception's class and its text in two fields, and never splices the exception
into its message: the message stays the same on every emission, so a log store groups and counts it, while the fields
say what went wrong this time and get the redaction's field treatment, control characters escaped included. No
traceback rides along: at WARNING and below a handled, expected failure is not a bug in Pipelex's frames, and at ERROR
an exception that is re-raised has its traceback written by whoever catches it.

A pydantic ``ValidationError`` is written as its locations and reasons only, by ``format_validation_error_without_input``
(``pipelex.tools.typing.pydantic_utils``), which a raise site refusing a run's data writes its message with as well: its
own text quotes every value it refused, which is payload, a run's inputs or a model's response, and no log line carries
payload. A reason is pydantic's own message, kept only when nothing in it came from the input: pydantic wrote all of it,
and every value its template fills in comes from the schema, a bound, the expected values or a discriminator's name.
Otherwise the error is written as
its error type, ``value_error``: a custom validator's message is the validator's text, which can quote the value it
rejected, and several of pydantic's own templates quote the input too, an unknown tag of a discriminated union, the
character a UUID could not parse, a parser's own complaint. A location quotes the keys of a dict the input holds, and a
key the model does not declare, which are input by definition, so a location is written only as far as the schema of the
validated model names it, every other component as ``<key>``; a line that does not know that model, given as
``validated_type``, writes each error by its reason alone. A line about a method author's own document, or a value
Pipelex built for itself such as a dry run's mock, says so with ``is_authored_input`` and writes its locations as
pydantic gives them, since no key of it is a run's data.

``error.type`` is the OpenTelemetry semantic-convention key for the class of error an operation ended with.
``error.message`` is the key the conventions gave an error's text before deprecating the general attribute in favour
of domain-specific ones; it is kept here as ``error.type``'s companion because the ``exception.*`` keys belong to the
sinks, which write them for a record that carries the exception itself and prefix a field spelling one.
"""

from pipelex.tools.typing.pydantic_utils import ValidatedType, describe_exception_without_input

#: The class of the handled exception, by its name.
ERROR_TYPE_FIELD = "error.type"

#: The handled exception's text.
ERROR_MESSAGE_FIELD = "error.message"

#: The registry code a failure's problem carries, which a line about a run's failure gives in place of its text.
ERROR_CODE_FIELD = "error.code"


def error_fields(
    *, exc: BaseException, text: str | None = None, validated_type: ValidatedType | None = None, is_authored_input: bool = False
) -> dict[str, str]:
    """The ``error.type`` and ``error.message`` fields of a handled exception, to spread into a call's ``fields``.

    Args:
        exc: The exception the line is about.
        text: The text to carry instead of the exception's own, for a line whose diagnosis is the exception's cause
            chain rather than its own text.
        validated_type: The model whose validation raised ``exc``, when it is a ``ValidationError`` and the line knows
            it, which lets its locations be written.
        is_authored_input: Whether the input ``exc`` refused is a method author's own document or a value Pipelex
            built for itself, never a run's data, so that its locations are written as pydantic gives them.

    Returns:
        ``{"error.type": <the exception's class name>, "error.message": <its text>}``, the text of a pydantic
        ``ValidationError`` being its reasons, each located as far as the validated model's schema names it, without
        the values it refused, without a key of the input's own, and without any message that may quote the input, a
        custom validator's or one of pydantic's own, which is written as its error type.
    """
    message = describe_exception_without_input(exc=exc, validated_type=validated_type, is_authored_input=is_authored_input) if text is None else text
    return {ERROR_TYPE_FIELD: type(exc).__name__, ERROR_MESSAGE_FIELD: message}
