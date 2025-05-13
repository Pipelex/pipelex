# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Tuple

from jinja2 import BaseLoader, Environment, PackageLoader

from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.jinja2_template_loader import Jinja2TemplateLoader
from pipelex.tools.templating.template_provider_abstract import TemplateProviderAbstract


def make_jinja2_env_from_loader(
    template_category: Jinja2TemplateCategory,
    loader: BaseLoader,
) -> Environment:
    match template_category:
        case Jinja2TemplateCategory.HTML:
            jinja2_env = Environment(
                loader=loader,
                enable_async=True,
                autoescape=False,
                trim_blocks=True,
                lstrip_blocks=True,
            )
        case Jinja2TemplateCategory.MARKDOWN:
            jinja2_env = Environment(
                loader=loader,
                enable_async=True,
                autoescape=False,
                trim_blocks=True,
                lstrip_blocks=True,
            )
        case Jinja2TemplateCategory.MERMAID:
            jinja2_env = Environment(
                loader=loader,
                enable_async=True,
                autoescape=False,
                trim_blocks=False,
                lstrip_blocks=False,
            )
        case Jinja2TemplateCategory.LLM_PROMPT:
            jinja2_env = Environment(
                loader=loader,
                enable_async=True,
                autoescape=False,
                trim_blocks=False,
                lstrip_blocks=False,
            )
    return jinja2_env


def make_jinja2_env_from_package(
    template_category: Jinja2TemplateCategory,
    package_name: str,
    package_path: str,
) -> Tuple[Environment, BaseLoader]:
    full_package_path = f"{package_path}/jinja2_{template_category}"
    loader = PackageLoader(
        package_name=package_name,
        package_path=full_package_path,
    )
    jinja2_env = make_jinja2_env_from_loader(template_category=template_category, loader=loader)
    return jinja2_env, loader


def make_jinja2_env_without_loader(
    template_category: Jinja2TemplateCategory,
) -> Environment:
    loader = BaseLoader()
    jinja2_env = make_jinja2_env_from_loader(template_category=template_category, loader=loader)
    return jinja2_env


def make_jinja2_env_from_template_provider(
    template_category: Jinja2TemplateCategory,
    template_provider: TemplateProviderAbstract,
) -> Tuple[Environment, BaseLoader]:
    loader = Jinja2TemplateLoader(template_provider=template_provider)
    jinja2_env = make_jinja2_env_from_loader(template_category=template_category, loader=loader)

    filters = template_category.filters
    for filter_name, filter_function in filters.items():
        jinja2_env.filters[filter_name] = filter_function  # type: ignore
    return jinja2_env, loader
