"""Find the stored values a tree of contents holds, wherever they sit.

A `Text`, `Markdown`, `Html` or `JSON` content may hold a reference to its value rather than the value
(`pipelex.core.stuffs.stored_value_content`), and such a content may sit anywhere in a stuff: as the stuff's content,
as an item of a list, as a field of a structure, as the text of a `TextAndImages`, at any depth. Code that is about to
render a value synchronously, a prompt template above all, must load every one of them first, so it walks the tree
with this helper and hands what it found to `load_stored_values` (`pipelex.core.stuffs.stored_value_loader`).

This module performs no IO, so workflow code may use it to decide whether a load is needed at all.
"""

from collections.abc import Iterator, Mapping
from typing import Any, NamedTuple, cast

from pydantic import BaseModel

from pipelex.core.stuffs.stored_value_content import StoredValueContent


class StoredValueAtPath(NamedTuple):
    """A content holding its value in storage, and where it sits in the tree it was found in."""

    path: str
    content: StoredValueContent

    @property
    def position(self) -> str:
        """Where the value sits, in the words a refusal to read it names."""
        return f"the stored value '{self.path}'"


def find_unloaded_stored_values(*, roots: Mapping[str, Any]) -> list[StoredValueAtPath]:
    """Every content under the given roots that holds a reference to its value which was never loaded.

    A content reached twice, through two roots naming one stuff, is listed once, under the first path that reached it.

    Args:
        roots: The values to walk, each keyed by the name its path starts with: a stuff's content keyed by the stuff's
            name, typically.

    Returns:
        The stored values to load, in the order a depth-first walk of the roots meets them.
    """
    found: list[StoredValueAtPath] = []
    seen_ids: set[int] = set()
    for root_name, root_value in roots.items():
        for stored_value in _walk(value=root_value, path=root_name):
            if id(stored_value.content) in seen_ids or stored_value.content.is_loaded:
                continue
            seen_ids.add(id(stored_value.content))
            found.append(stored_value)
    return found


def _walk(*, value: Any, path: str) -> Iterator[StoredValueAtPath]:
    if isinstance(value, StoredValueContent):
        yield StoredValueAtPath(path=path, content=value)
        return
    if isinstance(value, BaseModel):
        for field_name in type(value).model_fields:
            yield from _walk(value=getattr(value, field_name), path=f"{path}.{field_name}")
        for extra_name, extra_value in (value.model_extra or {}).items():
            yield from _walk(value=extra_value, path=f"{path}.{extra_name}")
        return
    if isinstance(value, (list, tuple)):
        for item_index, item in enumerate(cast("list[Any] | tuple[Any, ...]", value)):
            yield from _walk(value=item, path=f"{path}[{item_index}]")
        return
    if isinstance(value, dict):
        for item_key, item in cast("dict[Any, Any]", value).items():
            yield from _walk(value=item, path=f"{path}[{item_key!r}]")
