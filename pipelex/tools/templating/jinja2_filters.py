from typing import Any, Optional

from jinja2 import pass_context
from jinja2.runtime import Context, Undefined

from pipelex.tools.templating.jinja2_errors import Jinja2ContextError
from pipelex.tools.templating.jinja2_models import Jinja2ContextKey, Jinja2TaggableAbstract
from pipelex.tools.templating.templating_models import TagStyle, TextFormat
from pipelex.types import StrEnum

########################################################################################
# Jinja2 filters
########################################################################################

ALLOWED_FILTERS = ["tag", "format"]


# Filter to format some Stuff or any object with the appropriate text formatting methods
@pass_context
def text_format(context: Context, value: Any, text_format: Optional[TextFormat] = None) -> Any:
    if text_format:
        if isinstance(text_format, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            applied_text_format = TextFormat(text_format)
        elif isinstance(text_format, TextFormat):  # pyright: ignore[reportUnnecessaryIsInstance]
            applied_text_format = text_format
        else:
            raise Jinja2ContextError(f"Invalid text format: '{text_format}'")
    else:
        applied_text_format = TextFormat(context.get(Jinja2ContextKey.TEXT_FORMAT, default=TextFormat.PLAIN))

    if hasattr(value, "rendered_str"):
        rendered_str = value.rendered_str(text_format=applied_text_format)
        return rendered_str
    elif hasattr(value, applied_text_format.render_method_name):
        render_method = getattr(value, applied_text_format.render_method_name)
        rendered_str = render_method()
        return rendered_str
    elif isinstance(value, StrEnum):
        return value.value
    else:
        return value


# TODO: better separate tag and render
# Filter to tag the variable with a tag style and a provided name, appropriate for tagging in a prompt
@pass_context
def tag(context: Context, value: Any, tag_name: Optional[str] = None) -> Any:
    if isinstance(value, Undefined):
        # maybe we don't need this check
        if tag_name:
            raise Jinja2ContextError(f"Jinja2 undefined value with tag_name '{tag_name}'.")
        else:
            raise Jinja2ContextError("Jinja2 undefined value.")

    if isinstance(value, Jinja2TaggableAbstract):
        value, tag_name = value.render_tagged_for_jinja2(context=context, tag_name=tag_name)

    return render_any_tagged_for_jinja2(context=context, value=value, tag_name=tag_name)


def render_any_tagged_for_jinja2(context: Context, value: Any, tag_name: Optional[str] = None) -> Any:
    tag_style_str = context.get(Jinja2ContextKey.TAG_STYLE)
    tag_style: TagStyle
    if tag_style_str:
        tag_style = TagStyle(tag_style_str)
    else:
        raise Jinja2ContextError(f"Tag style is required for Jinja2 tag filter (context.name = {context.name})")

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
