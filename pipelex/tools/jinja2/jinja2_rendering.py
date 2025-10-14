from typing import Any

from jinja2.exceptions import (
    TemplateAssertionError,
    TemplateSyntaxError,
    UndefinedError,
)

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_errors import (
    Jinja2ContextError,
    Jinja2StuffError,
    Jinja2TemplateRenderError,
)
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey


def _add_to_templating_context(temlating_context: dict[str, Any], jinja2_context_key: Jinja2ContextKey, value: Any) -> None:
    if jinja2_context_key in temlating_context:
        msg = f"Jinja2 context key '{jinja2_context_key}' already in temlating_context"
        raise Jinja2StuffError(msg)
    temlating_context[jinja2_context_key] = value


async def render_jinja2(
    template_source: str,
    template_category: TemplateCategory,
    temlating_context: dict[str, Any],
    templating_style: TemplatingStyle | None = None,
) -> str:
    jinja2_env = make_jinja2_env_without_loader(
        template_category=template_category,
    )

    try:
        template = jinja2_env.from_string(template_source)
    except TemplateAssertionError as exc:
        msg = f"Jinja2 render error: '{exc}', template_source:\n{template_source}"
        raise Jinja2TemplateRenderError(msg) from exc

    # Create a copy to avoid mutating the caller's original dictionary
    temlating_context = temlating_context.copy()
    if templating_style:
        _add_to_templating_context(
            temlating_context=temlating_context,
            jinja2_context_key=Jinja2ContextKey.TAG_STYLE,
            value=templating_style.tag_style,
        )
        _add_to_templating_context(
            temlating_context=temlating_context,
            jinja2_context_key=Jinja2ContextKey.TEXT_FORMAT,
            value=templating_style.text_format,
        )

    try:
        generated_text: str = await template.render_async(**temlating_context)
    except Jinja2StuffError as stuff_error:
        msg = f"Jinja2 render — stuff error: '{stuff_error}', template_source:\n{template_source}"
        raise Jinja2TemplateRenderError(msg) from stuff_error
    except TemplateSyntaxError as syntax_error:
        msg = f"Jinja2 render — syntax error: '{syntax_error}', template_source:\n{template_source}"
        raise Jinja2TemplateRenderError(msg) from syntax_error
    except UndefinedError as undef_error:
        msg = f"Jinja2 render — undefined error: '{undef_error}', template_source:\n{template_source}"
        raise Jinja2TemplateRenderError(msg) from undef_error
    except Jinja2ContextError as context_error:
        msg = f"Jinja2 render — context error: '{context_error}', template_source:\n{template_source}"
        raise Jinja2TemplateRenderError(msg) from context_error
    return generated_text
