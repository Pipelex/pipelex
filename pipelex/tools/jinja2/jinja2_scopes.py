"""Where Jinja binds a name a template sets, and the one read walk the template detectors share.

The input check, the image and document references and PipeDocGen's field check all ask which of the names a
template reads come from its inputs. A name the template binds itself (a `{% set %}`, a loop target, a macro
argument) does not, from where Jinja binds it, and the rule is stated here once, as Jinja's compiler applies it
(`jinja2/idtracking.py`):

- A loop body, a loop's `else` branch, a macro body, a call block, a filter block, a set block's body and a
  `with` body each run in a frame of their own, and so does `{% autoescape %}`, which Jinja parses into a scope:
  a name set inside one is not bound after it.
- An `if` opens no frame, and each of its branches starts from the names bound before it. After the `if`, a name
  every branch sets, the `else` included, is bound; a name only some branches set is the input of that name on
  every path where none of them ran, so a read of it after the `if` reads that input.
- Within a frame, a name is bound from the statement that binds it on: a read placed before a `set`, and the
  `set`'s own right-hand side (`{% set topic = topic|trim %}`), read the input.
- A macro body runs where the macro is called, which the walk cannot place among the statements, so it sees the
  names the statement list it is defined in binds for certain, wherever they stand in it.

The walk hands every node that may read a variable to a handler, with the bindings where the node stands. A
binding maps a name to the input path it stands for when that can be followed, which is a loop target over an
attribute chain, and to None otherwise.
"""

from typing import Protocol

from jinja2 import nodes

# The segment standing for "an item of the list" in a path reached through a loop variable.
LIST_ITEM_SEGMENT = "[]"

# The names a template binds where a node stands, each mapped to the input path it stands for, or to None when it
# cannot be followed (a `set`, a macro argument, `loop`). A name absent from the bindings is an input, or a global.
ScopeBindings = dict[str, tuple[str, ...] | None]


def assigned_target_names(target: nodes.Node) -> list[str]:
    """The names a `set`, `with` or loop target binds: a plain name or a tuple of them, nested tuples included.

    A namespace attribute (`{% set ns.found = true %}`) binds no name.
    """
    if isinstance(target, nodes.Name):
        return [target.name]
    if isinstance(target, nodes.Tuple):
        return [name for item in target.items for name in assigned_target_names(item)]
    return []


def _names_assigned_by_statements(statements: list[nodes.Node]) -> set[str]:
    names: set[str] = set()
    for statement in statements:
        names |= definitely_assigned_names(statement)
    return names


def definitely_assigned_names(statement: nodes.Node) -> set[str]:
    """The names a statement leaves bound, whichever way it runs, in the frame it runs in.

    A set or a set block binds its targets, a macro its name, an import its alias; an `if` binds what every one of
    its branches binds, nothing when it has no `else`; the statements of an `autoescape` run in the frame they stand
    in; and a statement that opens a frame of its own binds nothing outside it.
    """
    if isinstance(statement, (nodes.Assign, nodes.AssignBlock)):
        return set(assigned_target_names(statement.target))
    if isinstance(statement, nodes.Macro):
        return {statement.name}
    if isinstance(statement, nodes.Import):
        return {statement.target}
    if isinstance(statement, nodes.FromImport):
        return {name[1] if isinstance(name, tuple) else name for name in statement.names}
    if isinstance(statement, nodes.If):
        if not statement.else_:
            return set()
        body_names = _names_assigned_by_statements(statement.body)
        other_branches = [*(elif_branch.body for elif_branch in statement.elif_), statement.else_]
        return body_names.intersection(*(_names_assigned_by_statements(branch) for branch in other_branches))
    if isinstance(statement, nodes.ScopedEvalContextModifier):
        return _names_assigned_by_statements(statement.body)
    return set()


def frame_bound_names(statement: nodes.Node) -> set[str]:
    """The names a statement binds in the frame it opens, before its body runs: a loop's target and `loop`, a
    `with`'s targets, and a macro's or a call block's arguments with the names Jinja provides in a macro.
    """
    if isinstance(statement, nodes.For):
        return {"loop", *assigned_target_names(statement.target)}
    if isinstance(statement, nodes.With):
        return {name for target in statement.targets for name in assigned_target_names(target)}
    if isinstance(statement, (nodes.Macro, nodes.CallBlock)):
        return {*(argument.name for argument in statement.args), "caller", "varargs", "kwargs"}
    return set()


def attribute_chain(node: nodes.Node) -> tuple[str, list[str]] | None:
    """The name and attribute names of a pure attribute chain (`a.b.c`), or None for any other shape."""
    attributes: list[str] = []
    current = node
    while isinstance(current, nodes.Getattr):
        attributes.append(current.attr)
        current = current.node
    if isinstance(current, nodes.Name):
        return current.name, list(reversed(attributes))
    return None


def resolve_bound_path(*, name: str, attributes: list[str], bindings: ScopeBindings) -> tuple[str, ...] | None:
    """The input path a chain reads, through the bindings: None when it starts from a name that cannot be followed."""
    if name not in bindings:
        return (name, *attributes)
    bound_path = bindings[name]
    if bound_path is None:
        return None
    return (*bound_path, *attributes)


class ReadHandler(Protocol):
    """Deals with a node that may read a variable, given the bindings where it stands.

    Returns True when it has dealt with the node, which is then not walked into.
    """

    def __call__(self, *, node: nodes.Node, bindings: ScopeBindings) -> bool: ...


def _with_unfollowed(*, bindings: ScopeBindings, names: set[str]) -> ScopeBindings:
    extended = dict(bindings)
    for name in names:
        extended[name] = None
    return extended


