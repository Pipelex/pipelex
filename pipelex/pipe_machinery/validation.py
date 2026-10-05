import re
from collections.abc import Mapping

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.variable_multiplicity import format_concept_with_multiplicity, parse_concept_with_multiplicity
from pipelex.tools.misc.string_utils import get_root_from_dotted_path, is_snake_case
from pipelex.validation_error_types import PipeValidationErrorType

# The grammar of an input name, the standard's `[a-z][a-z0-9_]*`: a plain snake_case identifier, which
# is never dotted. It applies to every key of a pipe's `inputs`, whatever the pipe, and to a PipeBatch's
# `input_list_name`. The MTHDS JSON Schema generator writes this same pattern on both, so a structural
# check refuses exactly what `validate_input_names` and `check_input_list_name` refuse.
INPUT_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"


def is_input_used_by_variables(input_name: str, *, variable_paths: set[str]) -> bool:
    """Check if an input is used by any of the variable paths.

    An input is considered used if:
    - It exactly matches a variable path, OR
    - It is a prefix of any variable path (the input is accessed via attributes)

    Args:
        input_name: The declared input name
        variable_paths: Set of full dotted variable paths used in the template

    Returns:
        True if the input is used by any variable path.
    """
    for var_path in variable_paths:
        # Exact match
        if var_path == input_name:
            return True
        # Input is a prefix of the variable path
        if var_path.startswith(input_name + "."):
            return True
    return False


def check_inputs_match_variables(
    *,
    declared_inputs: set[str],
    variable_paths: set[str],
    reader: str,
) -> None:
    """Refuse a variable the templates read that no input declares, then a declared input no template reads.

    The rule shared by every operator that reads its inputs through templates: PipeLLM, PipeCompose,
    PipeSearch and PipeImgGen. It is the composition of `check_variables_are_declared` and
    `check_inputs_are_read`, in that order. PipeJudge calls the first half alone, since every input it
    declares is material to judge whether its question names it or not.

    Raises:
        PipeValidationError: ``MISSING_INPUT_VARIABLE`` with the undeclared root names, or
            ``EXTRANEOUS_INPUT_VARIABLE`` with the unread input names, each sorted.
    """
    check_variables_are_declared(declared_inputs=declared_inputs, variable_paths=variable_paths, reader=reader)
    check_inputs_are_read(declared_inputs=declared_inputs, variable_paths=variable_paths, reader=reader)


def check_variables_are_declared(
    *,
    declared_inputs: set[str],
    variable_paths: set[str],
    reader: str,
) -> None:
    """Refuse a variable the templates read that no input declares.

    ``variable_paths`` are the full dotted paths the operator's templates read, already rid of the
    operator's special names, and ``reader`` names the fields that read them, for the message
    ("prompt or system_prompt", "template"). A path reads the input its root names, on every operator
    alike: ``page.page_view`` reads ``page``, and the field is reached through that input's concept.

    Raises:
        PipeValidationError: ``MISSING_INPUT_VARIABLE`` with the undeclared root names, sorted.
    """
    missing_names = sorted({get_root_from_dotted_path(variable_path) for variable_path in variable_paths} - declared_inputs)
    if missing_names:
        quoted_names = _quoted_names(names=missing_names)
        if len(missing_names) == 1:
            msg = f"Variable {quoted_names} is read by the {reader} but not declared in `inputs`. Declare it in `inputs`, or stop reading it."
        else:
            msg = f"Variables {quoted_names} are read by the {reader} but not declared in `inputs`. Declare them in `inputs`, or stop reading them."
        raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE, variable_names=missing_names)


def check_inputs_are_read(*, declared_inputs: set[str], variable_paths: set[str], reader: str) -> None:
    """Refuse a declared input no template reads: an input is read by a path equal to its name or rooted in it.

    Raises:
        PipeValidationError: ``EXTRANEOUS_INPUT_VARIABLE`` with the unread input names, sorted.
    """
    unread_names = sorted(input_name for input_name in declared_inputs if not is_input_used_by_variables(input_name, variable_paths=variable_paths))
    if unread_names:
        quoted_names = _quoted_names(names=unread_names)
        if len(unread_names) == 1:
            msg = f"Input {quoted_names} is declared but never read by the {reader}. Reference it in the {reader}, or remove it from `inputs`."
        else:
            msg = f"Inputs {quoted_names} are declared but never read by the {reader}. Reference them in the {reader}, or remove them from `inputs`."
        raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE, variable_names=unread_names)


