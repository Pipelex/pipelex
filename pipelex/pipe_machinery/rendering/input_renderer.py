import json
from enum import StrEnum
from typing import Any, cast

import tomlkit

from pipelex.core.memory.input_shaper import InputKind, InputShaper
from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.interpreter_hub import get_concept_library
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract


class InputsTemplateFormat(StrEnum):
    """Serialization format for a generated inputs template."""

    JSON = "json"
    TOML = "toml"


def build_inputs_template(the_pipe: PipeAbstract, *, explicit: bool = False) -> dict[str, Any]:
    """Build the inputs template dict for a pipe.

    By default the template is the *light*, signature-driven shape (D11): example values shaped like
    what smart inputs accepts — a bare string for a Text-refining input, a bare number for a
    Number-refining one, the content dict for a structured one, a bare URL for a file-ish one, and
    the same wrapped in a list for a declared-multiple input. With ``explicit=True`` the ceremonial
    ``{"concept", "content"}`` envelope form is kept.

    Args:
        the_pipe: The pipe to build the inputs template for
        explicit: When True, keep the envelope form; when False (default), emit the light shape.

    Returns:
        Dictionary mapping each input variable to its generated example value

    Raises:
        NoInputsRequiredError: If the pipe has no inputs
    """
    if not the_pipe.inputs.root:
        msg = f"No inputs required for pipe '{the_pipe.code}'."
        raise NoInputsRequiredError(msg)

    envelope_template = the_pipe.inputs.build_inputs_template()
    if explicit:
        return envelope_template
    return _delighten_template(envelope_template, input_specs=the_pipe.inputs)


def render_inputs(the_pipe: PipeAbstract, *, indent: int = 2, explicit: bool = False) -> str:
    """Render a JSON representation of the pipe's inputs.

    Args:
        the_pipe: The pipe to render inputs for
        indent: Number of spaces for indentation (default: 2)
        explicit: When True, keep the envelope form; when False (default), emit the light shape.

    Returns:
        Formatted JSON string with the inputs representation

    Raises:
        NoInputsRequiredError: If the pipe has no inputs
    """
    return json.dumps(build_inputs_template(the_pipe, explicit=explicit), indent=indent, ensure_ascii=False)


def render_inputs_toml(the_pipe: PipeAbstract, *, explicit: bool = False) -> str:
    """Render a TOML representation of the pipe's inputs.

    In the default light mode each top-level key carries the declared concept as a ``# concept: ...``
    comment (TOML has comments; JSON does not — one reason ``--explicit`` stays around).

    Args:
        the_pipe: The pipe to render inputs for
        explicit: When True, keep the envelope form; when False (default), emit the light shape.

    Returns:
        TOML string with the inputs representation

    Raises:
        NoInputsRequiredError: If the pipe has no inputs
    """
    template = build_inputs_template(the_pipe, explicit=explicit)
    if explicit:
        return serialize_inputs_template_to_toml(template)
    return serialize_inputs_template_to_toml(template, light=True, concept_comments=build_concept_comments(the_pipe.inputs))


def serialize_inputs_template_to_toml(
    template: dict[str, Any],
    *,
    light: bool = False,
    concept_comments: dict[str, str] | None = None,
) -> str:
    """Serialize an inputs template dict to a TOML string.

    TOML has no null: a None placeholder is substituted with an empty string so the key stays visible
    in the template (omitting it would hide the field from the user filling the template in).

    Envelope templates (``light=False``) are all-tables, so the plain ``tomlkit.dumps`` layout is
    both valid and unchanged. Light templates interleave bare top-level scalars with structured
    values, so they are laid out with **inline tables** — everything stays at the top level, which
    keeps declaration order and lets a trailing scalar avoid being swallowed into a ``[section]`` — and
    each key may carry a ``# concept: ...`` comment.

    Args:
        template: The inputs template dict (variable name -> example value)
        light: When True, use the inline-table layout that a light template requires.
        concept_comments: Optional per-key comment text (without the leading ``# ``), only used in
            light mode.

    Returns:
        TOML string of the template
    """
    sanitized = _substitute_none_values(template)
    if not light:
        return tomlkit.dumps(sanitized)  # pyright: ignore[reportUnknownMemberType]

    document = tomlkit.document()
    comments = concept_comments or {}
    for key, value in sanitized.items():
        comment_text = comments.get(key)
        if comment_text:
            document.add(tomlkit.comment(comment_text))
        document[key] = _to_toml_value(value)
    return tomlkit.dumps(document)  # pyright: ignore[reportUnknownMemberType]