class _ReadWalk:
    def __init__(self, *, global_names: set[str], handle_read: ReadHandler) -> None:
        self.global_names = global_names
        self.handle_read = handle_read

    def walk_statements(self, *, statements: list[nodes.Node], bindings: ScopeBindings) -> ScopeBindings:
        """Walk a statement list in the frame it runs in, and return the bindings after it.

        Each statement sees what the statements before it bound for certain; a macro sees what the whole list binds.
        """
        names_bound_by_the_list = _names_assigned_by_statements(statements)
        scope = dict(bindings)
        for statement in statements:
            if isinstance(statement, nodes.Macro):
                self.walk(node=statement, bindings=_with_unfollowed(bindings=scope, names=names_bound_by_the_list))
            else:
                self.walk(node=statement, bindings=scope)
            scope = _with_unfollowed(bindings=scope, names=definitely_assigned_names(statement))
        return scope

    def walk(self, *, node: nodes.Node, bindings: ScopeBindings) -> None:
        if isinstance(node, nodes.If):
            # Every branch, and every `elif` test, starts from the bindings before the `if`
            for branch in (node, *node.elif_):
                self.walk(node=branch.test, bindings=bindings)
                self.walk_statements(statements=branch.body, bindings=bindings)
            self.walk_statements(statements=node.else_, bindings=bindings)
            return

        if isinstance(node, nodes.For):
            # The iterable is read outside the loop, the loop filter and the body inside it, and the `else` branch in
            # a frame of its own. A single loop target over an attribute chain reads an item of that chain's list
            self.walk(node=node.iter, bindings=bindings)
            loop_bindings = _with_unfollowed(bindings=bindings, names=frame_bound_names(node))
            iterated_chain = attribute_chain(node.iter)
            if isinstance(node.target, nodes.Name) and iterated_chain is not None:
                iterated_name, iterated_attributes = iterated_chain
                iterated_path = resolve_bound_path(name=iterated_name, attributes=iterated_attributes, bindings=bindings)
                if iterated_path is not None:
                    loop_bindings[node.target.name] = (*iterated_path, LIST_ITEM_SEGMENT)
            if node.test is not None:
                self.walk(node=node.test, bindings=loop_bindings)
            self.walk_statements(statements=node.body, bindings=loop_bindings)
            self.walk_statements(statements=node.else_, bindings=bindings)
            return

        if isinstance(node, nodes.With):
            # The values are read outside the `with`, before its targets are bound
            for value in node.values:
                self.walk(node=value, bindings=bindings)
            self.walk_statements(statements=node.body, bindings=_with_unfollowed(bindings=bindings, names=frame_bound_names(node)))
            return

        if isinstance(node, (nodes.Macro, nodes.CallBlock)):
            if isinstance(node, nodes.CallBlock):
                # The call is made from the enclosing frame; the block's body is the macro it passes as `caller`
                self.walk(node=node.call, bindings=bindings)
            macro_bindings = _with_unfollowed(bindings=bindings, names=frame_bound_names(node))
            # A default is evaluated in the macro's frame, where the arguments are bound
            for default in node.defaults:
                self.walk(node=default, bindings=macro_bindings)
            self.walk_statements(statements=node.body, bindings=macro_bindings)
            return

        if isinstance(node, (nodes.FilterBlock, nodes.AssignBlock)):
            # The body runs in a frame of its own, and the filter is applied in that frame once the body has run
            body_bindings = self.walk_statements(statements=node.body, bindings=bindings)
            if node.filter is not None:
                self.walk(node=node.filter, bindings=body_bindings)
            return

        if isinstance(node, (nodes.Scope, nodes.Block)):
            self.walk_statements(statements=node.body, bindings=bindings)
            return

        if isinstance(node, nodes.OverlayScope):
            self.walk(node=node.context, bindings=bindings)
            self.walk_statements(statements=node.body, bindings=bindings)
            return

        if isinstance(node, nodes.ScopedEvalContextModifier):
            # Its statements run in the frame it stands in, the scope Jinja wraps an `autoescape` in
            for option in node.options:
                self.walk(node=option, bindings=bindings)
            self.walk_statements(statements=node.body, bindings=bindings)
            return

        if isinstance(node, nodes.Name) and node.ctx != "load":
            # The target of a `set` or a `for`, and a macro argument, are written, not read
            return

        if isinstance(node, nodes.Call) and isinstance(node.node, nodes.Name) and node.node.name in self.global_names:
            # A call to a Jinja global (`range(count)`, `namespace()`) reads only its arguments. Any other read of the
            # name (`{{ range }}`, `range.low`) reads the input of that name, which shadows the global when rendered
            for child in node.iter_child_nodes():
                if child is not node.node:
                    self.walk(node=child, bindings=bindings)
            return

        if self.handle_read(node=node, bindings=bindings):
            return

        for child in node.iter_child_nodes():
            self.walk(node=child, bindings=bindings)


def walk_template_reads(*, template: nodes.Template, global_names: set[str], handle_read: ReadHandler) -> None:
    """Walk a template in Jinja's scopes, handing every node that may read a variable to `handle_read`.

    The detectors that ask which inputs a template reads, and which fields of them, all walk through here, so the
    names they treat as bound cannot drift apart.

    Args:
        template: The parsed template
        global_names: The environment's globals (`range`, `namespace`, `dict`...)
        handle_read: What to do with a node that may read a variable
    """
    _ReadWalk(global_names=global_names, handle_read=handle_read).walk_statements(statements=template.body, bindings={})
