"""Jinja2 filter for extracting and rendering images from structures."""

from typing import Any

from jinja2 import pass_context
from jinja2.runtime import Context, Undefined

from pipelex.cogt.templating.text_format import TextFormat
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.image_renderable import ImageRenderable
from pipelex.tools.jinja2.jinja2_errors import Jinja2ContextError
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey


@pass_context
def with_images(context: Context, value: Any, _: Any = None) -> str:
    """Filter to extract nested images from a structure and render with image tokens.

    This filter uses the ImageRenderable protocol to render content with image
    extraction. Types implementing this protocol (StuffContent, StuffArtefact,
    etc.) can render themselves with image tokens.

    This filter:
    1. Gets or creates an image registry from context
    2. Calls render_with_images() on the value (if it implements ImageRenderable)
    3. Returns the text representation with [Image N] tokens inline

    Usage in templates:
        {{ document | with_images }}

    Args:
        context: Jinja2 context (passed automatically)
        value: The value to render with images (must implement ImageRenderable)

    Returns:
        Text representation with image tokens inline

    Raises:
        Jinja2ContextError: If value is undefined or doesn't implement ImageRenderable
    """
    if isinstance(value, Undefined):
        msg = "Cannot use with_images filter on undefined value"
        raise Jinja2ContextError(msg)

    # Get or create the image registry from context
    registry = context.get(Jinja2ContextKey.IMAGE_REGISTRY)
    if registry is None:
        registry = ImageRegistry()
        # Note: We can't modify context directly in Jinja2, so the registry
        # must be pre-set in the context by the caller. If not present,
        # we create a temporary one (images won't persist across expressions)
    if not isinstance(registry, ImageRegistry):
        msg = f"Expected ImageRegistry in context, got {type(registry).__name__}"
        raise Jinja2ContextError(msg)

    # Get text format from context
    text_format_str = context.get(Jinja2ContextKey.TEXT_FORMAT, default=TextFormat.PLAIN)
    text_format = TextFormat(text_format_str)

    # Protocol-based rendering
    if isinstance(value, ImageRenderable):
        return value.render_with_images(registry, text_format)

    # Handle plain lists/tuples (structural types that may contain ImageRenderable items)
    if isinstance(value, (list, tuple)):
        return _render_sequence_with_images(value, registry, text_format)  # pyright: ignore[reportUnknownArgumentType]

    # Type cannot be rendered with images
    msg = (
        f"The with_images filter received a {type(value).__name__} which does not "
        f"implement the ImageRenderable protocol. This filter requires StuffArtefact, "
        f"StuffContent subclasses, or lists containing such types. "
        f"Did you accidentally apply another filter first that converted to string?"
    )
    raise Jinja2ContextError(msg)


def _render_sequence_with_images(
    sequence: list[Any] | tuple[Any, ...],
    registry: ImageRegistry,
    text_format: TextFormat,
) -> str:
    """Render a sequence with image extraction.

    Args:
        sequence: List or tuple that may contain ImageRenderable items
        registry: ImageRegistry to track discovered images
        text_format: Format for rendering text content

    Returns:
        String with [Image N] tokens where images appear
    """
    parts: list[str] = []
    for item in sequence:
        if isinstance(item, ImageRenderable):
            rendered = item.render_with_images(registry, text_format)
        else:
            rendered = str(item)
        if rendered:
            parts.append(rendered)
    return "\n".join(parts)
