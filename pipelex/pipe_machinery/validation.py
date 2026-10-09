import re
from collections.abc import Mapping
from typing import NamedTuple

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.memory.working_memory import PRIVATE_BINDING_NAME_PREFIX
from pipelex.core.pipes.exceptions import PipeValidationError, PipeVariableMultiplicityError
from pipelex.core.pipes.variable_multiplicity import (
    PresenceMarker,
    VariableMultiplicity,
    fixed_item_count,
    format_concept_with_multiplicity,
    is_multiple_multiplicity,
    multiplicity_from_bracket_content,
    parse_concept_with_multiplicity,
    presence_from_symbol,
    presence_symbol,
)
from pipelex.tools.misc.string_utils import (
    FIELD_PATH_PATTERN,
    FIELD_PATH_SEGMENT_REGEX,
    SNAKE_CASE_IDENTIFIER_REGEX,
    SNAKE_CASE_PATTERN,
    camel_to_snake_case,
    get_root_from_dotted_path,
    is_snake_case,
)
from pipelex.validation_error_types import PipeValidationErrorType

# The grammar of an input name, the standard's `[a-z][a-z0-9_]*`: a plain snake_case identifier, which
# is never dotted. It applies to every key of a pipe's `inputs`, whatever the pipe, and to a PipeBatch's
# `input_list_name`. The MTHDS JSON Schema generator writes this same pattern on both, so a structural
# check refuses exactly what `validate_input_names` and `check_input_list_name` refuse. It is the
# snake_case grammar of `string_utils`, the one source every name grammar here is composed from.
INPUT_NAME_PATTERN = SNAKE_CASE_PATTERN

# The grammar of a stored name, a name under which a step stores a value in working memory: a pipe step's or
# a PipeParallel branch's `result`, the `batch_as` of either, a PipeBatch's `input_item_name`, and a binding
# step's `result`. A later pipe reads a stored value through an input, or a later binding through its root,
# both plain names, so a stored name is a plain input name and every value a step stores can be read. The
# MTHDS JSON Schema generator writes this pattern on each of these fields, so a structural check refuses
# exactly what `check_stored_name` and the binding step's own validator refuse.
STORED_NAME_PATTERN = INPUT_NAME_PATTERN

# The grammar of a binding step's `from`: a root name followed by zero or more field names, separated by
# single dots, each segment a letter followed by letters, digits and underscores. Subscripts, expressions,
# whitespace and underscore-led segments are outside it.
BINDING_PATH_PATTERN = FIELD_PATH_PATTERN

# The grammar of a PipeSequence pipe step's `batch_over`: a name with no dot, which names the list as a step or the
# sequence's inputs store it, or a dotted path following the binding path grammar, which the sequence binds before
# batching over the bound list. A dotted `batch_over` outside the path grammar is `binding_step_invalid`.
SEQUENCE_STEP_BATCH_OVER_PATTERN = rf"^(?:[^.]*|{FIELD_PATH_SEGMENT_REGEX}(?:\.{FIELD_PATH_SEGMENT_REGEX})+)$"

# The grammar of a PipeParallel branch's `batch_over`: a name with no dot. A dotted `batch_over` binds, and only a
# sequence's steps bind, so a branch carrying one is `binding_step_invalid`.
PARALLEL_BRANCH_BATCH_OVER_PATTERN = r"^[^.]*$"

# The names the runtime reserves: those taking the prefix a PipeSequence binds a dotted `batch_over`'s list under. A nested
# sequence binds in its caller's working memory, so a caller's name taking the prefix could be overwritten by that list. No
# stored name or input name can take it, being plain and so never underscore-led, and `check_name_is_not_reserved` refuses
# it on the one name an author writes that no such grammar holds, a plain `batch_over`, which reads a name rather than
# storing one. The MTHDS JSON Schema generator writes this pattern under `not` on that field, so a structural check refuses
# exactly what the runtime refuses.
RESERVED_NAME_PATTERN = f"^{re.escape(PRIVATE_BINDING_NAME_PREFIX)}"

# The marker of an input declaration as `_input_marker` writes it after the concept: an optional multiplicity
# suffix (`[]` or `[N]`), then an optional presence symbol (`?` or `!`). Group 1 is the bracket content, group 2
# the presence symbol.
_INPUT_MARKER_PATTERN = r"^(?:\[(\d*)\])?([?!])?$"


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
    return is_snake_case(input_name)


