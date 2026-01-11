"""Jinja2 filter for extracting and rendering images from structures."""

from typing import Any

from jinja2 import pass_context
from jinja2.runtime import Context, Undefined

from pipelex.cogt.templating.text_format import TextFormat
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_errors import Jinja2ContextError
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.jinja2_registry import get_jinja2_registry


@pass_context
def with_images(context: Context, value: Any, _: Any = None) -> str:
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

    Returns:
        Text representation with image tokens inline
    """
    if isinstance(value, Undefined):
        msg = "Cannot use with_images filter on undefined value"
        raise Jinja2ContextError(msg)

    # Get the registry for type checking and rendering
    jinja2_registry = get_jinja2_registry()

    # Check if the value is a type that can contain images
    if not jinja2_registry.can_contain_images(value):
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

    # Render the value with images using the registered function
    return jinja2_registry.render_value_with_images(value, registry, text_format)
