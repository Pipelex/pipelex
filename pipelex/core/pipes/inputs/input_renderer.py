import json
from enum import StrEnum
from typing import Any

import tomlkit

from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.core.pipes.pipe_abstract import PipeAbstract


class InputsTemplateFormat(StrEnum):
    """Serialization format for a generated inputs template."""

    JSON = "json"
    TOML = "toml"


def build_inputs_template(the_pipe: PipeAbstract) -> dict[str, Any]:
    """Build the inputs template dict for a pipe.

    Args:
        the_pipe: The pipe to build the inputs template for

    Returns:
        Dictionary mapping each input variable to its generated example value

    Raises:
        NoInputsRequiredError: If the pipe has no inputs
    """
    if not the_pipe.inputs.root:
        msg = f"No inputs required for pipe '{the_pipe.code}'."
        raise NoInputsRequiredError(msg)

    return the_pipe.inputs.build_inputs_template()


def render_inputs(the_pipe: PipeAbstract, *, indent: int = 2) -> str:
    """Render a JSON representation of the pipe's inputs.

    Args:
        the_pipe: The pipe to render inputs for
        indent: Number of spaces for indentation (default: 2)

    Returns:
        Formatted JSON string with the inputs representation

    Raises:
        NoInputsRequiredError: If the pipe has no inputs
    """
    return json.dumps(build_inputs_template(the_pipe), indent=indent, ensure_ascii=False)


def render_inputs_toml(the_pipe: PipeAbstract) -> str:
    """Render a TOML representation of the pipe's inputs.

    Args:
        the_pipe: The pipe to render inputs for

    Returns:
        TOML string with the inputs representation

    Raises:
        NoInputsRequiredError: If the pipe has no inputs
    """
    return serialize_inputs_template_to_toml(build_inputs_template(the_pipe))


def serialize_inputs_template_to_toml(template: dict[str, Any]) -> str:
    """Serialize an inputs template dict to a TOML string.

    TOML has no null: a None placeholder is substituted with an empty string
    so the key stays visible in the template (omitting it would hide the field
    from the user filling the template in).

    Args:
        template: The inputs template dict (variable name -> example value)

    Returns:
        TOML string of the template
    """
    sanitized = _substitute_none_values(template)
    return tomlkit.dumps(sanitized)  # pyright: ignore[reportUnknownMemberType]


def _substitute_none_values(value: Any) -> Any:
    """Recursively replace None with an empty string in a template value."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return {key: _substitute_none_values(sub_value) for key, sub_value in value.items()}  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
    if isinstance(value, list):
        return [_substitute_none_values(sub_value) for sub_value in value]  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
    return value
