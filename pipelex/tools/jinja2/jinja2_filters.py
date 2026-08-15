import re
from enum import StrEnum
from typing import Any

from jinja2 import pass_context
from jinja2.runtime import Context, Undefined

from pipelex.tools.jinja2.exceptions import Jinja2ContextError
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.tag_renderable import TagRenderable
from pipelex.tools.jinja2.text_format_renderable import TextFormatRenderable
from pipelex.tools.templating.templating_style import TagStyle
from pipelex.tools.templating.text_format import TextFormat

########################################################################################
# Jinja2 filters
########################################################################################

ALLOWED_FILTERS = ["tag", "format", "default", "escape_script_tag", "with_images"]


def require_templating_style_value(*, context: Context, jinja2_context_key: Jinja2ContextKey) -> str:
    """Read a templating-style key out of the render context, or fail loudly.

    Deliberately without a fallback: every prompt-rendering entry point resolves a templating style
    before rendering, so a missing key means the render was set up without one. A default here would
    silently change the shape of a prompt — which is exactly how a triple-backtick style used to
    reach prompts nobody had chosen it for.
    """
    value = context.get(jinja2_context_key)
    if value is None:
        msg = (
            f"No templating style in the render context: '{jinja2_context_key}' is missing. "
            "The tag, format and with_images filters have no default to fall back on — the caller "
            "must resolve a templating style and pass it to the render call."
        )
        raise Jinja2ContextError(msg)
    return str(value)


# Filter to format some Stuff or any object with the appropriate text formatting methods
@pass_context
async def text_format(context: Context, value: Any, text_format: TextFormat | str | None = None) -> Any:
    # Check if this is a registered image - use placeholder instead of rendering as text
    # This handles $page.page_view syntax where the format filter would otherwise call rendered_plain() → URL
    registry = context.get(Jinja2ContextKey.IMAGE_REGISTRY)
    if isinstance(registry, ImageRegistry) and hasattr(value, "url"):
        placeholder = registry.get_image_placeholder(value)
        if placeholder is not None:
            return placeholder

    applied_text_format: TextFormat
    if text_format:
        # A template can name its own format — `{{ x | format("markdown") }}` — and Jinja2 hands the
        # argument over as a raw string, so both that and a `TextFormat` member normalise here. An
        # unknown name is a template error, reported as one rather than as a bare `ValueError`.
        try:
            applied_text_format = TextFormat(text_format)
        except ValueError as exc:
            msg = f"Invalid text format: '{text_format}'"
            raise Jinja2ContextError(msg) from exc
    else:
        applied_text_format = TextFormat(require_templating_style_value(context=context, jinja2_context_key=Jinja2ContextKey.TEXT_FORMAT))

    # Protocol-based rendering
    if isinstance(value, TextFormatRenderable):
        return await value.rendered_for_template_async(text_format=applied_text_format)
    if isinstance(value, StrEnum):
        return value.value
    return value


# Filter to wrap content in tags according to the tag style
@pass_context
async def tag(context: Context, value: Any, tag_name: str | None = None) -> str:
    """Filter to wrap content in tags.

    Usage in templates:
        {{ variable | tag }}                # Uses default tag name from TagRenderable
        {{ variable | tag("custom_name") }} # Uses custom tag name
        {{ variable | format | tag }}       # Format first, then tag

    Args:
        context: Jinja2 context (passed automatically via @pass_context).
        value: The value to tag. If it implements TagRenderable, uses render_for_tag_async().
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
            rendered_value = await value.render_for_tag_async()
            if final_tag_name is None:
                final_tag_name = value.default_tag_name
        else:
            rendered_value = str(value)
    elif isinstance(value, TagRenderable):
        rendered_value = await value.render_for_tag_async()
        if final_tag_name is None:
            final_tag_name = value.default_tag_name
    else:
        rendered_value = str(value)

    return apply_tag_style(context=context, value=rendered_value, tag_name=final_tag_name)


def apply_tag_style(*, context: Context, value: str, tag_name: str | None = None) -> str:
    """Apply tag style wrapping to content.

    Args:
        context: Jinja2 context containing TAG_STYLE.
        value: The string content to wrap in tags.
        tag_name: Optional tag name. If None, behavior depends on tag style.

    Returns:
        Content wrapped in tags according to the style.
    """
    tag_style = TagStyle(require_templating_style_value(context=context, jinja2_context_key=Jinja2ContextKey.TAG_STYLE))

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
