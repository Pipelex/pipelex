"""Protocol for values that know their own HTML: markupsafe's `__html__` convention.

HTML autoescaping (`TemplateCategory.HTML`) escapes every value it prints, except a value that defines
`__html__`: markupsafe calls it and inserts what it returns as it is. A content class defines it when its
HTML rendering is both the right thing to print and safe to insert, which is the case of `MarkdownContent`,
whose conversion escapes any raw HTML in the source. `StuffArtefact` answers `__html__` for a stuff whose
content does, so `{{ report }}` prints a Markdown stuff as formatted HTML with no filter, while a Text stuff,
whose content defines no `__html__`, keeps being escaped.

markupsafe looks `__html__` up on the value itself, so the protocol is checked against the class with
`type_implements` (`renderable_dispatch.py`): a template can build instances, never a class.

This module lives in `tools/` and imports nothing from `core/`, like the other template protocols.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HtmlRenderable(Protocol):
    """A value whose `__html__` returns HTML that is safe to insert as it is.

    Implementations:
    - MarkdownContent: the Markdown converted by the shared parser, raw HTML escaped
    """

    def __html__(self) -> str:
        """The HTML to insert as it is, which HTML autoescaping will not escape again."""
        ...
