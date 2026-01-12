"""Protocol for types that can render with tagging support.

This module defines the TagRenderable protocol, which enables the `tag`
Jinja2 filter to work with any type that implements the `render_for_tag` method
and `default_tag_name` property.

The protocol uses `@runtime_checkable` to allow isinstance() checks at runtime,
which enables the filter to determine if a value can provide its own rendering
and tag name without importing concrete types (avoiding circular imports).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TagRenderable(Protocol):
    """Protocol for types that can provide rendering and default tag name.

    Types implementing this protocol can be used with the `tag` filter.
    The filter will call `render_for_tag()` to get the plain text content,
    and `default_tag_name` to get the suggested tag name.

    Implementations:
    - StuffArtefact: renders via rendered_plain(), uses stuff_name as default tag
    """

    def render_for_tag(self) -> str:
        """Render content as plain string for tagging.

        Returns:
            Plain text representation of the content.
        """
        ...

    @property
    def default_tag_name(self) -> str:
        """Get the default tag name for this content.

        Returns:
            Suggested tag name (e.g., stuff_name for StuffArtefact).
        """
        ...
