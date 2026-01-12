"""Protocol for types that can render in multiple text formats.

This module defines the TextFormatRenderable protocol, which enables the `text_format`
Jinja2 filter to work with any type that implements the `rendered_str_async` method.

The protocol uses `@runtime_checkable` to allow isinstance() checks at runtime,
which enables the filter to determine if a value can be rendered in different text
formats without importing concrete types (avoiding circular imports).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pipelex.cogt.templating.text_format import TextFormat


@runtime_checkable
class TextFormatRenderable(Protocol):
    """Protocol for types that can render in multiple text formats.

    Types implementing this protocol can be used with the `text_format` filter
    (aliased as `format`). The filter will call `rendered_str_async()` to get
    the rendered string in the specified format.

    Implementations:
    - StuffContent (base): dispatches to format-specific methods
    - StuffArtefact: delegates to underlying content
    """

    async def rendered_str_async(self, text_format: TextFormat) -> str:
        """Render content in the specified text format.

        Args:
            text_format: The format for rendering (plain, markdown, html, json)

        Returns:
            String representation in the requested format.
        """
        ...
