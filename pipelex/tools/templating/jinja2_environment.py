from __future__ import annotations

from typing import Any, Callable, Mapping, MutableMapping, cast

from jinja2 import BaseLoader, Environment, PackageLoader

from pipelex.tools.templating.jinja2_template_category import FilterFunc, Jinja2TemplateCategory
from pipelex.tools.templating.jinja2_template_loader import Jinja2TemplateLoader
from pipelex.tools.templating.template_provider_abstract import TemplateProviderAbstract


def _make_env(*, loader: BaseLoader | None, trim: bool, lstrip: bool) -> Environment:
    return Environment(
        loader=loader,
        enable_async=True,
        autoescape=False,
        trim_blocks=trim,
        lstrip_blocks=lstrip,
    )


def make_jinja2_env_from_loader(
    template_category: Jinja2TemplateCategory,
    loader: BaseLoader | None,
) -> Environment:
    trim, lstrip = {
        Jinja2TemplateCategory.HTML: (True, True),
        Jinja2TemplateCategory.MARKDOWN: (True, True),
        Jinja2TemplateCategory.MERMAID: (False, False),
        Jinja2TemplateCategory.LLM_PROMPT: (False, False),
    }[template_category]
    return _make_env(loader=loader, trim=trim, lstrip=lstrip)


def make_jinja2_env_from_package(
    template_category: Jinja2TemplateCategory,
    package_name: str,
    package_path: str,
) -> tuple[Environment, BaseLoader]:
    full_package_path = f"{package_path}/jinja2_{template_category}"
    loader: BaseLoader = PackageLoader(
        package_name=package_name,
        package_path=full_package_path,
    )
    jinja2_env = make_jinja2_env_from_loader(template_category=template_category, loader=loader)
    return jinja2_env, loader


def make_jinja2_env_without_loader(
    template_category: Jinja2TemplateCategory,
) -> Environment:
    # No loader is cleaner than instantiating the abstract BaseLoader
    return make_jinja2_env_from_loader(template_category=template_category, loader=None)


def make_jinja2_env_from_template_provider(
    template_category: Jinja2TemplateCategory,
    template_provider: TemplateProviderAbstract,
) -> tuple[Environment, BaseLoader]:
    loader: BaseLoader = Jinja2TemplateLoader(template_provider=template_provider)
    env = make_jinja2_env_from_loader(template_category=template_category, loader=loader)

    filters: Mapping[str, FilterFunc] = template_category.filters
    env_filters: MutableMapping[str, Callable[..., Any]] = cast(MutableMapping[str, Callable[..., Any]], env.filters)
    env_filters.update(filters)

    return env, loader