_PLAIN_NAME_RULE = (
    f"an input name is a plain snake_case identifier, matching `{SNAKE_CASE_IDENTIFIER_REGEX}`: a lowercase letter, then lowercase letters, "
    "digits and underscores"
)


def _is_dotted_field_path(*, name: str) -> bool:
    """Whether a name reads as a root followed by field names (``invoice.total``), each segment snake_case."""
    segments = name.split(".")
    return len(segments) > 1 and all(is_snake_case(segment) for segment in segments)


def _binding_step(*, dotted_path: str) -> str:
    """The binding step a calling sequence writes to hand the field a dotted path reaches to a pipe under a plain name."""
    plain_name = dotted_path.rsplit(".", maxsplit=1)[-1]
    return f'`{{ from = "{dotted_path}", result = "{plain_name}" }}`'


class _InputMarkerChange(NamedTuple):
    """What deleting a redundant dotted input would change in its root's contract, as the two markers it compares."""

    # The marker the key declares, which the deletion drops.
    dropped_input_marker: str
    # The marker of the declaration before the key, which takes over when the key is deleted: the root's own
    # whenever the change is reported (see `_input_marker_change`).
    root_input_marker: str


class _InputMarkerParts(NamedTuple):
    """An input marker split into the two parts the old fold let the last declaration under a root set."""

    multiplicity: VariableMultiplicity | None
    presence: PresenceMarker

    @property
    def multiplicity_suffix(self) -> str:
        """The multiplicity part as MTHDS writes it: the empty string for a single value, else `[]` or `[N]`."""
        return format_concept_with_multiplicity("", multiplicity=self.multiplicity)

    @property
    def presence_suffix(self) -> str:
        """The presence part as MTHDS writes it: the empty string for plain, else `?` or `!`."""
        return presence_symbol(presence=self.presence)


def _parse_input_marker(*, input_marker: str) -> _InputMarkerParts:
    """Split a marker written by `_input_marker` into its multiplicity and its presence.

    Raises:
        PipeVariableMultiplicityError: When the marker is not an optional multiplicity suffix followed by an
            optional presence symbol.
    """
    marker_match = re.fullmatch(_INPUT_MARKER_PATTERN, input_marker)
    if marker_match is None:
        msg = f"Invalid input marker '{input_marker}': expected an optional multiplicity suffix (`[]` or `[N]`), then an optional `?` or `!`."
        raise PipeVariableMultiplicityError(msg)
    return _InputMarkerParts(
        multiplicity=multiplicity_from_bracket_content(bracket_content=marker_match.group(1)),
        presence=presence_from_symbol(symbol=marker_match.group(2)),
    )


def _with_symbol(*, phrase: str, symbol: str) -> str:
    """A phrase followed by the symbol MTHDS writes for it, in backticks, unless the symbol is empty."""
    if symbol:
        return f"{phrase} (`{symbol}`)"
    return phrase


def _multiplicity_state(*, multiplicity: VariableMultiplicity | None) -> str:
    """What a multiplicity makes a declaration, without its suffix: a single value, a list, or a list of N."""
    if not is_multiple_multiplicity(multiplicity=multiplicity):
        return "a single value"
    item_count = fixed_item_count(multiplicity=multiplicity)
    if item_count is None:
        return "a list"
    return f"a list of {item_count}"


def _multiplicity_form(*, multiplicity: VariableMultiplicity | None) -> str:
    """The name of a multiplicity as a form a key drops, without its suffix."""
    if not is_multiple_multiplicity(multiplicity=multiplicity):
        return "single-value form"
    if fixed_item_count(multiplicity=multiplicity) is None:
        return "list form"
    return "fixed-count form"


def _presence_name(*, presence: PresenceMarker) -> str:
    """The name of a presence marker, as the docs on optionality give it."""
    match presence:
        case PresenceMarker.PLAIN:
            return "plain"
        case PresenceMarker.OPTIONAL:
            return "optional"
        case PresenceMarker.FORCE:
            return "forced"