def _quoted_names(*, names: list[str]) -> str:
    return ", ".join(f"'{name}'" for name in names)


def is_valid_input_name(input_name: str) -> bool:
    """Whether a name is a plain input name: a snake_case identifier matching ``INPUT_NAME_PATTERN``, never dotted."""
    return re.fullmatch(INPUT_NAME_PATTERN, input_name) is not None


_PLAIN_NAME_RULE = (
    "an input name is a plain snake_case identifier, matching `[a-z][a-z0-9_]*`: a lowercase letter, then lowercase letters, digits and underscores"
)


def _is_dotted_field_path(*, name: str) -> bool:
    """Whether a name reads as a root followed by field names (``invoice.total``), each segment snake_case."""
    segments = name.split(".")
    return len(segments) > 1 and all(is_snake_case(segment) for segment in segments)


def _binding_step(*, dotted_path: str) -> str:
    """The binding step a calling sequence writes to hand the field a dotted path reaches to a pipe under a plain name."""
    plain_name = dotted_path.rsplit(".", maxsplit=1)[-1]
    return f'`{{ from = "{dotted_path}", result = "{plain_name}" }}`'


def dropped_input_marker_warning(*, input_name: str, dropped_input_marker: str) -> str:
    """The warning that deleting a redundant dotted input drops the marker it declares, and where to move that marker.

    Shared by the refusal's message and the fix planner's description, so a person reading either gets the same
    warning. ``dropped_input_marker`` is written as MTHDS writes it after the concept, the empty string standing for
    a plain single value, which carries no marker.
    """
    root_name = get_root_from_dotted_path(input_name)
    if dropped_input_marker:
        return (
            f"Deleting '{input_name}' drops its marker `{dropped_input_marker}`, which '{root_name}' does not carry: "
            f"move `{dropped_input_marker}` onto '{root_name}' if the root must carry it"
        )
    return (
        f"Deleting '{input_name}' drops its plain single form, written with no marker, where '{root_name}' carries one: "
        f"declare '{root_name}' without a marker if the root must be a plain single value"
    )


def _dotted_input_message(*, input_name: str, is_root_declared: bool, dropped_input_marker: str | None = None) -> str:
    """The refusal of a dotted input name, naming both remedies: read the field through the root, or bind it.

    When the root is declared and deleting the key would drop the marker it declares, the message warns of it
    as the fix does, so a person reading the message does not delete the key blind.
    """
    root_name = get_root_from_dotted_path(input_name)
    preamble = f"Input '{input_name}' is not a plain input name: an input names one whole value, so its name cannot reach into a field with a dot."
    binding_remedy = f"have the calling sequence bind the field to a plain name with a binding step ({_binding_step(dotted_path=input_name)})"
    if is_root_declared:
        marker_warning = ""
        if dropped_input_marker is not None:
            marker_warning = f" {dropped_input_marker_warning(input_name=input_name, dropped_input_marker=dropped_input_marker)}."
        return (
            f"{preamble} '{root_name}' is already declared, so delete this key and read the field through '{root_name}' in the template "
            f"(`${input_name}`).{marker_warning} To hand the field to this pipe under a name of its own instead, {binding_remedy} and declare "
            "that name."
        )
    return (
        f"{preamble} Either declare '{root_name}' with its whole concept and read the field through it in the template (`${input_name}`), "
        f"or {binding_remedy} and declare that name."
    )


def _input_marker(*, input_spec: str) -> str:
    """The marker an input declaration carries, as MTHDS writes it after the concept: its multiplicity suffix, then its presence symbol.

    ``Text!`` carries ``!`` and ``Text[]`` carries ``[]``. A plain single value carries the empty string, and a count
    of one is the single form, so ``Text[1]!`` carries ``!`` as ``Text!`` does.
    """
    parsed_spec = parse_concept_with_multiplicity(input_spec)
    return format_concept_with_multiplicity("", multiplicity=parsed_spec.multiplicity, presence=parsed_spec.presence)


