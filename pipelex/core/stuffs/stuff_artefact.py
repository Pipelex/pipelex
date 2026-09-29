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

Templates render under the Pipelex sandbox (`pipelex/tools/jinja2/jinja2_sandbox.py`), which lets a
template read public data and call methods of plain values only. StuffArtefact declares its template
surface: the dict-like accessors a template may call, and the metadata fields it may read although
they start with an underscore.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, Iterator

from typing_extensions import override

from pipelex.core.stuffs.list_content import ListContent
from pipelex.tools.jinja2.image_renderable import ImageRenderable
from pipelex.tools.jinja2.template_surface import TemplateSurface
from pipelex.tools.templating.text_format import TextFormat

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff import Stuff
    from pipelex.core.stuffs.stuff_content import StuffContent
    from pipelex.tools.jinja2.image_registry import ImageRegistry


class BaseStuffArtefactField(StrEnum):
    """Reserved field names for StuffArtefact metadata.

    These fields are accessible via the artefact but are not part of the
    content model. They use underscore prefixes to avoid conflicts with
    user-defined content fields. They are scalars, and they are the only
    underscore-prefixed names a template may read on an artefact: the raw
    content object is deliberately not among them.
    """

    STUFF_NAME = "_stuff_name"
    CONTENT_CLASS = "_content_class"
    CONCEPT_CODE = "_concept_code"
    STUFF_CODE = "_stuff_code"


_METADATA_FIELD_NAMES = frozenset(field.value for field in BaseStuffArtefactField)


def _public_extra_fields(*, content: StuffContent) -> dict[str, Any]:
    """The public extra fields of a model that allows extras, which is where `CompositeContent` holds its parts.

    They are read from `model_extra` and never with getattr, so a part named like a pydantic attribute
    (`model_dump`, `model_extra`) resolves to the part and not to the attribute.
    """
    return {name: value for name, value in (content.model_extra or {}).items() if not name.startswith("_")}


def _content_field_names(*, content: StuffContent) -> list[str]:
    """The content fields a template reads: the declared ones, then the public extra fields."""
    declared_names: list[str] = list(type(content).model_fields)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    return [*declared_names, *_public_extra_fields(content=content)]


def _get_template_value(*, stuff: Stuff, key: str) -> Any:
    """Return what a template reads under `key`: a content field, else a metadata field.

    This is the whole of what a string key resolves to, with a dot, with brackets or through `get`:
    anything else (the wrapped Stuff, the artefact's own methods) raises KeyError.
    """
    content = stuff.content
    if key in type(content).model_fields:
        return getattr(content, key)
    extra_fields = _public_extra_fields(content=content)
    if key in extra_fields:
        return extra_fields[key]
    match key:
        case BaseStuffArtefactField.STUFF_NAME:
            return stuff.stuff_name
        case BaseStuffArtefactField.CONTENT_CLASS:
            return content.__class__.__name__
        case BaseStuffArtefactField.CONCEPT_CODE:
            return stuff.concept.code
        case BaseStuffArtefactField.STUFF_CODE:
            return stuff.stuff_code
        case _:
            raise KeyError(key)


