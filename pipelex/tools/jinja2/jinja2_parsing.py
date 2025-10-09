import jinja2

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateSyntaxError


def check_jinja2_parsing(
    template_source: str,
    template_category: TemplateCategory = TemplateCategory.LLM_PROMPT,
):
    jinja2_env = make_jinja2_env_without_loader(template_category=template_category)
    try:
        jinja2_env.parse(template_source)
    except jinja2.exceptions.TemplateSyntaxError as exc:
        msg = f"Could not parse Jinja2 template because of: {exc}. Template source:\n{template_source}"
        raise Jinja2TemplateSyntaxError(msg) from exc