def _marker_edit(*, root_name: str, root_part: str, key_part: str) -> str:
    """The edit that makes the root carry the key's part where it carries its own, each written as MTHDS writes it."""
    if not root_part:
        return f"add `{key_part}` to '{root_name}'"
    if not key_part:
        return f"remove `{root_part}` from '{root_name}'"
    return f"replace `{root_part}` with `{key_part}` on '{root_name}'"


def dropped_input_marker_warning(*, input_name: str, dropped_input_marker: str, root_input_marker: str) -> str:
    """The warning that deleting a redundant dotted input drops part of the marker it declares, and how to settle it on the root.

    Shared by the refusal's message and the fix planner's description, so a person reading either gets the same
    warning. Both markers are written as MTHDS writes them after the concept, the empty string standing for a plain
    single value: ``dropped_input_marker`` is the key's, and ``root_input_marker`` its root's. Their multiplicity and
    their presence are compared apart, and the warning names, and asks to change on the root, only the part that
    differs, or both when both do, so it never asks to add to the root a part the root already carries.

    Raises:
        PipelexUnexpectedError: When the two markers are equal, since deleting the key then drops nothing and no
            raise site reports it.
    """
    root_name = get_root_from_dotted_path(input_name)
    key_parts = _parse_input_marker(input_marker=dropped_input_marker)
    root_parts = _parse_input_marker(input_marker=root_input_marker)
    is_multiplicity_dropped = key_parts.multiplicity_suffix != root_parts.multiplicity_suffix
    is_presence_dropped = key_parts.presence != root_parts.presence

    dropped_multiplicity = "its " + _with_symbol(phrase=_multiplicity_form(multiplicity=key_parts.multiplicity), symbol=key_parts.multiplicity_suffix)
    root_multiplicity = _with_symbol(phrase=_multiplicity_state(multiplicity=root_parts.multiplicity), symbol=root_parts.multiplicity_suffix)
    wanted_multiplicity = f"must be {_multiplicity_state(multiplicity=key_parts.multiplicity)}"
    dropped_presence = "its " + _with_symbol(phrase=f"{_presence_name(presence=key_parts.presence)} presence", symbol=key_parts.presence_suffix)
    root_presence = _with_symbol(phrase=_presence_name(presence=root_parts.presence), symbol=root_parts.presence_suffix)
    wanted_presence: str
    if key_parts.presence.is_plain:
        wanted_presence = f"must not be {_presence_name(presence=root_parts.presence)}"
    else:
        wanted_presence = f"must be {_presence_name(presence=key_parts.presence)}"

    dropped: str
    held: str
    edit: str
    wanted: str
    match (is_multiplicity_dropped, is_presence_dropped):
        case (True, True):
            dropped = f"{dropped_multiplicity} and {dropped_presence}"
            held = f"{root_multiplicity} and {root_presence}"
            edit = _marker_edit(root_name=root_name, root_part=root_input_marker, key_part=dropped_input_marker)
            wanted = f"{wanted_multiplicity} and {wanted_presence}"
        case (True, False):
            dropped = dropped_multiplicity
            held = root_multiplicity
            edit = _marker_edit(root_name=root_name, root_part=root_parts.multiplicity_suffix, key_part=key_parts.multiplicity_suffix)
            wanted = wanted_multiplicity
        case (False, True):
            dropped = dropped_presence
            held = root_presence
            edit = _marker_edit(root_name=root_name, root_part=root_parts.presence_suffix, key_part=key_parts.presence_suffix)
            wanted = wanted_presence
        case (False, False):
            msg = (
                f"No marker to warn of for '{input_name}': it declares the marker `{dropped_input_marker}` its root '{root_name}' declares, "
                "so deleting it drops nothing."
            )
            raise PipelexUnexpectedError(msg)
    return f"Deleting '{input_name}' drops {dropped}, where '{root_name}' is {held}: {edit} if the root {wanted}"


def _dotted_input_message(*, input_name: str, is_root_declared: bool, marker_change: _InputMarkerChange | None = None) -> str:
    """The refusal of a dotted input name, naming both remedies: read the field through the root, or bind it.

    When the root is declared and deleting the key would change the root's contract, the message warns of it
    as the fix does, so a person reading the message does not delete the key blind.
    """
    root_name = get_root_from_dotted_path(input_name)
    preamble = f"Input '{input_name}' is not a plain input name: an input names one whole value, so its name cannot reach into a field with a dot."
    binding_remedy = f"have the calling sequence bind the field to a plain name with a binding step ({_binding_step(dotted_path=input_name)})"
    if is_root_declared:
        marker_warning = ""
        if marker_change is not None:
            warning = dropped_input_marker_warning(
                input_name=input_name,
                dropped_input_marker=marker_change.dropped_input_marker,
                root_input_marker=marker_change.root_input_marker,
            )
            marker_warning = f" {warning}."
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


