"""The library check of a `PipeDocGen` update: some list of records of the step's data carries the fields it matches by.

Under `table_fill = "update"`, a list of records the step's data holds may fill a Table of the template, which the engine
finds by the list's name. Which list fills which Table is known only once the template is read, so the load cannot hold a
given list to the fields `match_on` or `match_row` names: it refuses the step only when no list carries every one of
them, since then no Table could be updated, and holds each list that does carry them to their kinds. A Table filled from
a list lacking the fields is the engine's to refuse, at its template check and at the fill (`RenderJob`). The lists are
those where a Table can be filled from: an input that is a list of records, and a list of records a structured input
holds in a field, at any depth through structures. A list inside a list fills no Table, so the records of a list are not
searched further.
"""

from typing import NamedTuple

from pipelex.cogt.doc_gen.input_shape import InputShape, InputShapeKind


class RecordList(NamedTuple):
    """A list of records in a step's data, which a Table of its template may be filled from."""

    path: str
    """Its path in the data, its input's name first, such as `completions` or `report.line_items`."""

    fields: dict[str, InputShape]
    """The shape of each field of its records, by name."""


class RecordLists(NamedTuple):
    """The lists of records a step's data holds, and the paths of the values whose shape is not declared."""

    lists: list[RecordList]
    undeclared_paths: list[str]
    """Values that may hold a list of records unseen, such as a JSON input: a check cannot tell what they hold."""


def _holds_one_value(*, kind: InputShapeKind) -> bool:
    """Whether a field of this kind holds one value a cell can equal, as a key field must; `ANY` cannot be told, so it passes."""
    match kind:
        case (
            InputShapeKind.TEXT
            | InputShapeKind.MARKDOWN
            | InputShapeKind.HTML
            | InputShapeKind.NUMBER
            | InputShapeKind.BOOLEAN
            | InputShapeKind.DATE
            | InputShapeKind.DATETIME
            | InputShapeKind.TIME
            | InputShapeKind.ANY
        ):
            return True
        case InputShapeKind.STRUCTURE | InputShapeKind.LIST | InputShapeKind.IMAGE | InputShapeKind.DOCUMENT:
            return False


def _holds_a_position(*, kind: InputShapeKind) -> bool:
    """Whether a field of this kind can hold a row's position, an integer; `ANY` cannot be told, so it passes."""
    match kind:
        case InputShapeKind.NUMBER | InputShapeKind.ANY:
            return True
        case (
            InputShapeKind.TEXT
            | InputShapeKind.MARKDOWN
            | InputShapeKind.HTML
            | InputShapeKind.BOOLEAN
            | InputShapeKind.DATE
            | InputShapeKind.DATETIME
            | InputShapeKind.TIME
            | InputShapeKind.STRUCTURE
            | InputShapeKind.LIST
            | InputShapeKind.IMAGE
            | InputShapeKind.DOCUMENT
        ):
            return False


def record_lists(*, input_shapes: dict[str, InputShape]) -> RecordLists:
    """The lists of records a step's data holds, by their path, in the order its inputs and fields are declared."""
    found = RecordLists(lists=[], undeclared_paths=[])
    for input_name, shape in input_shapes.items():
        _collect(shape=shape, path=input_name, found=found)
    return found


def _collect(*, shape: InputShape, path: str, found: RecordLists) -> None:
    match shape.kind:
        case InputShapeKind.LIST:
            item = shape.item
            if item is None:
                found.undeclared_paths.append(path)
                return
            match item.kind:
                case InputShapeKind.STRUCTURE:
                    found.lists.append(RecordList(path=path, fields=item.fields))
                case InputShapeKind.ANY:
                    found.undeclared_paths.append(path)
                case (
                    InputShapeKind.TEXT
                    | InputShapeKind.MARKDOWN
                    | InputShapeKind.HTML
                    | InputShapeKind.NUMBER
                    | InputShapeKind.BOOLEAN
                    | InputShapeKind.DATE
                    | InputShapeKind.DATETIME
                    | InputShapeKind.TIME
                    | InputShapeKind.IMAGE
                    | InputShapeKind.DOCUMENT
                    | InputShapeKind.LIST
                ):
                    # Single values, files or lists of lists: nothing a Table's rows are filled from.
                    pass
        case InputShapeKind.STRUCTURE:
            for field_name, field_shape in shape.fields.items():
                _collect(shape=field_shape, path=f"{path}.{field_name}", found=found)
        case InputShapeKind.ANY:
            found.undeclared_paths.append(path)
        case (
            InputShapeKind.TEXT
            | InputShapeKind.MARKDOWN
            | InputShapeKind.HTML
            | InputShapeKind.NUMBER
            | InputShapeKind.BOOLEAN
            | InputShapeKind.DATE
            | InputShapeKind.DATETIME
            | InputShapeKind.TIME
            | InputShapeKind.IMAGE
            | InputShapeKind.DOCUMENT
        ):
            pass


