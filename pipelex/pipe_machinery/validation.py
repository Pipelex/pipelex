import re
from collections.abc import Sequence

from pipelex.core.pipes.exceptions import PipeValidationError
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


def _dotted_input_message(*, input_name: str, is_root_declared: bool) -> str:
    """The refusal of a dotted input name, naming both remedies: read the field through the root, or bind it."""
    root_name = get_root_from_dotted_path(input_name)
    preamble = f"Input '{input_name}' is not a plain input name: an input names one whole value, so its name cannot reach into a field with a dot."
    binding_remedy = f"have the calling sequence bind the field to a plain name with a binding step ({_binding_step(dotted_path=input_name)})"
    if is_root_declared:
        return (
            f"{preamble} '{root_name}' is already declared, so delete this key and read the field through '{root_name}' in the template "
            f"(`${input_name}`). To hand the field to this pipe under a name of its own instead, {binding_remedy} and declare that name."
        )
    return (
        f"{preamble} Either declare '{root_name}' with its whole concept and read the field through it in the template (`${input_name}`), "
        f"or {binding_remedy} and declare that name."
    )


def validate_input_names(*, input_names: Sequence[str]) -> None:
    """Refuse an `inputs` table holding a name that is not a plain input name.

    An input names one whole value, of the concept its slot declares, so its name is a plain snake_case
    identifier and never a dotted path into a field. One name is reported, chosen so the fix loop can
    make progress: the first dotted name whose root the same table declares, which is redundant and
    which the fix planner deletes, else the first name that is not plain, in declaration order.

    Raises:
        PipeValidationError: ``INVALID_INPUT_NAME`` naming the input, with ``redundant_input_name`` set
            when the name is dotted and its root is declared beside it.
    """
    invalid_names = [input_name for input_name in input_names if not is_valid_input_name(input_name)]
    if not invalid_names:
        return
    declared_names = set(input_names)
    for invalid_name in invalid_names:
        if _is_dotted_field_path(name=invalid_name) and get_root_from_dotted_path(invalid_name) in declared_names:
            raise PipeValidationError(
                message=_dotted_input_message(input_name=invalid_name, is_root_declared=True),
                error_type=PipeValidationErrorType.INVALID_INPUT_NAME,
                variable_names=[invalid_name],
                redundant_input_name=invalid_name,
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