def _input_marker_change(*, dotted_name: str, input_specs: Mapping[str, str]) -> _InputMarkerChange | None:
    """The markers deleting a redundant dotted input would trade on its root's contract, or ``None`` when deleting it keeps that contract.

    Before dotted names were refused, every declaration under a root, the root's own and each well-formed dotted
    key's, was folded onto the root in declaration order, so the last one set the root's presence marker and
    multiplicity. Deleting a key keeps that contract unless the key is the last declaration under its root and
    carries another marker than the declaration before it, which would take over. The key's own marker and that
    declaration's are then returned, for the fix and the message to name the part that differs. Concepts are never
    compared: a field's concept differs from its root's by nature, and typing the input by its root's whole concept
    is what refusing the dotted name is for.

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
    previous_marker = _input_marker(input_spec=input_specs[names_under_root[-2]])
    if previous_marker == dotted_marker:
        return None
    return _InputMarkerChange(dropped_input_marker=dotted_marker, root_input_marker=previous_marker)


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
            when the name is dotted and its root is declared beside it, and ``dropped_input_marker`` and
            ``root_input_marker`` set besides when deleting it would change the root's contract: the marker
            the key declares, and the one its root declares.
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
        marker_changes = {
            redundant_name: _input_marker_change(dotted_name=redundant_name, input_specs=input_specs) for redundant_name in redundant_names
        }
        reported_name = next((redundant_name for redundant_name in redundant_names if marker_changes[redundant_name] is None), redundant_names[0])
        marker_change = marker_changes[reported_name]
        raise PipeValidationError(
            message=_dotted_input_message(input_name=reported_name, is_root_declared=True, marker_change=marker_change),
            error_type=PipeValidationErrorType.INVALID_INPUT_NAME,
            variable_names=[reported_name],
            redundant_input_name=reported_name,
            dropped_input_marker=marker_change.dropped_input_marker if marker_change is not None else None,
            root_input_marker=marker_change.root_input_marker if marker_change is not None else None,
        )
    first_invalid_name = invalid_names[0]
    if _is_dotted_field_path(name=first_invalid_name):
        msg = _dotted_input_message(input_name=first_invalid_name, is_root_declared=False)
    else:
        msg = f"Input '{first_invalid_name}' is not a valid input name: {_PLAIN_NAME_RULE}."
    raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.INVALID_INPUT_NAME, variable_names=[first_invalid_name])


def check_input_list_name(*, input_list_name: str, branch_pipe_code: str, input_item_name: str) -> None:
    """Refuse a PipeBatch's `input_list_name` that is not a plain input name.

    It names one of the batch's own inputs, so it follows the input-name grammar: a list held in a field
    of a larger value is declared by the batch under a plain name, and handed to it by the calling sequence,
    which binds the field to that name, or runs the branch pipe in a step whose dotted `batch_over` binds the
    list and batches over it, in place of the PipeBatch.

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
            f"({_binding_step(dotted_path=input_list_name)}), or have the calling sequence run '{branch_pipe_code}' in a step that "
            f'batches over the field itself, which binds the list and batches over it, in place of the PipeBatch (`{{ pipe = "{branch_pipe_code}", '
            f'batch_over = "{input_list_name}", batch_as = "{input_item_name}" }}`).'
        )
    else:
        msg = f"`input_list_name` '{input_list_name}' is not a valid input name: {_PLAIN_NAME_RULE}."
    raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.INVALID_INPUT_NAME, variable_names=[input_list_name])


