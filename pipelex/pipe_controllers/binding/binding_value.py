"""The runtime half of a binding step: the value at a derived path, copied whole, or the segment that held nothing.

The walk follows the segments its derivation recorded, attribute by attribute, through the content of the
root's stuff. It is null-aware and list-aware, as the standard says:

- across a list, whether the root holds one or a field does, the rest of the path is applied to every item,
  and every list crossed is flattened into one list, items holding nothing being dropped;
- on a single value, a segment holding nothing ends the walk, and the binding records an absence naming it;
- a root whose shape contradicts the derived multiplicity is a run error: a single result never chooses one item of a list.

The value reached is a deep copy, never an alias of the root: a concept's content is copied whole, every field
included, and a plain value is stored as the native concept its field derives (`str` as `TextContent`, a number
as `NumberContent`, and so on), since the structure classes hold raw Python scalars. A field holding
`native.Anything` holds a raw value of any type, stored as the native its type maps to, as an `Anything` input is.
"""

import copy
import datetime
import math
from typing import Any, NamedTuple, cast

from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.pipe_controllers.binding.binding_derivation import BindingDerivation, BindingValueKind
from pipelex.pipe_controllers.binding.exceptions import BindingStepRunError


class FoundNothing(NamedTuple):
    """A single-value binding whose path reached nothing, and the dotted path of the segment that held nothing."""

    empty_path: str


def bind_content(*, root_content: StuffContent, derivation: BindingDerivation) -> StuffContent | FoundNothing:
    """The value a binding binds from its root's content: a fresh deep copy, or the segment that held nothing.

    Args:
        root_content: The content of the stuff stored under the binding's root name.
        derivation: What the binding binds, derived before the run.

    Returns:
        The bound content (a `ListContent` for a plural result, possibly empty), or `FoundNothing` for a single
        result whose path reached nothing.

    Raises:
        BindingStepRunError: When the value contradicts its declared structure, or its shape the derived multiplicity.
    """
    _refuse_shape_mismatch(root_content=root_content, derivation=derivation)
    if derivation.is_bare_name:
        return copy.deepcopy(root_content)

    values: list[Any]
    if isinstance(root_content, ListContent):
        values = list(cast("ListContent[StuffContent]", root_content).items)
    else:
        values = [root_content]
    reached_path = derivation.root_name
    empty_path: str | None = None
    for segment in derivation.segments:
        reached_path = f"{reached_path}.{segment.name}"
        next_values: list[Any] = []
        for value in values:
            if value is None:
                continue
            if not hasattr(value, segment.name):
                msg = (
                    f"Binding '{derivation.path}' cannot read '{segment.name}' at '{reached_path}': the value there, a "
                    f"'{type(value).__name__}', has no such field, although the declared structure has one."
                )
                raise BindingStepRunError(msg)
            field_value = getattr(value, segment.name)
            if field_value is None:
                if empty_path is None:
                    empty_path = reached_path
                continue
            if segment.crosses_list:
                next_values.extend(_list_items(value=field_value, reached_path=reached_path, path=derivation.path))
            else:
                next_values.append(field_value)
        values = next_values

    if derivation.is_plural:
        stored_items = [_store_value(value=value, leaf_kind=derivation.leaf_kind, path=derivation.path) for value in values if value is not None]
        return ListContent[StuffContent](items=stored_items)
    # A single result walks one value at most: its root holds a single value (`_refuse_shape_mismatch`) and its path crosses no list.
    if not values or values[0] is None:
        return FoundNothing(empty_path=empty_path or reached_path)
    return _store_value(value=values[0], leaf_kind=derivation.leaf_kind, path=derivation.path)


