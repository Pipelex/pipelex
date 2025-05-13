# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional, Set

from jinja2 import meta
from jinja2.exceptions import (
    TemplateSyntaxError,
    UndefinedError,
)

from pipelex.tools.templating.jinja2_environment import make_jinja2_env_from_template_provider
from pipelex.tools.templating.jinja2_errors import Jinja2DetectVariablesError, Jinja2StuffError, make_jinja2_error_explanation
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.template_provider_abstract import TemplateProviderAbstract


def detect_jinja2_required_variables(
    template_category: Jinja2TemplateCategory,
    template_provider: TemplateProviderAbstract,
    jinja2_name: Optional[str] = None,
    jinja2: Optional[str] = None,
) -> Set[str]:
    """
    Returns a list of variables required by the Jinja2 template.

    Args:
        template_category: Category of the template (HTML, MARKDOWN, etc.), used to set the appropriate jinja2 environment settings
        template_library: Library containing templates
        jinja2_name: Name of template in library (optional)
        jinja2: Direct Jinja2 template string (optional)

    Returns:
        List of variable names required by the template

    Raises:
        Jinja2StuffError: If neither jinja2 nor jinja2_name is provided
    """
    jinja2_env, loader = make_jinja2_env_from_template_provider(
        template_category=template_category,
        template_provider=template_provider,
    )

    template_source: str
    if jinja2:
        template_source = jinja2
    elif jinja2_name:
        template_source = loader.get_source(jinja2_env, jinja2_name)[0]
    else:
        raise Jinja2StuffError("No jinja2 or jinja2_name provided")

    try:
        parsed_ast = jinja2_env.parse(template_source)
        undeclared_variables = meta.find_undeclared_variables(parsed_ast)
    except Jinja2StuffError as stuff_error:
        explanation = make_jinja2_error_explanation(jinja2_name=jinja2_name, template_text=template_source)
        raise Jinja2DetectVariablesError(f"Jinja2 detect variables — stuff error: '{stuff_error}' {explanation}") from stuff_error
    except TemplateSyntaxError as syntax_error:
        explanation = make_jinja2_error_explanation(jinja2_name=jinja2_name, template_text=template_source)
        raise Jinja2DetectVariablesError(f"Jinja2 detect variables — syntax error: '{syntax_error}' {explanation}") from syntax_error
    except UndefinedError as undef_error:
        explanation = make_jinja2_error_explanation(jinja2_name=jinja2_name, template_text=template_source)
        raise Jinja2DetectVariablesError(f"Jinja2 detect variables — undefined error: '{undef_error}' {explanation}") from undef_error

    return undeclared_variables