def _delighten_template(envelope_template: dict[str, Any], *, input_specs: InputStuffSpecs) -> dict[str, Any]:
    """Transform every envelope entry into its light value, dispatched on the declared concept's kind."""
    light_template: dict[str, Any] = {}
    concept_provider = get_concept_library()
    for variable_name, entry in envelope_template.items():
        stuff_spec = input_specs.get_required_stuff_spec(variable_name=variable_name)
        kind = InputShaper.resolve_input_kind(stuff_spec.concept, concept_provider=concept_provider)
        light_template[variable_name] = _delighten_entry(entry, kind=kind)
    return light_template


def _delighten_entry(entry: dict[str, Any], *, kind: InputKind) -> Any:
    """Turn one envelope entry (``{"concept", "content"}``) into the light value the shaper accepts.

    Mirrors the shaper's arms (see ``input_shaper.py``): a scalar unwraps to its single content
    field, a structured value keeps its content dict, and a Dynamic / out-of-matrix value keeps the
    whole envelope — the signature genuinely can't shape it, so bottom-up building still needs it.
    """
    match kind:
        case InputKind.DYNAMIC:
            return entry
        case InputKind.STRUCTURED:
            return entry["content"]
        case InputKind.TEXT | InputKind.NUMBER | InputKind.YES_NO | InputKind.DATE | InputKind.TIME | InputKind.IMAGE | InputKind.DOCUMENT:
            return _unwrap_scalar_content(entry["content"], envelope=entry)


def _unwrap_scalar_content(content: Any, *, envelope: dict[str, Any]) -> Any:
    """Unwrap a scalar input's content to its bare field value (element-wise for a list).

    Each scalar content is a single-field dict (``{"text": ...}`` / ``{"number": ...}`` / ``{"url":
    ...}`` / ``{"date": ...}`` / ``{"yes_no": ...}``) — the bare value the shaper re-wraps. A content
    that is not a single-field dict (a refining scalar with extra required fields, which the shaper
    can't build from a bare value anyway) can't be delightened losslessly, so the whole envelope is
    kept for that input, so the template still runs.
    """
    items: list[Any] = cast("list[Any]", content) if isinstance(content, list) else [content]
    unwrapped: list[Any] = []
    for item in items:
        if isinstance(item, dict) and len(cast("dict[str, Any]", item)) == 1:
            unwrapped.append(next(iter(cast("dict[str, Any]", item).values())))
        else:
            return envelope
    return unwrapped if isinstance(content, list) else unwrapped[0]


def build_concept_comments(input_specs: InputStuffSpecs) -> dict[str, str]:
    """Build the per-input ``concept: <ref>`` comment map (declared concept + multiplicity/presence).

    Shared by both the human ``render_inputs_toml`` and the agent-CLI TOML path so a light TOML
    template carries the same concept hints on either surface.
    """
    return {variable_name: f"concept: {stuff_spec.to_bundle_representation()}" for variable_name, stuff_spec in input_specs.root.items()}


def _to_toml_value(value: Any) -> Any:
    """Convert a light template value into an order-preserving TOML value (dicts become inline tables)."""
    if isinstance(value, dict):
        inline_table = tomlkit.inline_table()
        for key, sub_value in cast("dict[str, Any]", value).items():
            inline_table[key] = _to_toml_value(sub_value)
        return inline_table
    if isinstance(value, list):
        array = tomlkit.array()
        for item in cast("list[Any]", value):
            array.append(_to_toml_value(item))  # pyright: ignore[reportUnknownMemberType]
        return array
    return value


def _substitute_none_values(value: Any) -> Any:
    """Recursively replace None with an empty string in a template value."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return {key: _substitute_none_values(sub_value) for key, sub_value in value.items()}  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
    if isinstance(value, list):
        return [_substitute_none_values(sub_value) for sub_value in value]  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
    return value
