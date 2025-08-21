from typing import Optional, Set

from jinja2 import meta
from jinja2.exceptions import (
    TemplateSyntaxError,
    UndefinedError,
)

from pipelex.tools.templating.jinja2_environment import make_jinja2_env_from_template_provider
from pipelex.tools.templating.jinja2_errors import TemplateDetectVariablesError, TemplateStuffError, make_jinja2_error_explanation
from pipelex.tools.templating.template_category import TemplateCategory
from pipelex.tools.templating.template_provider_abstract import TemplateProviderAbstract


def detect_template_required_variables(
    template_category: TemplateCategory,
    template_provider: TemplateProviderAbstract,
    template_name: Optional[str] = None,
    template: Optional[str] = None,
) -> Set[str]:
    """
    Returns a list of variables required by the Jinja2 template.

    Args:
        template_category: Category of the template (HTML, MARKDOWN, etc.), used to set the appropriate jinja2 environment settings
        template_library: Library containing templates
        template_name: Name of template in library (optional)
        template: Direct Jinja2 template string (optional)

    Returns:
        List of variable names required by the template

    Raises:
        Jinja2StuffError: If neither template nor template_name is provided
    """
    jinja2_env, loader = make_jinja2_env_from_template_provider(
        template_category=template_category,
        template_provider=template_provider,
    )

    template_source: str
    if template:
        template_source = template
    elif template_name:
        template_source = loader.get_source(jinja2_env, template_name)[0]
    else:
        raise TemplateStuffError("No template or template_name provided")

    try:
        parsed_ast = jinja2_env.parse(template_source)
        undeclared_variables = meta.find_undeclared_variables(parsed_ast)
    except TemplateStuffError as stuff_error:
        explanation = make_jinja2_error_explanation(template_name=template_name, template_text=template_source)
        raise TemplateDetectVariablesError(f"Jinja2 detect variables — stuff error: '{stuff_error}' {explanation}") from stuff_error
    except TemplateSyntaxError as syntax_error:
        explanation = make_jinja2_error_explanation(template_name=template_name, template_text=template_source)
        raise TemplateDetectVariablesError(f"Jinja2 detect variables — syntax error: '{syntax_error}' {explanation}") from syntax_error
    except UndefinedError as undef_error:
        explanation = make_jinja2_error_explanation(template_name=template_name, template_text=template_source)
        raise TemplateDetectVariablesError(f"Jinja2 detect variables — undefined error: '{undef_error}' {explanation}") from undef_error

    return undeclared_variables
