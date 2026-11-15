"""The library check of a `PipeDocGen` update: the fields it matches records to rows by exist on those records.

Under `table_fill = "update"`, every list of records the step's data holds may fill a Table of the template, which the
engine finds by the list's name, so every one of them must carry the fields `match_on` or `match_row` names. Which list
fills which Table is known only once the template is read, so the check covers each list the data holds, where a Table
can be filled from: an input that is a list of records, and a list of records a structured input holds in a field, at
any depth through structures. A list inside a list fills no Table, so the records of a list are not searched further.
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


def match_field_refusal(*, record_list: RecordList, match_on: list[str] | None, match_row: str | None) -> tuple[str, str] | None:
    """Why a list's records cannot be matched to rows by the update's fields, with the blueprint field at fault, or None.

    Returns:
        The blueprint field, `match_on` or `match_row`, and the finding, a clause naming the list, the field and why.
    """
    available = ", ".join(f"'{field_name}'" for field_name in record_list.fields) or "none"
    for key_field in match_on or []:
        key_shape = record_list.fields.get(key_field)
        if key_shape is None:
            return "match_on", f"the records of '{record_list.path}' have no field '{key_field}' to match a row's key by (their fields: {available})"
        if not _holds_one_value(kind=key_shape.kind):
            return (
                "match_on",
                f"the key field '{key_field}' of the records of '{record_list.path}' holds a {key_shape.kind}, not one value a cell can hold",
            )
    if match_row is not None:
        row_shape = record_list.fields.get(match_row)
        if row_shape is None:
            return (
                "match_row",
                f"the records of '{record_list.path}' have no field '{match_row}' holding their row's position (their fields: {available})",
            )
        if not _holds_a_position(kind=row_shape.kind):
            return (
                "match_row",
                f"the field '{match_row}' of the records of '{record_list.path}' holds a row's position, so it must be an integer or a number field",
            )
    return None
