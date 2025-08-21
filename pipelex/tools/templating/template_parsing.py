from pipelex.tools.templating.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.templating.template_category import TemplateCategory


def check_template_parsing(
    template_source: str,
    template_category: TemplateCategory = TemplateCategory.LLM_PROMPT,
):
    jinja2_env = make_jinja2_env_without_loader(template_category=template_category)
    jinja2_env.parse(template_source)
