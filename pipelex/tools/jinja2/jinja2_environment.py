from jinja2 import BaseLoader, Environment

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry


def make_jinja2_env_from_loader(
    template_category: TemplateCategory,
    loader: BaseLoader,
    *,
    enable_async: bool = True,
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
            autoescape = True
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
        case TemplateCategory.IMG_GEN_PROMPT:
            autoescape = False
            trim_blocks = False
            lstrip_blocks = False

    return Environment(
        loader=loader,
        enable_async=enable_async,
        autoescape=autoescape,
        trim_blocks=trim_blocks,
        lstrip_blocks=lstrip_blocks,
    )


def make_jinja2_env_without_loader(
    template_category: TemplateCategory,
    *,
    enable_async: bool = True,
) -> Environment:
    loader = BaseLoader()
    jinja2_env = make_jinja2_env_from_loader(
        template_category=template_category,
        loader=loader,
        enable_async=enable_async,
    )

    filters = template_category.filters
    for filter_name, filter_function in filters.items():
        jinja2_env.filters[filter_name] = filter_function  # pyright: ignore[reportArgumentType]
    return jinja2_env


def make_jinja2_env_from_registry(
    template_category: TemplateCategory,
    *,
    enable_async: bool = True,
) -> Environment:
    """Create Environment with DictLoader from pre-loaded registry.

    This function creates a Jinja2 Environment backed by the TemplateRegistry,
    enabling {% include %} statements to resolve templates without filesystem
    access at render time. Safe for use in Temporal.io sandboxes.

    Args:
        template_category: The category of templates being rendered.
        enable_async: Whether to enable async mode for the environment.

    Returns:
        A Jinja2 Environment with DictLoader and appropriate filters.
    """
    loader = TemplateRegistry.get_dict_loader()
    jinja2_env = make_jinja2_env_from_loader(
        template_category=template_category,
        loader=loader,
        enable_async=enable_async,
    )

    filters = template_category.filters
    for filter_name, filter_function in filters.items():
        jinja2_env.filters[filter_name] = filter_function  # pyright: ignore[reportArgumentType]
    return jinja2_env
