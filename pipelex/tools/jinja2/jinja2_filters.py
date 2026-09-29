from enum import StrEnum
from typing import Any

from jinja2 import pass_context
from jinja2.runtime import Context, Undefined
from markupsafe import Markup

from pipelex.tools.jinja2.exceptions import Jinja2ContextError
from pipelex.tools.jinja2.html_renderable import HtmlRenderable
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.renderable_dispatch import type_implements
from pipelex.tools.jinja2.tag_renderable import TagRenderable
from pipelex.tools.jinja2.text_format_renderable import TextFormatRenderable
from pipelex.tools.markdown.markdown_parser import render_markdown_as_html
from pipelex.tools.templating.templating_style import TagStyle
from pipelex.tools.templating.text_format import TextFormat

########################################################################################
# Jinja2 filters
########################################################################################

ALLOWED_FILTERS = ["tag", "format", "default", "escape_script_tag", "with_images", "markdown"]


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

    named_text_format: TextFormat | None
    if text_format:
        # A template can name its own format — `{{ x | format("markdown") }}` — and Jinja2 hands the
        # argument over as a raw string, so both that and a `TextFormat` member normalise here. An
        # unknown name is a template error, reported as one rather than as a bare `ValueError`.
        try:
            named_text_format = TextFormat(text_format)
        except ValueError as exc:
            msg = f"Invalid text format: '{text_format}'"
            raise Jinja2ContextError(msg) from exc
    else:
        named_text_format = None

    # In an HTML template, a value that knows its own HTML (a Markdown stuff) prints as that HTML unless the
    # template names another format, so `$report` prints what `{{ report }}` prints. The result is inserted
    # unescaped, so the value's class must define `__html__`, which a template cannot forge, and the value must
    # answer it: a `StuffArtefact`'s class defines it for every stuff, and only a content that knows its HTML
    # answers it. `isinstance` cannot ask the second question, since from Python 3.12 it reads a protocol's
    # members off the class too.
    if context.eval_ctx.autoescape and type_implements(value=value, protocol=HtmlRenderable) and hasattr(value, "__html__"):
        match named_text_format:
            case None | TextFormat.HTML:
                return Markup(value)  # ruff: ignore[unsafe-markup-use] - Markup inserts the __html__ the value's class vouches for
            case TextFormat.PLAIN | TextFormat.MARKDOWN | TextFormat.JSON:
                pass

    applied_text_format = named_text_format or TextFormat(
        require_templating_style_value(context=context, jinja2_context_key=Jinja2ContextKey.TEXT_FORMAT)
    )

    # Protocol-based rendering, licensed by the value's type (see renderable_dispatch.py)
    if isinstance(value, TextFormatRenderable) and type_implements(value=value, protocol=TextFormatRenderable):
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

    # Protocol-based rendering, licensed by the value's type (see renderable_dispatch.py)
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
        elif isinstance(value, TagRenderable) and type_implements(value=value, protocol=TagRenderable):
            rendered_value = await value.render_for_tag_async()
            if final_tag_name is None:
                final_tag_name = value.default_tag_name
        else:
            rendered_value = str(value)
    elif isinstance(value, TagRenderable) and type_implements(value=value, protocol=TagRenderable):
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
    r"""Escape every `<` as `\u003c` to prevent script tag injection in JSON embeddings.

    When embedding JSON in a `<script>` block, a string containing `</script>` could break out of the
    block and inject arbitrary HTML/JavaScript. Matching that literal spelling is not enough: the HTML
    script-data end-tag also terminates on `</script` followed by a space, a tab, a slash or `>`, so
    `</script >` and `</script/>` closed the block just as effectively while passing a `</script>` filter
    untouched. Every `<` is therefore escaped instead of any particular tag spelling, which no end-tag
    form can get around.

    `\u003c` is a valid escape both in JSON and in a JavaScript string literal, and it parses back to
    `<`, so every consumer reads exactly the value it was given. In JSON a `<` can only ever appear
    inside a string, so escaping it unconditionally never touches the document's structure.

    Args:
        value: The string to escape. Non-string values are returned unchanged.

    Returns:
        The escaped string, with every `<` replaced by `\u003c`.
    """
    if not isinstance(value, str):
        return value
    return value.replace("<", "\\u003c")


def markdown_to_html(value: Any) -> Markup:
    """Render a Markdown text as HTML: the `markdown` filter of HTML templates.

    It is for Markdown held in a plain text field, such as an invoice's notes; a `Markdown` stuff renders as
    HTML by itself. A text stuff renders its text, anything else its string form, and None nothing. An
    undefined value prints the way the template prints one anywhere else: nothing in a lenient template, and a
    render error in a strict one, which is how a misspelled field reached through an alias still fails. The parser is Pipelex's one Markdown parser (`markdown_parser.py`): raw HTML in the source
    is escaped rather than passed through, and only URLs with a scheme become links, so the markup is marked
    safe.
    """
    if value is None:
        return Markup("")
    # `str()` of a strict undefined raises, and of a lenient one is empty.
    source_text = value if isinstance(value, str) else str(value)
    return Markup(render_markdown_as_html(source_text))  # ruff: ignore[unsafe-markup-use] - raw HTML in the source is escaped by the parser
