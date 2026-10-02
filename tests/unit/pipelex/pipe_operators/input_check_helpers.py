from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.mthds_parsing.handle_pipe_errors import extract_wrapped_pipe_validation_error
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint


def refused_input_error(*, blueprint_class: type[PipeBlueprint], blueprint_kwargs: dict[str, Any]) -> PipeValidationError:
    """Build a blueprint that the input check must refuse, and return the structured error it raised.

    The operator blueprints raise a ``PipeValidationError`` inside a pydantic model validator, so the
    error reaches the caller wrapped in a ``ValidationError``; the test asserts on the wrapped error's
    ``error_type`` and ``variable_names``, never on its message text.
    """
    with pytest.raises(ValidationError) as exc_info:
        blueprint_class.model_validate(blueprint_kwargs)
    for error_details in exc_info.value.errors():
        wrapped = extract_wrapped_pipe_validation_error(error_details)
        if wrapped is not None:
            return wrapped
    msg = f"No wrapped PipeValidationError found in: {exc_info.value}"
    raise AssertionError(msg)
