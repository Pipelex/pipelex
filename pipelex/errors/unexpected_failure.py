"""The stand-in a surface gives an exception that is not a Pipelex error, so it fails as ``runtime.unexpected``.

Every surface that reports a foreign exception, a pipe router, a failed run's webhooks, an error tracker's report and
the API server, stands the same ``PipelexUnexpectedError`` in for it, so one failure reads the same on all of them and
none quotes the foreign exception's text.
"""

from pydantic import ValidationError

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.tools.typing.pydantic_utils import format_validation_error_without_input


def make_unexpected_failure(*, error: BaseException) -> PipelexUnexpectedError:
    """Stand a `PipelexUnexpectedError` in for an exception that is not a `PipelexError`.

    Its message names the original class, and it is chained to the original so its traceback
    survives. The message becomes the run's `diagnostics.message`, which an operator's webhook
    receives, so it never holds the foreign exception's text, which can carry anything: a key of the
    run's data (`KeyError('jane.doe@acme.com')`), a value a function was handed, a server path or a
    secret. A pydantic `ValidationError` adds its reasons, which hold none of the values it refused,
    and no location, since the model it came from is not known here.
    """
    if isinstance(error, ValidationError):
        message = f"{type(error).__name__}: {format_validation_error_without_input(validation_error=error)}"
    else:
        message = type(error).__name__
    unexpected_error = PipelexUnexpectedError(message)
    unexpected_error.__cause__ = error
    unexpected_error.__suppress_context__ = True
    return unexpected_error
