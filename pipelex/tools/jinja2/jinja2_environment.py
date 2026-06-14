import inspect

from jinja2 import BaseLoader, Environment

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry


def make_jinja2_env_from_loader(
    template_category: TemplateCategory,
    *,
    loader: BaseLoader,
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


def _register_filters(
    jinja2_env: Environment,
    *,
    template_category: TemplateCategory,
    enable_async: bool,
) -> None:
    """Register template category filters on the Jinja2 environment.

    Async filters (detected via inspect.iscoroutinefunction) are only registered
    when enable_async is True. This prevents silent corruption where async filters
    would return coroutine objects instead of strings in sync environments.

    Args:
        jinja2_env: The Jinja2 environment to register filters on.
        template_category: The category defining which filters to register.
        enable_async: Whether the environment supports async rendering.
    """
    filters = template_category.filters
    for filter_name, filter_function in filters.items():
        if not enable_async and inspect.iscoroutinefunction(filter_function):
            continue
        jinja2_env.filters[filter_name] = filter_function  # pyright: ignore[reportArgumentType]


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

    _register_filters(jinja2_env, template_category=template_category, enable_async=enable_async)
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

    _register_filters(jinja2_env, template_category=template_category, enable_async=enable_async)
    return jinja2_env