def suggest_plain_name(*, name: str) -> str | None:
    """A plain input name close to a name that is not one, for a refusal to offer, or `None` when none comes out of it.

    The reserved prefix is dropped, dots and hyphens become underscores and PascalCase or camelCase becomes snake_case, so
    `Pages` gives `pages`, `catalog.pages` gives `catalog_pages` and `_bound_catalog_pages` gives `catalog_pages`.
    """
    unprefixed_name = name.removeprefix(PRIVATE_BINDING_NAME_PREFIX).replace(".", "_").replace("-", "_")
    candidate = re.sub(r"_+", "_", camel_to_snake_case(name=unprefixed_name)).strip("_")
    if candidate == name or not is_valid_input_name(candidate):
        return None
    return candidate


def check_stored_name(*, name: str, field_label: str) -> None:
    """Refuse a stored name that is not a plain input name.

    A stored name is a name under which a step stores a value in working memory: a pipe step's or a PipeParallel branch's
    `result`, the `batch_as` of either, and a PipeBatch's `input_item_name`. A later pipe reads a stored value through an
    input, and an input name is a plain snake_case identifier, so a value stored under any other name could never be read.
    No plain name takes the prefix the runtime reserves for the bound list of a dotted `batch_over`, being never
    underscore-led, so this refuses such a name too, and the message says why the prefix is not the author's. A binding
    step's `result` is a stored name held to the same grammar, which its own blueprint refuses as `binding_step_invalid`.

    Args:
        name: The name as written.
        field_label: The field holding it, for the message, such as "The `result` of the step running pipe 'describe_page'".

    Raises:
        PipeValidationError: ``INVALID_INPUT_NAME`` naming the name.
    """
    if is_valid_input_name(name):
        return
    stored_name_rule = "a value is stored under it in working memory for a pipe to read through an input, so it must be a plain input name"
    reason: str
    if name.startswith(PRIVATE_BINDING_NAME_PREFIX):
        reason = (
            f"{stored_name_rule}, and the `{PRIVATE_BINDING_NAME_PREFIX}` prefix it starts with is reserved for the bound list of a "
            "dotted `batch_over`, which only the runtime writes or reads."
        )
    elif "." in name:
        reason = f"{stored_name_rule}, which names one whole value and cannot reach into a field with a dot."
    else:
        reason = f"{stored_name_rule}, and {_PLAIN_NAME_RULE}."
    plain_name = suggest_plain_name(name=name)
    suggestion = f", such as '{plain_name}'" if plain_name is not None else ""
    msg = (
        f"{field_label}, '{name}', is not a plain input name: {reason} Rename it to a plain name{suggestion}, and rename every input, "
        "binding path and `batch_over` reading it to match."
    )
    raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.INVALID_INPUT_NAME, variable_names=[name])


def check_name_is_not_reserved(*, name: str, field_label: str) -> None:
    """Refuse a plain `batch_over` taking the prefix the runtime reserves for the bound list of a dotted `batch_over`.

    A PipeSequence binds a dotted `batch_over`'s list under a private name taking the prefix, `_bound_catalog_pages` for
    `catalog.pages`, and a nested sequence binds in the working memory of the sequence calling it. A step batching over such
    a name by hand would read a list a sequence it calls binds, so the prefix is the runtime's alone. A stored name never
    takes it, being a plain input name (`check_stored_name`), but a plain `batch_over` reads a name rather than storing
    one, so no other grammar keeps it off the prefix.

    Args:
        name: The name as written.
        field_label: The field holding it, for the message, such as "The `batch_over` of the step running pipe 'describe_page'".

    Raises:
        PipeValidationError: ``INVALID_INPUT_NAME`` naming the name.
    """
    if not name.startswith(PRIVATE_BINDING_NAME_PREFIX):
        return
    unreserved_name = name.removeprefix(PRIVATE_BINDING_NAME_PREFIX)
    suggestion = f", such as '{unreserved_name}'" if is_snake_case(unreserved_name) else ""
    msg = (
        f"{field_label}, '{name}', takes the `{PRIVATE_BINDING_NAME_PREFIX}` prefix, which is reserved for the bound list of a dotted "
        f"`batch_over`: a PipeSequence binds that list under a `{PRIVATE_BINDING_NAME_PREFIX}` name in the working memory it shares "
        f"with the sequence calling it, so only the runtime writes or reads such a name. Choose another name{suggestion}."
    )
    raise PipeValidationError(message=msg, error_type=PipeValidationErrorType.INVALID_INPUT_NAME, variable_names=[name])


def is_pipe_code_valid(pipe_code: str) -> bool:
    return is_snake_case(pipe_code)
