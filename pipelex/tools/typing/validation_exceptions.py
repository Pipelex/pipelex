"""The refusal a pydantic validator raises when its message holds nothing of the value it refused.

Its own module, importing nothing, because ``pydantic_utils`` reads it and ``pipelex.base_exceptions``, which the
package's ``exceptions.py`` imports, already imports ``pydantic_utils``.
"""


class InputFreeValueError(ValueError):
    """A validator's refusal whose message names what was expected and never the value it refused.

    Pydantic wraps it into a ``value_error`` like any ``ValueError``. Where a ``ValidationError`` over a run's data is
    written without its input, by ``format_validation_error_without_input``, a ``value_error`` keeps its message only
    when the validator raised this class, since any other validator's text may quote the value it rejected.
    """
