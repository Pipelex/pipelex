"""The filters and tests a template names that its environment does not define.

Jinja2 refuses such a name when it compiles the template, unless the name sits inside a branch: there it compiles to a
lookup that only fails when that branch renders. A run that reaches the failure knows what Jinja2 refused, not which
of a pipe's templates refused it, so a pipe holding several templates asks this walker which of them names an unknown
filter or test, to name that template's field in its refusal.
"""

from jinja2 import nodes
from jinja2.exceptions import TemplateSyntaxError

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.template_category import TemplateCategory


def find_unknown_filters_and_tests(*, template_source: str, template_category: TemplateCategory) -> list[str]:
    """Return the names of the filters and tests the template uses that its category's environment does not define.

    Args:
        template_source: Jinja2 template source (sigils already rewritten to Jinja2).
        template_category: Category of the template, which decides the filters its environment defines.

    Returns:
        Each unknown name once, in the order the template names them.

    Raises:
        Jinja2DetectVariablesError: If the template cannot be parsed.
    """
    jinja2_env = make_jinja2_env_without_loader(template_category=template_category)
    try:
        parsed_ast = jinja2_env.parse(template_source)
    except TemplateSyntaxError as syntax_error:
        msg = f"Jinja2 unknown-name lint — syntax error: '{syntax_error}', template_category: {template_category}"
        raise Jinja2DetectVariablesError(msg) from syntax_error

    unknown_names: list[str] = []
    for node in parsed_ast.find_all((nodes.Filter, nodes.Test)):
        if isinstance(node, nodes.Filter):
            is_known = node.name in jinja2_env.filters
        else:
            is_known = node.name in jinja2_env.tests
        if not is_known and node.name not in unknown_names:
            unknown_names.append(node.name)
    return unknown_names