def _dropped_input_marker(*, dotted_name: str, input_specs: Mapping[str, str]) -> str | None:
    """The marker deleting a redundant dotted input would drop from its root's contract, or ``None`` when deleting it keeps that contract.

    Before dotted names were refused, every declaration under a root, the root's own and each well-formed dotted
    key's, was folded onto the root in declaration order, so the last one set the root's presence marker and
    multiplicity. Deleting a key keeps that contract unless the key is the last declaration under its root and
    carries another marker than the declaration before it, which would take over. The key's own marker is then
    returned, for the fix and the message to name. Concepts are never compared: a field's concept differs from its
    root's by nature, and typing the input by its root's whole concept is what refusing the dotted name is for.

    When this is reported, the declaration before the key is the root itself, since a key followed by another under
    the same root is always safe to delete and is reported first.
    """
    root_name = get_root_from_dotted_path(dotted_name)
    names_under_root = [
        input_name
        for input_name in input_specs
        if input_name == root_name or (_is_dotted_field_path(name=input_name) and get_root_from_dotted_path(input_name) == root_name)
    ]
    if names_under_root[-1] != dotted_name:
        return None
    dotted_marker = _input_marker(input_spec=input_specs[dotted_name])
    if _input_marker(input_spec=input_specs[names_under_root[-2]]) == dotted_marker:
        return None
    return dotted_marker


def validate_input_names(*, input_specs: Mapping[str, str]) -> None:
    """Refuse an `inputs` table holding a name that is not a plain input name.

    An input names one whole value, of the concept its slot declares, so its name is a plain snake_case
    identifier and never a dotted path into a field. One name is reported, chosen so the fix loop can
    make progress: the first dotted name whose root the same table declares and whose deletion keeps the
    root's presence marker and multiplicity, which the fix planner deletes safely, else the first dotted
    name whose root the same table declares, else the first name that is not plain, in declaration order.

    Args:
        input_specs: Each input name, in declaration order, mapped to its concept spec with its markers
            (``Text?``, ``Item[]``). The specs are already valid, as the blueprint checks them first.

    Raises:
        PipeValidationError: ``INVALID_INPUT_NAME`` naming the input, with ``redundant_input_name`` set
            when the name is dotted and its root is declared beside it, and ``dropped_input_marker`` set
            besides when deleting it would drop the marker it declares from the root's contract.
    """
    invalid_names = [input_name for input_name in input_specs if not is_valid_input_name(input_name)]
    if not invalid_names:
        return
    redundant_names = [
        invalid_name
        for invalid_name in invalid_names
        if _is_dotted_field_path(name=invalid_name) and get_root_from_dotted_path(invalid_name) in input_specs
    ]
    if redundant_names:
        dropped_markers = {
            redundant_name: _dropped_input_marker(dotted_name=redundant_name, input_specs=input_specs) for redundant_name in redundant_names
        }
        reported_name = next((redundant_name for redundant_name in redundant_names if dropped_markers[redundant_name] is None), redundant_names[0])
        raise PipeValidationError(
            message=_dotted_input_message(input_name=reported_name, is_root_declared=True, dropped_input_marker=dropped_markers[reported_name]),
            error_type=PipeValidationErrorType.INVALID_INPUT_NAME,
            variable_names=[reported_name],
            redundant_input_name=reported_name,
            dropped_input_marker=dropped_markers[reported_name],
        )
    first_invalid_name = invalid_names[0]
    if _is_dotted_field_path(name=first_invalid_name):
        msg = _dotted_input_message(input_name=first_invalid_name, is_root_declared=False)
    else:
        msg = f"Input '{first_invalid_name}' is not a valid input name: {_PLAIN_NAME_RULE}."
    raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.INVALID_INPUT_NAME, variable_names=[first_invalid_name])


def check_input_list_name(*, input_list_name: str) -> None:
    """Refuse a PipeBatch's `input_list_name` that is not a plain input name.

    It names one of the batch's own inputs, so it follows the input-name grammar: a list held in a field
    of a larger value is declared by the batch under a plain name, and handed to it by the calling sequence.

    Raises:
        PipeValidationError: ``INVALID_INPUT_NAME`` naming the list.
    """
    if is_valid_input_name(input_list_name):
        return
    if _is_dotted_field_path(name=input_list_name):
        plain_name = input_list_name.rsplit(".", maxsplit=1)[-1]
        msg = (
            f"`input_list_name` '{input_list_name}' is not a plain input name: a PipeBatch maps over a list it declares as an input "
            f'of its own, under a plain name. Declare the list itself (`{plain_name} = "<Concept>[]"`, with '
            f'`input_list_name = "{plain_name}"`), and have the calling sequence bind the field to that name with a binding step '
            f"({_binding_step(dotted_path=input_list_name)})."
        )
    else:
        msg = f"`input_list_name` '{input_list_name}' is not a valid input name: {_PLAIN_NAME_RULE}."
    raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.INVALID_INPUT_NAME, variable_names=[input_list_name])


def is_pipe_code_valid(pipe_code: str) -> bool:
    return is_snake_case(pipe_code)