def _refuse_shape_mismatch(*, root_content: StuffContent, derivation: BindingDerivation) -> None:
    """Refuse a root whose shape contradicts the multiplicity derived for the binding, rather than bind a value of the wrong shape.

    A single result over a list would have to choose one item and drop the others, which a binding never does. A bare name
    binds its root's value as it is, so a root derived as a list must hold one. A path whose derivation is a list maps a
    single root as a list of one, so that shape binds as derived.
    """
    if isinstance(root_content, ListContent):
        if derivation.is_plural:
            return
        item_count = len(cast("ListContent[StuffContent]", root_content).items)
        msg = (
            f"Binding '{derivation.path}' was derived as a single value, but its root '{derivation.root_name}' holds a list of "
            f"{item_count} items, and a binding never chooses one item of a list. The root was typed before the run as a single value, "
            "so whatever stored it stored a list instead, such as a step whose caller asked for several outputs."
        )
        raise BindingStepRunError(msg)
    if derivation.is_bare_name and derivation.is_plural:
        msg = (
            f"Binding '{derivation.path}' was derived as a list, but its root '{derivation.root_name}' holds a single value, "
            "and a bare name binds its root's value as it is. The root was typed before the run as a list, so whatever stored it "
            "stored a single value instead."
        )
        raise BindingStepRunError(msg)


def _list_items(*, value: Any, reached_path: str, path: str) -> list[Any]:
    if isinstance(value, ListContent):
        return list(cast("ListContent[StuffContent]", value).items)
    if isinstance(value, list):
        return list(cast("list[Any]", value))
    msg = f"Binding '{path}' expected a list at '{reached_path}', as its declared structure says, but found a '{type(value).__name__}'."
    raise BindingStepRunError(msg)


def _store_value(*, value: Any, leaf_kind: BindingValueKind, path: str) -> StuffContent:
    """A deep copy of the value at the path, stored as content: whole when it is a concept's, wrapped when it is plain."""
    match leaf_kind:
        case BindingValueKind.CONCEPT:
            if isinstance(value, StuffContent):
                return copy.deepcopy(value)
        case BindingValueKind.TEXT:
            if isinstance(value, str):
                return TextContent(text=value)
        case BindingValueKind.NUMBER:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return NumberContent(number=value)
        case BindingValueKind.YES_NO:
            if isinstance(value, bool):
                return YesNoContent(yes_no=value)
        case BindingValueKind.DATE:
            if isinstance(value, datetime.datetime):
                return DateContent(date=value.date(), time=value.timetz())
            if isinstance(value, datetime.date):
                return DateContent(date=value)
        case BindingValueKind.DATETIME:
            if isinstance(value, datetime.datetime):
                return DateContent(date=value.date(), time=value.timetz())
            if isinstance(value, datetime.date):
                return DateContent(date=value)
        case BindingValueKind.TIME:
            if isinstance(value, datetime.time):
                return TimeContent(time=value)
        case BindingValueKind.JSON:
            if isinstance(value, dict):
                return JSONContent(json_obj=copy.deepcopy(cast("dict[str, Any]", value)))
        case BindingValueKind.ANYTHING:
            if (natural_content := _natural_content(value=value)) is not None:
                return natural_content
        case BindingValueKind.UNDERIVABLE:
            pass
    msg = f"Binding '{path}' reached a '{type(value).__name__}', which cannot be stored as {leaf_kind.leaf_description}'s value."
    raise BindingStepRunError(msg)


def _natural_content(*, value: Any) -> StuffContent | None:
    """The content a value of any type is stored as, keyed on its type as an `Anything` input is shaped, `None` when it has none.

    A content is copied whole; a boolean is a yes-no, a finite number a number, a time a time, a date or a datetime a date,
    a string a text and a dict a JSON object. A list, which a single value never is, and any other object have no content.
    """
    if isinstance(value, StuffContent):
        return copy.deepcopy(value)
    # `bool` before numbers, which it subclasses, and `datetime` before `date`, likewise.
    if isinstance(value, bool):
        return YesNoContent(yes_no=value)
    if isinstance(value, (int, float)):
        return NumberContent(number=value) if math.isfinite(value) else None
    if isinstance(value, datetime.time):
        return TimeContent(time=value)
    if isinstance(value, datetime.datetime):
        return DateContent(date=value.date(), time=value.timetz())
    if isinstance(value, datetime.date):
        return DateContent(date=value)
    if isinstance(value, str):
        return TextContent(text=value)
    if isinstance(value, dict):
        return JSONContent(json_obj=copy.deepcopy(cast("dict[str, Any]", value)))
    return None
