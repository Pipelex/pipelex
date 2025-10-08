import jinja2

from pipelex.tools.templating.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.templating.jinja2_errors import TemplateSyntaxError
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory


def check_jinja2_parsing(
    jinja2_template_source: str,
    template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT,
):
    jinja2_env = make_jinja2_env_without_loader(template_category=template_category)
    try:
        jinja2_env.parse(jinja2_template_source)
    except jinja2.exceptions.TemplateSyntaxError as exc:
        msg = f"Could not parse Jinja2 template because of: {exc}. Template source:\n{jinja2_template_source}"
        raise TemplateSyntaxError(msg) from exc
