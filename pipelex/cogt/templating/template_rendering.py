from collections.abc import Callable
from typing import Any

from pipelex.cogt.templating.template_preprocessor import rewrite_template_sigils
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TemplatingStyle


async def render_template(
    template: str,
    *,
    category: TemplateCategory,
    context: dict[str, Any],
    templating_style: TemplatingStyle | None = None,
    finalize: Callable[[Any], Any] | None = None,
) -> str:
    template_source = rewrite_template_sigils(template)

    return await render_jinja2_async(
        template_source=template_source,
        template_category=category,
        templating_context=context,
        templating_style=templating_style,
        finalize=finalize,
    )
