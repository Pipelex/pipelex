"""Load-time detection of the private names a template reads, for a located validation error.

The template sandbox (`jinja2_sandbox.py`) refuses, at render time, every name starting with an
underscore that the value's type does not declare in its template surface. Most such reads are
visible in the template itself: `{{ doc._stuff }}` or `{{ doc['_content'] }}`. This walker finds those
at load, so that validation names the pipe and the template instead of a run failing later.

It is feedback, not enforcement. The types of the values are unknown at load, so it allows every name
any declaring type declares, and it cannot see a name that is only computed at render time: the
runtime policy remains what refuses them.
"""

from collections.abc import Iterator

from jinja2 import nodes
from jinja2.exceptions import TemplateSyntaxError

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.template_category import TemplateCategory


def detect_private_name_references(
    *,
    template_category: TemplateCategory,
    template_source: str,
    allowed_private_names: frozenset[str],
) -> list[str]:
    """Return the private names the template reads with a dot or with a constant bracketed key.

    Args:
        template_category: Category of the template (LLM_PROMPT, EXPRESSION, etc.)
        template_source: Jinja2 template source (sigils already rewritten to Jinja2).
        allowed_private_names: The underscore-prefixed names a declaring type lets templates read.

    Returns:
        Each refused name once, in the order a render would reach them.

    Raises:
        Jinja2DetectVariablesError: If the template cannot be parsed.
    """
    jinja2_env = make_jinja2_env_without_loader(template_category=template_category)
    try:
        parsed_ast = jinja2_env.parse(template_source)
    except TemplateSyntaxError as syntax_error:
        msg = (
            f"Jinja2 private-name lint — syntax error: '{syntax_error}', template_category: {template_category}, template_source:\n{template_source}"
        )
        raise Jinja2DetectVariablesError(msg) from syntax_error

    refused_names: list[str] = []
    for node in _iter_nodes_in_evaluation_order(node=parsed_ast):
        name: str | None = None
        if isinstance(node, nodes.Getattr):
            name = node.attr
        elif isinstance(node, nodes.Getitem) and isinstance(node.arg, nodes.Const) and isinstance(node.arg.value, str):
            name = node.arg.value
        if name is None or not name.startswith("_") or name in allowed_private_names or name in refused_names:
            continue
        refused_names.append(name)
    return refused_names


def _iter_nodes_in_evaluation_order(*, node: nodes.Node) -> Iterator[nodes.Node]:
    """Yield every node after its children, so a chain's first access comes first: `__class__` before `__mro__`."""
    for child in node.iter_child_nodes():
        yield from _iter_nodes_in_evaluation_order(node=child)
    yield node
