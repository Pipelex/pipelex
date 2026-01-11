"""Jinja2 handlers for Stuff types - registered during application boot.

This module provides the actual implementations of type-checking and rendering
functions that are registered with the Jinja2Registry. These functions know
about the high-level Stuff types (StuffArtefact, ImageContent, etc.) and
provide the isinstance() checks that the low-level Jinja2 filters need.
"""

from typing import Any, cast

from pipelex.cogt.templating.text_format import TextFormat
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_artefact import StuffArtefact
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_registry import get_jinja2_registry


def can_contain_images(value: Any) -> bool:
    """Check if a value is a type that with_images can extract images from.

    Returns True for types that can potentially contain images:
    - StuffArtefact (wraps content that may have images)
    - ImageContent (is an image itself)
    - list/tuple (may contain images or structs with images)
    - ListContent (items may contain images)
    - StuffContent (may have nested image fields)

    Returns False for types that cannot contain images (e.g., plain strings,
    numbers, etc.) which would result from a previous filter already converting
    to string.
    """
    if isinstance(value, StuffArtefact):
        return True
    if isinstance(value, ImageContent):
        return True
    if isinstance(value, (list, tuple)):
        return True
    if isinstance(value, ListContent):
        return True
    return isinstance(value, StuffContent) and not isinstance(value, (ImageContent, ListContent))


def render_value_with_images(value: Any, registry: ImageRegistry, text_format: TextFormat) -> str:
    """Recursively render a value with image tokens inline.

    Args:
        value: The value to render (could be ImageContent, StuffContent, list, etc.)
        registry: The image registry to track images
        text_format: The text format to use for rendering

    Returns:
        String representation with [Image N] tokens where images appear
    """
    # Handle StuffArtefact first - extract the actual content
    if isinstance(value, StuffArtefact):
        actual_content = value.root.get("_content")
        if actual_content is not None:
            return render_value_with_images(actual_content, registry, text_format)
        # Fallback if no _content (shouldn't happen)
        return str(value)

    # Handle ImageContent directly
    if isinstance(value, ImageContent):
        image_num = registry.register_image(value)
        return f"[Image {image_num}]"

    # Handle lists/tuples
    if isinstance(value, (list, tuple)):
        list_value = cast("list[Any] | tuple[Any]", value)
        parts: list[str] = []
        value_list: list[Any] = list(list_value)
        for list_item in value_list:
            rendered = render_value_with_images(list_item, registry, text_format)
            if rendered:
                parts.append(rendered)
        return "\n".join(parts)

    # Handle ListContent
    if isinstance(value, ListContent):
        list_content_value = cast("ListContent[Any]", value)
        parts = []
        list_items: list[Any] = list(list_content_value.items)
        for list_item in list_items:
            rendered = render_value_with_images(list_item, registry, text_format)
            if rendered:
                parts.append(rendered)
        return "\n".join(parts)

    # Handle StuffContent with nested fields (but not ImageContent or ListContent which are subclasses)
    if isinstance(value, StuffContent) and not isinstance(value, (ImageContent, ListContent)):
        parts = []
        model_fields = type(value).model_fields
        field_names: list[str] = list(model_fields.keys())
        for field_name in field_names:
            field_value = getattr(value, field_name)
            if field_value is None:
                continue
            # Recurse into field value
            rendered = render_value_with_images(field_value, registry, text_format)
            if rendered:
                parts.append(f"{field_name}: {rendered}")
        return "\n".join(parts)

    # For other values, use text_format rendering if available
    if hasattr(value, "rendered_str"):  # pyright: ignore[reportUnknownArgumentType]
        return value.rendered_str(text_format=text_format)  # type: ignore[no-any-return]
    if hasattr(value, text_format.render_method_name):  # pyright: ignore[reportUnknownArgumentType]
        render_method = getattr(value, text_format.render_method_name)  # pyright: ignore[reportUnknownArgumentType]
        return render_method()  # type: ignore[no-any-return]

    # Fallback to str
    return str(value)  # type: ignore[no-any-return]


def register_jinja2_stuff_handlers() -> None:
    """Register the Stuff type handlers with the Jinja2Registry.

    This function should be called during application boot (in Pipelex.setup()).
    """
    jinja2_registry = get_jinja2_registry()
    jinja2_registry.register_can_contain_images(can_contain_images)
    jinja2_registry.register_render_value_with_images(render_value_with_images)
