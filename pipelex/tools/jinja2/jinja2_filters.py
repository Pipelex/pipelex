from typing import Any

from jinja2 import pass_context
from jinja2.runtime import Context, Undefined

from pipelex.cogt.templating.templating_style import TagStyle, TextFormat
from pipelex.tools.jinja2.jinja2_errors import Jinja2ContextError
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey, Jinja2TaggableAbstract
from pipelex.types import StrEnum

########################################################################################
# Jinja2 filters
########################################################################################

ALLOWED_FILTERS = ["tag", "format", "default"]


# Filter to format some Stuff or any object with the appropriate text formatting methods
@pass_context
def text_format(context: Context, value: Any, text_format: TextFormat | None = None) -> Any:
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

    if hasattr(value, "rendered_str"):
        return value.rendered_str(text_format=applied_text_format)
    if hasattr(value, applied_text_format.render_method_name):
        render_method = getattr(value, applied_text_format.render_method_name)
        return render_method()
    if isinstance(value, StrEnum):
        return value.value
    return value


# TODO: better separate tag and render
# Filter to tag the variable with a tag style and a provided name, appropriate for tagging in a prompt
@pass_context
def tag(context: Context, value: Any, tag_name: str | None = None) -> Any:
    if isinstance(value, Undefined):
        # maybe we don't need this check
        if tag_name:
            msg = f"Jinja2 undefined value with tag_name '{tag_name}'"
            raise Jinja2ContextError(msg)
        msg = "Jinja2 undefined value."
        raise Jinja2ContextError(msg)

    if isinstance(value, Jinja2TaggableAbstract):
        value, tag_name = value.render_tagged_for_jinja2(context=context, tag_name=tag_name)

    return render_any_tagged_for_jinja2(context=context, value=value, tag_name=tag_name)


def render_any_tagged_for_jinja2(context: Context, value: Any, tag_name: str | None = None) -> Any:
    tag_style_str = context.get(Jinja2ContextKey.TAG_STYLE)
    tag_style: TagStyle
    if tag_style_str:
        tag_style = TagStyle(tag_style_str)
    else:
        # raise Jinja2ContextError(f"Tag style is required for Jinja2 tag filter (context.name = {context.name})")
        # TODO: ignoring this error is a workaround, the real bug will be fixed as part of a full refactor of the jinja2 filters
        tag_style = TagStyle.TICKS

    tagged: Any
    if tag_name:
        match tag_style:
            case TagStyle.NO_TAG:
                tagged = value
            case TagStyle.TICKS:
                tagged = f"{tag_name}: ```\n{value}\n```"
            case TagStyle.XML:
                tagged = f"<{tag_name}>\n{value}\n</{tag_name}>"
            case TagStyle.SQUARE_BRACKETS:
                tagged = f"[{tag_name}]\n{value}\n[/{tag_name}]"
    else:
        match tag_style:
            case TagStyle.NO_TAG:
                tagged = value
            case TagStyle.TICKS:
                tagged = f"```\n{value}\n```"
            case TagStyle.XML:
                fallback_tag_name = "data"
                tagged = f"<{fallback_tag_name}>\n{value}\n</{fallback_tag_name}>"
            case TagStyle.SQUARE_BRACKETS:
                fallback_tag_name = "data"
                tagged = f"[{fallback_tag_name}]\n{value}\n[/{fallback_tag_name}]"
    return tagged
