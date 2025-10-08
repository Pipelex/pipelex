from jinja2 import meta
from jinja2.exceptions import (
    TemplateSyntaxError,
    UndefinedError,
)

from pipelex.tools.templating.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.templating.jinja2_errors import Jinja2DetectVariablesError, Jinja2StuffError
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory


def detect_jinja2_required_variables(
    template_category: Jinja2TemplateCategory,
    template_source: str,
) -> set[str]:
    """Returns a list of variables required by the Jinja2 template.

    Args:
        template_category: Category of the template (HTML, MARKDOWN, etc.), used to set the appropriate jinja2 environment settings
        template_source: Jinja2 template string

    Returns:
        List of variable names required by the template

    Raises:
        Jinja2StuffError: If neither jinja2 nor jinja2_name is provided

    """
    jinja2_env = make_jinja2_env_without_loader(
        template_category=template_category,
    )

    try:
        parsed_ast = jinja2_env.parse(template_source)
        undeclared_variables = meta.find_undeclared_variables(parsed_ast)
    except Jinja2StuffError as stuff_error:
        msg = f"Jinja2 detect variables — stuff error: '{stuff_error}', template_source:\n{template_source}"
        raise Jinja2DetectVariablesError(msg) from stuff_error
    except TemplateSyntaxError as syntax_error:
        msg = f"Jinja2 detect variables — syntax error: '{syntax_error}', template_source:\n{template_source}"
        raise Jinja2DetectVariablesError(msg) from syntax_error
    except UndefinedError as undef_error:
        msg = f"Jinja2 detect variables — undefined error: '{undef_error}', template_source:\n{template_source}"
        raise Jinja2DetectVariablesError(msg) from undef_error

    return undeclared_variables
