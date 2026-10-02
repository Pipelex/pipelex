"""The field paths a template reads from its inputs, through loop variables included, for checking them at load.

`detect_jinja2_required_variables` answers which inputs a template needs; this answers which fields of them it
reads, so a load-time check can compare each path with the input's concept and refuse `invoice.nosuch` before
any run. A loop variable is followed back to what it iterates: in `{% for item in invoice.line_items %}`,
`item.amount` reads `invoice.line_items[].amount`, the `[]` standing for an item of the list.

It is deliberately conservative, since what it cannot follow is left to the strict undefined at the dry run: a
name set with `{% set %}`, a macro argument, a tuple loop target, and a chain that starts from a subscript, a
call or a filter give no path. Only attribute chains (`a.b.c`) are followed; `a['b']` is not.
"""

from typing import NamedTuple

from jinja2 import nodes
from jinja2.exceptions import TemplateSyntaxError

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.template_category import TemplateCategory

# The segment standing for "an item of the list" in a path reached through a loop variable.
LIST_ITEM_SEGMENT = "[]"


class TemplateFieldPath(NamedTuple):
    """One attribute chain a template reads, resolved back to the input it starts from."""

    root: str
    segments: tuple[str, ...]
    written: str
    """The chain as the template writes it, such as `item.amount`, for messages."""


# What a name stands for where it is read: the path it is bound to, or None when it is declared locally and
# cannot be followed (a `set`, a macro argument, `loop`). A name absent from the bindings is an input or a global.
_Bindings = dict[str, tuple[str, ...] | None]


def _chain(node: nodes.Node) -> tuple[str, list[str]] | None:
    """The name and attribute names of a pure attribute chain (`a.b.c`), or None for any other shape."""
    attributes: list[str] = []
    current = node
    while isinstance(current, nodes.Getattr):
        attributes.append(current.attr)
        current = current.node
    if isinstance(current, nodes.Name):
        return current.name, list(reversed(attributes))
    return None


def _resolve(*, name: str, attributes: list[str], bindings: _Bindings) -> tuple[str, ...] | None:
    """The full path a chain reads, through the bindings: None when it starts from a name that cannot be followed."""
    if name in bindings:
        bound = bindings[name]
        if bound is None:
            return None
        return (*bound, *attributes)
    return (name, *attributes)


def _target_names(target: nodes.Node) -> list[str]:
    if isinstance(target, nodes.Name):
        return [target.name]
    if isinstance(target, nodes.Tuple):
        return [name for item in target.items for name in _target_names(item)]
    return []


def _walk(*, node: nodes.Node, bindings: _Bindings, paths: list[TemplateFieldPath]) -> None:
    if isinstance(node, (nodes.Template, nodes.Scope)):
        _walk_body(body=node.body, bindings=bindings, paths=paths)
        return
    if isinstance(node, nodes.With):
        for value in node.values:
            _walk(node=value, bindings=bindings, paths=paths)
        with_bindings: _Bindings = dict(bindings)
        for target in node.targets:
            for target_name in _target_names(target):
                with_bindings[target_name] = None
        _walk_body(body=node.body, bindings=with_bindings, paths=paths)
        return
    if isinstance(node, nodes.For):
        _walk(node=node.iter, bindings=bindings, paths=paths)
        loop_bindings: _Bindings = {**bindings, "loop": None}
        iterated = _chain(node.iter)
        iterated_path = _resolve(name=iterated[0], attributes=iterated[1], bindings=bindings) if iterated is not None else None
        if isinstance(node.target, nodes.Name) and iterated_path is not None:
            loop_bindings[node.target.name] = (*iterated_path, LIST_ITEM_SEGMENT)
        else:
            for target_name in _target_names(node.target):
                loop_bindings[target_name] = None
        _walk_body(body=node.body, bindings=loop_bindings, paths=paths)
        if node.test is not None:
            _walk(node=node.test, bindings=loop_bindings, paths=paths)
        _walk_body(body=node.else_, bindings=bindings, paths=paths)
        return
    if isinstance(node, nodes.Macro):
        macro_bindings: _Bindings = {**bindings, "caller": None, "varargs": None, "kwargs": None}
        for argument in node.args:
            macro_bindings[argument.name] = None
        for default in node.defaults:
            _walk(node=default, bindings=bindings, paths=paths)
        _walk_body(body=node.body, bindings=macro_bindings, paths=paths)
        return
    if isinstance(node, (nodes.Name, nodes.Getattr)):
        chain = _chain(node)
        if chain is not None:
            if isinstance(node, nodes.Name) and node.ctx != "load":
                return
            name, attributes = chain
            path = _resolve(name=name, attributes=attributes, bindings=bindings)
            if path is not None:
                written = ".".join([name, *attributes])
                paths.append(TemplateFieldPath(root=path[0], segments=path[1:], written=written))
            return
    for child in node.iter_child_nodes():
        _walk(node=child, bindings=bindings, paths=paths)


def _walk_body(*, body: list[nodes.Node], bindings: _Bindings, paths: list[TemplateFieldPath]) -> None:
    """Walk statements in order: a `{% set %}` declares its name for the statements after it, in this scope."""
    scope_bindings: _Bindings = dict(bindings)
    for statement in body:
        if isinstance(statement, nodes.Macro):
            scope_bindings[statement.name] = None
        _walk(node=statement, bindings=scope_bindings, paths=paths)
        if isinstance(statement, (nodes.Assign, nodes.AssignBlock)):
            for target_name in _target_names(statement.target):
                scope_bindings[target_name] = None


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
    _walk(node=parsed_ast, bindings={}, paths=paths)
    return paths
