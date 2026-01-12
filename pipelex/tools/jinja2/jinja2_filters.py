import re
from typing import Any

from jinja2 import pass_context
from jinja2.runtime import Context, Undefined

from pipelex.cogt.templating.templating_style import TagStyle
from pipelex.cogt.templating.text_format import TextFormat
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_errors import Jinja2ContextError
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.tag_renderable import TagRenderable
from pipelex.tools.jinja2.text_format_renderable import TextFormatRenderable
from pipelex.types import StrEnum

########################################################################################
# Jinja2 filters
########################################################################################

ALLOWED_FILTERS = ["tag", "format", "default", "escape_script_tag", "with_images"]


# Filter to format some Stuff or any object with the appropriate text formatting methods
@pass_context
async def text_format(context: Context, value: Any, text_format: TextFormat | None = None) -> Any:
    if text_format:
        if isinstance(text_format, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            applied_text_format = TextFormat(text_format)
        elif isinstance(text_format, TextFormat):  # pyright: ignore[reportUnnecessaryIsInstance]
            applied_text_format = text_format
        else:
            msg = f"Invalid text format: '{text_format}'"
            raise Jinja2ContextError(msg)
    else:
        applied_text_format = TextFormat(context.get(Jinja2ContextKey.TEXT_FORMAT, default=TextFormat.PLAIN))

    # Protocol-based rendering
    if isinstance(value, TextFormatRenderable):
        return await value.rendered_str_async(text_format=applied_text_format)
    if isinstance(value, StrEnum):
        return value.value
    return value


# Filter to wrap content in tags according to the tag style
@pass_context
def tag(context: Context, value: Any, tag_name: str | None = None) -> str:
    """Filter to wrap content in tags.

    Usage in templates:
        {{ variable | tag }}                # Uses default tag name from TagRenderable
        {{ variable | tag("custom_name") }} # Uses custom tag name
        {{ variable | format | tag }}       # Format first, then tag

    Args:
        context: Jinja2 context (passed automatically via @pass_context).
        value: The value to tag. If it implements TagRenderable, uses render_for_tag().
        tag_name: Optional tag name override.

    Returns:
        Tagged content as string.

    Raises:
        Jinja2ContextError: If value is undefined.
    """
    if isinstance(value, Undefined):
        msg = "Cannot use tag filter on undefined value"
        if tag_name:
            msg = f"Cannot use tag filter on undefined value with tag_name '{tag_name}'"
        raise Jinja2ContextError(msg)

    # Protocol-based rendering
    rendered_value: str
    final_tag_name: str | None = tag_name

    # Check if this is a registered image - use placeholder as content
    # This handles nested image paths like page.page_view where extra_params
    # substitution cannot reach due to immutable StuffArtefacts
    registry = context.get(Jinja2ContextKey.IMAGE_REGISTRY)
    if isinstance(registry, ImageRegistry) and hasattr(value, "url"):
        placeholder = registry.get_image_placeholder(value)
        if placeholder is not None:
            rendered_value = placeholder
            # For registered images, use tag_name if provided, otherwise no default
            # (the placeholder already identifies the image)
        elif isinstance(value, TagRenderable):
            rendered_value = value.render_for_tag()
            if final_tag_name is None:
                final_tag_name = value.default_tag_name
        else:
            rendered_value = str(value)
    elif isinstance(value, TagRenderable):
        rendered_value = value.render_for_tag()
        if final_tag_name is None:
            final_tag_name = value.default_tag_name
    else:
        rendered_value = str(value)

    return apply_tag_style(context, rendered_value, final_tag_name)


def apply_tag_style(context: Context, value: str, tag_name: str | None = None) -> str:
    """Apply tag style wrapping to content.

    Args:
        context: Jinja2 context containing TAG_STYLE.
        value: The string content to wrap in tags.
        tag_name: Optional tag name. If None, behavior depends on tag style.

    Returns:
        Content wrapped in tags according to the style.
    """
    tag_style_str = context.get(Jinja2ContextKey.TAG_STYLE)
    tag_style = TagStyle(tag_style_str) if tag_style_str else TagStyle.TICKS

    match tag_style:
        case TagStyle.NO_TAG:
            return value
        case TagStyle.TICKS:
            if tag_name:
                return f"{tag_name}: ```\n{value}\n```"
            return f"```\n{value}\n```"
        case TagStyle.XML:
            effective_tag = tag_name or "data"
            return f"<{effective_tag}>\n{value}\n</{effective_tag}>"
        case TagStyle.SQUARE_BRACKETS:
            effective_tag = tag_name or "data"
            return f"[{effective_tag}]\n{value}\n[/{effective_tag}]"


def escape_script_tag(value: Any) -> Any:
    r"""Escape </script> to prevent script tag injection in JSON embeddings.

    When embedding JSON in <script type="application/json"> tags, a malicious
    string containing </script> could break out of the script block and inject
    arbitrary HTML/JavaScript. HTML tag names are case-insensitive, so this
    function uses case-insensitive matching to catch all variants.

    Args:
        value: The string to escape. Non-string values are returned unchanged.

    Returns:
        The escaped string with </script> (any case) replaced by <\/script>.
    """
    if not isinstance(value, str):
        return value
    return re.sub(r"</script>", r"<\/script>", value, flags=re.IGNORECASE)
