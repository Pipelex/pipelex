"""StuffArtefact - Thin adapter providing Jinja2-compatible access to Stuff.

This module provides StuffArtefact, a lightweight wrapper around Stuff objects
that enables them to be used in Jinja2 templates. Unlike the previous implementation
which flattened Stuff into a dictionary, this version delegates attribute access
to the underlying Stuff and StuffContent objects.

Example template usage:
    {{ my_stuff.field_name }}       # Access content field
    {{ my_stuff._stuff_name }}      # Access metadata
    {{ my_stuff | tag }}            # Use tag filter
    {{ my_stuff | with_images }}    # Use with_images filter
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator

from typing_extensions import override

from pipelex.tools.jinja2.image_renderable import ImageRenderable
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.cogt.templating.text_format import TextFormat
    from pipelex.core.stuffs.stuff import Stuff
    from pipelex.tools.jinja2.image_registry import ImageRegistry


class BaseStuffArtefactField(StrEnum):
    """Reserved field names for StuffArtefact metadata.

    These fields are accessible via the artefact but are not part of the
    content model. They use underscore prefixes to avoid conflicts with
    user-defined content fields.
    """

    STUFF_NAME = "_stuff_name"
    CONTENT_CLASS = "_content_class"
    CONCEPT_CODE = "_concept_code"
    STUFF_CODE = "_stuff_code"
    CONTENT = "_content"


# Attributes that should NOT be intercepted and delegated to content
_PASSTHROUGH_ATTRS = frozenset(
    {
        # Core object attributes
        "_stuff",
        "__class__",
        "__dict__",
        "__doc__",
        # Methods that must remain accessible (TagRenderable protocol)
        "render_for_tag",
        "default_tag_name",
        # Methods that must remain accessible (ImageRenderable protocol)
        "render_with_images",
        # Other methods
        "rendered_str_async",
        "stuff",
        # Dict-like methods for template iteration
        "iter_keys",
        "iter_items",
        "iter_values",
        "get",
        # Magic methods
        "__getitem__",
        "__contains__",
        "__repr__",
        "__str__",
        "__init__",
        "__getattribute__",
    }
)


class StuffArtefact:
    """Thin adapter providing Jinja2-compatible access to Stuff.

    Enables templates to access content fields via dot notation:
        {{ my_stuff.field_name }}
        {{ my_stuff._stuff_name }}
        {{ my_stuff | tag }}
        {{ my_stuff | format }}
        {{ my_stuff | with_images }}

    Unlike the previous implementation, this does NOT flatten data.
    It delegates to the underlying Stuff and StuffContent on access.

    IMPORTANT: Content fields take priority over class methods. This means
    if your content has a field named 'items', accessing `artefact.items`
    will return that field value, not the dict-like iteration method.
    Use `artefact.iter_items()` for explicit dict-like iteration.

    Implements:
        - TagRenderable protocol (render_for_tag, default_tag_name)
        - TextFormatRenderable protocol (rendered_str_async)
        - ImageRenderable protocol (render_with_images)

    Attributes:
        _stuff: The underlying Stuff object being wrapped.
    """

    __slots__ = ("_stuff",)

    def __init__(self, stuff: Stuff) -> None:
        """Initialize the artefact with a Stuff object.

        Args:
            stuff: The Stuff object to wrap.
        """
        object.__setattr__(self, "_stuff", stuff)

    # -------------------------------------------------------------------------
    # Attribute access for Jinja2 templates
    # -------------------------------------------------------------------------

    @override
    def __getattribute__(self, key: str) -> Any:
        """Provide attribute access prioritizing content fields.

        Priority:
        1. Passthrough attributes (_stuff, methods, magic methods)
        2. Content fields (from stuff.content)
        3. Metadata fields (_stuff_name, _content_class, etc.)
        4. Fall back to normal attribute lookup

        Args:
            key: The attribute name to access.

        Returns:
            The attribute value.

        Raises:
            AttributeError: If the attribute is not found.
        """
        # Always allow access to passthrough attributes
        if key in _PASSTHROUGH_ATTRS or key.startswith("__"):
            return object.__getattribute__(self, key)

        # Get the underlying stuff - use object.__getattribute__ to avoid recursion
        stuff = object.__getattribute__(self, "_stuff")
        content = stuff.content

        # Check content fields (most common access pattern in templates)
        content_fields = type(content).model_fields  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if key in content_fields:
            return getattr(content, key)

        # Metadata accessors (underscore-prefixed)
        match key:
            case "_stuff_name":
                return stuff.stuff_name
            case "_content_class":
                return content.__class__.__name__
            case "_concept_code":
                return stuff.concept.code
            case "_stuff_code":
                return stuff.stuff_code
            case "_content":
                return content
            case _:
                # Fall back to normal attribute lookup for methods etc.
                return object.__getattribute__(self, key)

    def __getitem__(self, key: str) -> Any:
        """Support bracket notation: stuff['field'].

        Args:
            key: The key to access.

        Returns:
            The value for the key.

        Raises:
            KeyError: If the key is not found.
        """
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like get method.

        Args:
            key: The key to access.
            default: Value to return if key not found.

        Returns:
            The value for the key, or default if not found.
        """
        try:
            return getattr(self, key)
        except AttributeError:
            return default

    def __contains__(self, key: str) -> bool:
        """Support 'in' operator.

        Args:
            key: The key to check.

        Returns:
            True if the key is accessible, False otherwise.
        """
        content_fields = type(self._stuff.content).model_fields  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

        # Check content fields
        if key in content_fields:
            return True

        # Check metadata fields
        return key in {"_stuff_name", "_content_class", "_concept_code", "_stuff_code", "_content"}

    # -------------------------------------------------------------------------
    # Dict-like iteration (for template compatibility)
    # Named with 'iter_' prefix to avoid conflicts with content fields
    # -------------------------------------------------------------------------

    def iter_keys(self) -> Iterator[str]:
        """Yield accessible keys (content fields + metadata).

        Note: Named 'iter_keys' to avoid conflicts with content fields named 'keys'.

        Yields:
            Field names from content, followed by metadata field names.
        """
        # Content fields (use self._stuff since it's in _PASSTHROUGH_ATTRS)
        yield from type(self._stuff.content).model_fields  # pyright: ignore[reportUnknownMemberType]
        # Metadata fields
        for field in BaseStuffArtefactField:
            yield field.value

    def iter_items(self) -> Iterator[tuple[str, Any]]:
        """Yield (key, value) pairs.

        Note: Named 'iter_items' to avoid conflicts with content fields named 'items'.

        Yields:
            Tuples of (key, value) for all accessible fields.
        """
        for key in self.iter_keys():
            yield key, self.get(key)

    def iter_values(self) -> Iterator[Any]:
        """Yield values.

        Note: Named 'iter_values' to avoid conflicts with content fields named 'values'.

        Yields:
            Values for all accessible fields.
        """
        for key in self.iter_keys():
            yield self.get(key)

    # -------------------------------------------------------------------------
    # TagRenderable protocol implementation
    # -------------------------------------------------------------------------

    def render_for_tag(self) -> str:
        """Render content as plain string for tagging.

        Returns:
            Plain text representation via rendered_plain().
        """
        result: str = self._stuff.content.rendered_plain()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return result  # pyright: ignore[reportUnknownVariableType]

    @property
    def default_tag_name(self) -> str:
        """Get the default tag name (stuff_name).

        Returns:
            The stuff_name of the wrapped Stuff object.
        """
        return self._stuff.stuff_name or "data"  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    # -------------------------------------------------------------------------
    # TextFormatRenderable protocol implementation
    # -------------------------------------------------------------------------

    async def rendered_str_async(self, text_format: TextFormat) -> str:
        """Render content as string.

        Args:
            text_format: The format for rendering.

        Returns:
            The rendered string.
        """
        result: str = await self._stuff.content.rendered_str_async(text_format=text_format)  # pyright: ignore[reportUnknownVariableType]
        return result  # pyright: ignore[reportUnknownVariableType]

    # -------------------------------------------------------------------------
    # ImageRenderable protocol implementation
    # -------------------------------------------------------------------------

    def render_with_images(
        self,
        registry: ImageRegistry,
        text_format: TextFormat,
    ) -> str:
        """Delegate to content's render_with_images.

        Args:
            registry: ImageRegistry to track discovered images.
            text_format: Format for rendering text content.

        Returns:
            String with [Image N] tokens where images appear.

        Raises:
            TypeError: If content type does not implement ImageRenderable.
        """
        content = self._stuff.content
        if not isinstance(content, ImageRenderable):
            msg = (
                f"Content type {type(content).__name__} does not implement ImageRenderable. "
                f"The | with_images filter can only be used with content types that may contain images: "
                f"ImageContent, TextAndImagesContent, ListContent, StructuredContent (and subclasses like PageContent)."
            )
            raise TypeError(msg)
        return content.render_with_images(registry, text_format)

    # -------------------------------------------------------------------------
    # Access to underlying Stuff
    # -------------------------------------------------------------------------

    @property
    def stuff(self) -> Stuff:
        """Access the underlying Stuff object.

        Returns:
            The wrapped Stuff object.
        """
        return self._stuff  # type: ignore[no-any-return]

    @override
    def __repr__(self) -> str:
        """Return string representation."""
        return f"StuffArtefact({self._stuff.stuff_name or 'unnamed'})"
