"""The runtime half of a binding step: the value at a derived path, copied whole, or the segment that held nothing.

The walk follows the segments its derivation recorded, attribute by attribute, through the content of the
root's stuff. It is null-aware and list-aware, as the standard says:

- across a list, whether the root holds one or a field does, the rest of the path is applied to every item,
  and every list crossed is flattened into one list, items holding nothing being dropped;
- on a single value, a segment holding nothing ends the walk, and the binding records an absence naming it.

The value reached is a deep copy, never an alias of the root: a concept's content is copied whole, every field
included, and a plain value is stored as the native concept its field derives (`str` as `TextContent`, a number
as `NumberContent`, and so on), since the structure classes hold raw Python scalars.
"""

import copy
import datetime
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
        BindingStepRunError: When the value contradicts its declared structure.
    """
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
    if not values or values[0] is None:
        return FoundNothing(empty_path=empty_path or reached_path)
    return _store_value(value=values[0], leaf_kind=derivation.leaf_kind, path=derivation.path)


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
        case BindingValueKind.UNDERIVABLE:
            pass
    msg = f"Binding '{path}' reached a '{type(value).__name__}', which cannot be stored as {leaf_kind.leaf_description}'s value."
    raise BindingStepRunError(msg)
