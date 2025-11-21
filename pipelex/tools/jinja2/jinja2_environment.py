from jinja2 import BaseLoader, Environment

from pipelex.cogt.templating.template_category import TemplateCategory


def make_jinja2_env_from_loader(
    template_category: TemplateCategory,
    loader: BaseLoader,
) -> Environment:
    autoescape: bool
    trim_blocks: bool
    lstrip_blocks: bool
    match template_category:
        case TemplateCategory.BASIC:
            autoescape = False
            trim_blocks = False
            lstrip_blocks = False
        case TemplateCategory.EXPRESSION:
            autoescape = False
            trim_blocks = False
            lstrip_blocks = False
        case TemplateCategory.HTML:
            autoescape = False
            trim_blocks = True
            lstrip_blocks = True
        case TemplateCategory.MARKDOWN:
            autoescape = False
            trim_blocks = True
            lstrip_blocks = True
        case TemplateCategory.MERMAID:
            autoescape = False
            trim_blocks = False
            lstrip_blocks = False
        case TemplateCategory.LLM_PROMPT:
            autoescape = False
            trim_blocks = False
            lstrip_blocks = False

    return Environment(
        loader=loader,
        enable_async=True,
        autoescape=autoescape,
        trim_blocks=trim_blocks,
        lstrip_blocks=lstrip_blocks,
    )


def make_jinja2_env_without_loader(
    template_category: TemplateCategory,
) -> Environment:
    loader = BaseLoader()
    jinja2_env = make_jinja2_env_from_loader(template_category=template_category, loader=loader)

    filters = template_category.filters
    for filter_name, filter_function in filters.items():
        jinja2_env.filters[filter_name] = filter_function  # pyright: ignore[reportArgumentType]
    return jinja2_env