# Attributes that should NOT be intercepted and delegated to content
_PASSTHROUGH_ATTRS = frozenset(
    {
        # Core object attributes
        "_stuff",
        "__class__",
        "__dict__",
        "__doc__",
        # Methods that must remain accessible (TagRenderable protocol)
        "render_for_tag_async",
        "default_tag_name",
        # Methods that must remain accessible (ImageRenderable protocol)
        "render_with_images",
        # Methods that must remain accessible (TextFormatRenderable protocol)
        "rendered_for_template_async",
        # Dict-like methods for template iteration
        "iter_keys",
        "iter_items",
        "iter_values",
        "get",
        # Magic methods
        "__getitem__",
        "__contains__",
        "__iter__",
        "__len__",
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
        - TagRenderable protocol (render_for_tag_async, default_tag_name)
        - TextFormatRenderable protocol (rendered_for_template_async)
        - ImageRenderable protocol (render_with_images)

    Attributes:
        _stuff: The underlying Stuff object being wrapped.
    """

    __slots__ = ("_stuff",)

    # What a template may do beyond reading public data: call the dict-like accessors, and read the
    # metadata fields although they start with an underscore.
    __template_surface__ = TemplateSurface(
        callable_names=frozenset({"get", "iter_keys", "iter_items", "iter_values"}),
        private_names=_METADATA_FIELD_NAMES,
    )

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

        # Content fields first (the most common access pattern in templates), then metadata fields,
        # then normal attribute lookup for methods etc. Use object.__getattribute__ to avoid recursion.
        stuff = object.__getattribute__(self, "_stuff")
        try:
            return _get_template_value(stuff=stuff, key=key)
        except KeyError:
            return object.__getattribute__(self, key)

    def __getitem__(self, key: str | int | slice) -> Any:
        """Support bracket notation: stuff['field'] or stuff[0] for list indexing.

        A string key resolves to a content field or a metadata field only, never to the artefact's
        own attributes: the template sandbox checks a bracketed name only when `obj[key]` fails.

        Args:
            key: String key for field access, or int/slice for list content indexing.

        Returns:
            The value for the key, or the indexed item(s) from list content.

        Raises:
            KeyError: If string key is not a content field or a metadata field.
            TypeError: If int/slice indexing on non-indexable content.
        """
        if isinstance(key, str):
            return _get_template_value(stuff=self._stuff, key=key)
        # Integer or slice - delegate to ListContent
        content = self._stuff.content
        if isinstance(content, ListContent):
            return content[key]  # pyright: ignore[reportUnknownVariableType]
        content_type = type(content).__name__
        msg = f"'{content_type}' content does not support indexing."
        raise TypeError(msg)

    def get(self, key: str, *, default: Any = None) -> Any:
        """Dict-like get method, resolving the same keys as bracket access.

        Args:
            key: The key to access.
            default: Value to return if key not found.

        Returns:
            The value for the key, or default if it is neither a content field nor a metadata field.
        """
        try:
            return _get_template_value(stuff=self._stuff, key=key)
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        """Support 'in' operator.

        Args:
            key: The key to check.

        Returns:
            True if the key is accessible, False otherwise.
        """
        # Check content fields
        if key in _content_field_names(content=self._stuff.content):
            return True

        # Check metadata fields
        return key in _METADATA_FIELD_NAMES

    def __iter__(self) -> Iterator[Any]:
        """Enable direct iteration when content is ListContent.

        Enables: {% for item in my_list_stuff %} in Jinja2 templates.

        Note: Only ListContent supports this. Other content types inherit
        BaseModel.__iter__ which iterates over field names, not items.

        Returns:
            Iterator over the content's items.

        Raises:
            TypeError: If content is not ListContent.
        """
        content = self._stuff.content
        if isinstance(content, ListContent):
            return iter(content)  # type: ignore[call-overload]
        content_type = type(content).__name__
        msg = f"'{content_type}' content is not iterable. Only ListContent supports direct iteration."
        raise TypeError(msg)

    def __len__(self) -> int:
        """Return length when content is ListContent.

        Returns:
            Length of the content (number of items in ListContent).

        Raises:
            TypeError: If content is not ListContent.
        """
        content = self._stuff.content
        if isinstance(content, ListContent):
            return len(content)
        content_type = type(content).__name__
        msg = f"'{content_type}' content does not support len()."
        raise TypeError(msg)

    def __bool__(self) -> bool:
        """A present artefact is truthy; a ListContent artefact follows list emptiness.

        Load-bearing for the optionals guard idiom: without `__bool__`, Jinja2's truth test
        (`{% if var %}`, `@?var`'s expansion) falls through to `__len__`, which raises for
        non-list content — the D7-blessed guard would crash on a PRESENT singular value.
        An empty list is falsy on purpose (D4: `[]`-emptiness is the absence story for plurals).
        """
        content = self._stuff.content
        if isinstance(content, ListContent):
            return len(content) > 0
        return True

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
        yield from _content_field_names(content=self._stuff.content)
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

    async def render_for_tag_async(self) -> str:
        """Render content as plain string for tagging.

        Returns:
            Plain text representation via rendered_for_template_async(PLAIN).
        """
        result: str = await self._stuff.content.rendered_for_template_async(  # pyright: ignore[reportUnknownVariableType]
            text_format=TextFormat.PLAIN
        )
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

    async def rendered_for_template_async(self, *, text_format: TextFormat) -> str:
        """Render content for templates in the specified text format.

        Args:
            text_format: The format for rendering.

        Returns:
            The rendered string.
        """
        result: str = await self._stuff.content.rendered_for_template_async(text_format=text_format)  # pyright: ignore[reportUnknownVariableType]
        return result  # pyright: ignore[reportUnknownVariableType]

    # -------------------------------------------------------------------------
    # ImageRenderable protocol implementation
    # -------------------------------------------------------------------------

    def render_with_images(
        self,
        *,
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
        return content.render_with_images(registry=registry, text_format=text_format)

    @override
    def __str__(self) -> str:
        """Return plain text content for string conversion."""
        result: str = self._stuff.content.rendered_plain()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return result  # pyright: ignore[reportUnknownVariableType]

    @override
    def __repr__(self) -> str:
        """Return string representation."""
        return f"StuffArtefact({self._stuff.stuff_name or 'unnamed'})"


def unwrap_stuff_artefact(*, artefact: StuffArtefact) -> Stuff:
    """Return the Stuff an artefact wraps, for Python code.

    This is a function rather than a property on purpose: every public attribute of an artefact is
    readable from a template, and the wrapped Stuff, with its raw content object, is not template data.
    """
    # The one read of the slot from outside the class, which is the point: the class exposes no accessor.
    return artefact._stuff  # type: ignore[no-any-return]  # ruff: ignore[private-member-access]
