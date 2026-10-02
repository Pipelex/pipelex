"""The field paths a template reads from its inputs, through loop variables included, for checking them at load.

`detect_jinja2_required_variables` answers which inputs a template needs; this answers which fields of them it
reads, so a load-time check can compare each path with the input's concept and refuse `invoice.nosuch` before
any run. A loop variable is followed back to what it iterates: in `{% for item in invoice.line_items %}`,
`item.amount` reads `invoice.line_items[].amount`, the `[]` standing for an item of the list.

Both detectors are handlers on the one read walk of `jinja2_scopes.py`, so they agree on which names the template
binds: a name set in every branch of an `if`, or anywhere before the read in the same loop or block body, is the
template's own and gives no path, while a name set in only some branches is read as the input of that name, and
its path is checked. The walk is deliberately conservative, since what it cannot follow is left to the strict
undefined at the dry run: a name the template sets, a macro argument, a tuple loop target, a called global and
a chain that starts from a subscript, a call or a filter give no path. Only attribute chains (`a.b.c`) are
followed; `a['b']` is not.
"""

from typing import NamedTuple

from jinja2 import nodes
from jinja2.exceptions import TemplateSyntaxError

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_scopes import ScopeBindings, attribute_chain, resolve_bound_path, walk_template_reads
from pipelex.tools.jinja2.template_category import TemplateCategory


class TemplateFieldPath(NamedTuple):
    """One attribute chain a template reads, resolved back to the input it starts from."""

    root: str
    segments: tuple[str, ...]
    written: str
    """The chain as the template writes it, such as `item.amount`, for messages."""


def detect_template_field_paths(*, template_source: str, template_category: TemplateCategory) -> list[TemplateFieldPath]:
    """Every attribute chain the template reads, in source order, resolved back to the name it starts from.

    The root of a path is an input name or a global of the environment; the caller keeps the ones it knows.

    Raises:
        Jinja2DetectVariablesError: the template does not parse.
    """
    jinja2_env = make_jinja2_env_without_loader(template_category=template_category)
    try:
        parsed_ast = jinja2_env.parse(template_source)
    except TemplateSyntaxError as syntax_error:
        msg = f"Jinja2 detect field paths — syntax error: '{syntax_error}', template_category: {template_category}"
        raise Jinja2DetectVariablesError(msg) from syntax_error
    paths: list[TemplateFieldPath] = []

    def collect_field_path(*, node: nodes.Node, bindings: ScopeBindings) -> bool:
        if not isinstance(node, (nodes.Name, nodes.Getattr)):
            return False
        chain = attribute_chain(node)
        if chain is None:
            # An attribute on a subscript, a call or a filter (`items[0].text`) reads the path its chain starts from
            return False
        name, attributes = chain
        path = resolve_bound_path(name=name, attributes=attributes, bindings=bindings)
        if path is not None:
            paths.append(TemplateFieldPath(root=path[0], segments=path[1:], written=".".join([name, *attributes])))
        return True

    walk_template_reads(template=parsed_ast, global_names=set(jinja2_env.globals), handle_read=collect_field_path)
    return paths
