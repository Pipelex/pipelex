"""Jinja2 filter for extracting and rendering images from structures.

This module uses duck typing to avoid circular imports with core.stuffs modules.
Images are identified by having a 'url' attribute and class name 'ImageContent'.
"""

from typing import TYPE_CHECKING, Any

from jinja2 import pass_context
from jinja2.runtime import Context, Undefined

from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_errors import Jinja2ContextError
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey

if TYPE_CHECKING:
    from pipelex.cogt.templating.templating_style import TextFormat


def _is_image_content(value: Any) -> bool:
    """Check if a value is an ImageContent using duck typing.

    We use duck typing to avoid importing ImageContent, which would cause circular imports.
    An ImageContent is identified by:
    - Having a 'url' attribute
    - Class name is 'ImageContent'
    """
    return hasattr(value, "url") and type(value).__name__ == "ImageContent"


def _is_list_content(value: Any) -> bool:
    """Check if a value is a ListContent using duck typing.

    ListContent is identified by having an 'items' attribute and class name 'ListContent'.
    """
    return hasattr(value, "items") and type(value).__name__ == "ListContent"


def _is_stuff_content(value: Any) -> bool:
    """Check if a value is a StuffContent using duck typing.

    StuffContent is a Pydantic model, so it has 'model_fields' attribute.
    We check that it's NOT an ImageContent (which is also a StuffContent).
    We also exclude StuffArtefact (which wraps content in a dict-like structure).
    """
    if not hasattr(value, "model_fields"):
        return False
    if _is_image_content(value) or _is_list_content(value):
        return False
    # Exclude StuffArtefact (RootModel with _content key)
    return not _is_stuff_artefact(value)


def _is_stuff_artefact(value: Any) -> bool:
    """Check if a value is a StuffArtefact using duck typing.

    StuffArtefact is identified by:
    - Being a RootModel (has 'root' attribute that is a dict)
    - Having a '_content' key in the root dict
    - Class name is 'StuffArtefact'
    """
    if type(value).__name__ != "StuffArtefact":
        return False
    if not hasattr(value, "root"):
        return False
    root = getattr(value, "root", None)
    return isinstance(root, dict) and "_content" in root


def _can_contain_images(value: Any) -> bool:
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
    if _is_stuff_artefact(value):
        return True
    if _is_image_content(value):
        return True
    if isinstance(value, (list, tuple)):
        return True
    if _is_list_content(value):
        return True
    return _is_stuff_content(value)


def _render_value_with_images(value: Any, registry: ImageRegistry, text_format: "TextFormat") -> str:
    """Recursively render a value with image tokens inline.

    Args:
        value: The value to render (could be ImageContent, StuffContent, list, etc.)
        registry: The image registry to track images
        text_format: The text format to use for rendering

    Returns:
        String representation with [Image N] tokens where images appear
    """
    # Handle StuffArtefact first - extract the actual content
    if _is_stuff_artefact(value):
        actual_content = value.root.get("_content")  # pyright: ignore[reportUnknownMemberType]
        if actual_content is not None:
            return _render_value_with_images(actual_content, registry, text_format)
        # Fallback if no _content (shouldn't happen)
        return str(value)

    # Handle ImageContent directly (using duck typing)
    if _is_image_content(value):
        image_num = registry.register_image(value)
        return f"[Image {image_num}]"

    # Handle lists/tuples
    if isinstance(value, (list, tuple)):
        parts: list[str] = []
        value_list: list[Any] = list(value)  # pyright: ignore[reportUnknownArgumentType]
        for list_item in value_list:
            rendered = _render_value_with_images(list_item, registry, text_format)
            if rendered:
                parts.append(rendered)
        return "\n".join(parts)

    # Handle ListContent (using duck typing)
    if _is_list_content(value):
        parts = []
        list_items: list[Any] = list(value.items)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        for list_item in list_items:
            rendered = _render_value_with_images(list_item, registry, text_format)
            if rendered:
                parts.append(rendered)
        return "\n".join(parts)

    # Handle StuffContent with nested fields (using duck typing)
    if _is_stuff_content(value):
        parts = []
        model_fields = getattr(type(value), "model_fields", {})  # pyright: ignore[reportUnknownArgumentType]
        field_names: list[str] = list(model_fields.keys())
        for field_name in field_names:
            field_value = getattr(value, field_name)
            if field_value is None:
                continue
            # Recurse into field value
            rendered = _render_value_with_images(field_value, registry, text_format)
            if rendered:
                parts.append(f"{field_name}: {rendered}")
        return "\n".join(parts)

    # For other values, use text_format rendering if available
    if hasattr(value, "rendered_str"):
        return value.rendered_str(text_format=text_format)  # type: ignore[no-any-return]
    if hasattr(value, text_format.render_method_name):
        render_method = getattr(value, text_format.render_method_name)
        return render_method()  # type: ignore[no-any-return]

    # Fallback to str
    return str(value)


@pass_context
def with_images(context: Context, value: Any, _unused: Any = None) -> str:
    """Filter to extract nested images from a structure and render with image tokens.

    This filter:
    1. Gets or creates an image registry from context
    2. Walks the structure to find all ImageContent objects
    3. Registers each image and assigns a number
    4. Returns the text representation with [Image N] tokens inline

    Usage in templates:
        {{ document | with_images }}

    Args:
        context: Jinja2 context (passed automatically)
        value: The value to render with images
        _unused: Unused parameter for signature compatibility

    Returns:
        Text representation with image tokens inline
    """
    # Lazy import to avoid circular imports
    from pipelex.cogt.templating.templating_style import TextFormat  # noqa: PLC0415

    if isinstance(value, Undefined):
        msg = "Cannot use with_images filter on undefined value"
        raise Jinja2ContextError(msg)

    # Check if the value is a type that can contain images
    if not _can_contain_images(value):
        msg = (
            f"The with_images filter received a {type(value).__name__} which cannot contain images. "
            "This filter requires structured data (StuffContent, ListContent, ImageContent, list, etc.). "
            "If chaining filters, ensure with_images receives structured data "
            "(e.g., use '| with_images | tag' not '| tag | with_images')."
        )
        raise Jinja2ContextError(msg)

    # Get or create the image registry from context
    registry = context.get(Jinja2ContextKey.IMAGE_REGISTRY)
    if registry is None:
        registry = ImageRegistry()
        # Note: We can't modify context directly in Jinja2, so the registry
        # must be pre-set in the context by the caller. If not present,
        # we create a temporary one (images won't persist across expressions)
    if not isinstance(registry, ImageRegistry):
        msg = f"Expected ImageRegistry in context, got {type(registry)}"
        raise Jinja2ContextError(msg)

    # Get text format from context
    text_format_str = context.get(Jinja2ContextKey.TEXT_FORMAT, default=TextFormat.PLAIN)
    text_format = TextFormat(text_format_str)

    # Render the value with images
    return _render_value_with_images(value, registry, text_format)
