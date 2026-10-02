import inspect
from collections.abc import Callable
from typing import Any

from jinja2 import BaseLoader, Undefined

from pipelex.tools.jinja2.jinja2_sandbox import PipelexTemplateEnvironment
from pipelex.tools.jinja2.jinja2_template_registry import TemplateRegistry
from pipelex.tools.jinja2.jinja2_undefined import PresenceProbingStrictUndefined
from pipelex.tools.jinja2.template_category import TemplateCategory


def make_jinja2_env_from_loader(
    *,
    template_category: TemplateCategory,
    loader: BaseLoader,
    enable_async: bool = True,
    finalize: Callable[..., Any] | None = None,
    is_undefined_strict: bool = False,
) -> PipelexTemplateEnvironment:
    """Build the environment for one template category. Every template renders sandboxed (`jinja2_sandbox.py`).

    A `finalize` is handed to the environment here, which wraps it to charge what is printed to the
    render's budget.

    With `is_undefined_strict`, a missing value fails the render instead of printing as empty text
    (`jinja2_undefined.py`); `PipeDocGen` asks for it, and every other template keeps Jinja's lenient default.
    """
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

    undefined: type[Undefined] = PresenceProbingStrictUndefined if is_undefined_strict else Undefined
    return PipelexTemplateEnvironment(
        loader=loader,
        enable_async=enable_async,
        autoescape=autoescape,
        trim_blocks=trim_blocks,
        lstrip_blocks=lstrip_blocks,
        finalize=finalize,
        undefined=undefined,
    )


def _register_filters(
    jinja2_env: PipelexTemplateEnvironment,
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
    finalize: Callable[..., Any] | None = None,
    is_undefined_strict: bool = False,
) -> PipelexTemplateEnvironment:
    loader = BaseLoader()
    jinja2_env = make_jinja2_env_from_loader(
        template_category=template_category,
        loader=loader,
        enable_async=enable_async,
        finalize=finalize,
        is_undefined_strict=is_undefined_strict,
    )

    _register_filters(jinja2_env, template_category=template_category, enable_async=enable_async)
    return jinja2_env


def make_jinja2_env_from_registry(
    template_category: TemplateCategory,
    *,
    enable_async: bool = True,
    finalize: Callable[..., Any] | None = None,
    is_undefined_strict: bool = False,
) -> PipelexTemplateEnvironment:
    """Create Environment with DictLoader from pre-loaded registry.

    This function creates a Jinja2 Environment backed by the TemplateRegistry,
    enabling {% include %} statements to resolve templates without filesystem
    access at render time. Safe for use in Temporal.io sandboxes.

    Args:
        template_category: The category of templates being rendered.
        enable_async: Whether to enable async mode for the environment.
        finalize: The caller's own finalize, if any, applied to every printed value.
        is_undefined_strict: Whether a missing value fails the render instead of printing as empty text.

    Returns:
        A Jinja2 Environment with DictLoader and appropriate filters.
    """
    loader = TemplateRegistry.get_dict_loader()
    jinja2_env = make_jinja2_env_from_loader(
        template_category=template_category,
        loader=loader,
        enable_async=enable_async,
        finalize=finalize,
        is_undefined_strict=is_undefined_strict,
    )

    _register_filters(jinja2_env, template_category=template_category, enable_async=enable_async)
    return jinja2_env