def table_match_fields_refusal(*, found: RecordLists, match_on: list[str] | None, match_row: str | None) -> tuple[str, str] | None:
    """Why no Table of the step could be updated by the fields it matches records to rows by, with the blueprint field at fault, or None.

    The step is refused when its data holds no list of records, when no list carries every field the update matches by,
    or when a list that carries them holds one of a kind that cannot match a row. A value whose shape is not declared,
    such as a JSON input, may hold a list carrying the fields, so it spares the step the first two refusals.

    Returns:
        The blueprint field, `match_on` or `match_row`, and the finding, a clause naming the list, the field and why.
    """
    match_field = "match_on" if match_on is not None else "match_row"
    if not found.lists and not found.undeclared_paths:
        return (
            match_field,
            (
                "'table_fill = \"update\"' writes the records of a list into the rows of the Table it fills, and none of "
                "the step's inputs holds a list of records: declare one, such as 'ExpenseCompletion[]'"
            ),
        )
    missing_refusals: list[tuple[str, str]] = []
    for record_list in found.lists:
        missing_refusal = _missing_field_refusal(record_list=record_list, match_on=match_on, match_row=match_row)
        if missing_refusal is not None:
            missing_refusals.append(missing_refusal)
            continue
        kind_refusal = _field_kind_refusal(record_list=record_list, match_on=match_on, match_row=match_row)
        if kind_refusal is not None:
            return kind_refusal
    if found.undeclared_paths or len(missing_refusals) < len(found.lists):
        return None
    if len(missing_refusals) == 1:
        return missing_refusals[0]
    findings = "; ".join(finding for _, finding in missing_refusals)
    return missing_refusals[0][
        0
    ], f"no list of records of the step's data carries every field the update matches rows by, so no Table could be updated: {findings}"


def _missing_field_refusal(*, record_list: RecordList, match_on: list[str] | None, match_row: str | None) -> tuple[str, str] | None:
    """The first field the update matches by that a list's records lack, as the blueprint field and the finding, or None."""
    available = ", ".join(f"'{field_name}'" for field_name in record_list.fields) or "none"
    for key_field in match_on or []:
        if key_field not in record_list.fields:
            return "match_on", f"the records of '{record_list.path}' have no field '{key_field}' to match a row's key by (their fields: {available})"
    if match_row is not None and match_row not in record_list.fields:
        return (
            "match_row",
            f"the records of '{record_list.path}' have no field '{match_row}' holding their row's position (their fields: {available})",
        )
    return None


def _field_kind_refusal(*, record_list: RecordList, match_on: list[str] | None, match_row: str | None) -> tuple[str, str] | None:
    """The first field a list's records carry whose kind cannot match a row, as the blueprint field and the finding, or None."""
    for key_field in match_on or []:
        key_shape = record_list.fields[key_field]
        if not _holds_one_value(kind=key_shape.kind):
            return (
                "match_on",
                f"the key field '{key_field}' of the records of '{record_list.path}' holds a {key_shape.kind}, not one value a cell can hold",
            )
    if match_row is not None and not _holds_a_position(kind=record_list.fields[match_row].kind):
        return (
            "match_row",
            f"the field '{match_row}' of the records of '{record_list.path}' holds a row's position, so it must be an integer or a number field",
        )
    return None
