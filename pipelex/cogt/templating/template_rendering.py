from typing import Any

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2


async def render_template(
    template: str,
    category: TemplateCategory,
    context: dict[str, Any],
    templating_style: TemplatingStyle | None = None,
) -> str:
    template_source = preprocess_template(template)
    return await render_jinja2(
        template_source=template_source,
        template_category=category,
        temlating_context=context,
        templating_style=templating_style,
    )
