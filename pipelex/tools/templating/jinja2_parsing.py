from jinja2.exceptions import TemplateSyntaxError

from pipelex.tools.templating.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory


class Jinja2ParsingError(Exception):
    pass


def check_jinja2_parsing(
    jinja2_template_source: str,
    template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT,
):
    jinja2_env = make_jinja2_env_without_loader(template_category=template_category)
    try:
        jinja2_env.parse(jinja2_template_source)
    except TemplateSyntaxError as exc:
        msg = f"Could not parse Jinja2 template because of: {exc}. The template is:\n{jinja2_template_source}"
        raise Jinja2ParsingError(msg) from exc
