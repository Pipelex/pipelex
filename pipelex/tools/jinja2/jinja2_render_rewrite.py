"""Rewrite a parsed template so that what no sandbox hook reaches is charged to the render's budget.

Six constructs compile to plain Python, with no hook the sandbox could use to charge them:

- iterating a `{% for %}` loop, which an empty loop body makes free;
- joining with `~`;
- comparing (`==`, `<`, `in` and the rest);
- slicing (`value[a:b]`), which bypasses the sandbox's `getitem`;
- writing out a list, a tuple or a dict (`[a, b]`, `(a, b)`, `{k: v}`), which a loop rebuilds;
- emitting the template's own static text, which a loop repeats.

`PipelexTemplateEnvironment._generate`, the hook Jinja documents for this, runs the parsed template
through `rewrite_for_render_budget` before compiling it, so that each goes through one of the charging
filters of `jinja2_render_charging.py`. Static text becomes a constant marked safe, which the
environment's `finalize` charges without escaping it. The rewrite changes what is charged, never what
a template renders.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jinja2 import nodes
from jinja2.visitor import NodeTransformer
from typing_extensions import override

from pipelex.tools.jinja2.jinja2_render_charging import (
    COMPARE_FILTER,
    COMPARED_FILTER,
    CONCAT_FILTER,
    ITERATE_FILTER,
    LITERAL_FILTER,
    SLICED_FILTER,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _charging_filter(*, node: nodes.Node, name: str, args: list[nodes.Expr] | None = None) -> nodes.Filter:
    return nodes.Filter(node, name, args or [], [], None, None, lineno=node.lineno)


def _is_charging_filter(*, node: nodes.Node, name: str) -> bool:
    return isinstance(node, nodes.Filter) and node.name == name


class _RenderBudgetRewriter(NodeTransformer):
    """Route loops, `~`, comparisons, slices, literals and static text through the budget's charging filters."""

    @override
    def get_visitor(self, node: nodes.Node) -> Callable[..., Any] | None:
        match node:
            case nodes.For():
                return self._rewrite_loop
            case nodes.Concat():
                return self._rewrite_concat
            case nodes.Compare():
                return self._rewrite_comparison
            case nodes.Getitem():
                return self._rewrite_item
            case nodes.Filter():
                return self._rewrite_filter
            case nodes.Output():
                return self._rewrite_output
            case nodes.List() | nodes.Dict():
                return self._rewrite_literal
            case nodes.Tuple():
                # A tuple is also what a `for` loop or a `set` unpacks into, which builds nothing.
                return self._rewrite_literal if node.ctx == "load" else None
            case _:
                return None

    def _rewrite_loop(self, node: nodes.For) -> nodes.Node:
        self.generic_visit(node)
        if not _is_charging_filter(node=node.iter, name=ITERATE_FILTER):
            node.iter = _charging_filter(node=node.iter, name=ITERATE_FILTER)
        return node

    def _rewrite_concat(self, node: nodes.Concat) -> nodes.Node:
        self.generic_visit(node)
        return _charging_filter(node=nodes.List(node.nodes, lineno=node.lineno), name=CONCAT_FILTER)

    def _rewrite_comparison(self, node: nodes.Compare) -> nodes.Node:
        self.generic_visit(node)
        if len(node.ops) == 1:
            operand = node.ops[0]
            return _charging_filter(node=node.expr, name=COMPARE_FILTER, args=[nodes.Const(operand.op, lineno=node.lineno), operand.expr])
        # A chained comparison evaluates each operand once and stops at the first false link, so its
        # operands are charged one by one rather than the comparison as a whole.
        if not _is_charging_filter(node=node.expr, name=COMPARED_FILTER):
            node.expr = _charging_filter(node=node.expr, name=COMPARED_FILTER)
        for operand in node.ops:
            if not _is_charging_filter(node=operand.expr, name=COMPARED_FILTER):
                operand.expr = _charging_filter(node=operand.expr, name=COMPARED_FILTER)
        return node

    def _rewrite_item(self, node: nodes.Getitem) -> nodes.Node:
        self.generic_visit(node)
        if isinstance(node.arg, nodes.Slice):
            return _charging_filter(node=node, name=SLICED_FILTER)
        return node

    def _rewrite_literal(self, node: nodes.List | nodes.Tuple | nodes.Dict) -> nodes.Node:
        self.generic_visit(node)
        return _charging_filter(node=node, name=LITERAL_FILTER)

    def _rewrite_filter(self, node: nodes.Filter) -> nodes.Node:
        if (node.name == SLICED_FILTER and isinstance(node.node, nodes.Getitem)) or (
            node.name in {LITERAL_FILTER, CONCAT_FILTER} and isinstance(node.node, (nodes.List, nodes.Tuple, nodes.Dict))
        ):
            # A construct already wrapped: visit what it holds, not the construct again.
            self.generic_visit(node.node)
            node.args = [self.visit(argument) for argument in node.args]
            return node
        self.generic_visit(node)
        return node

    def _rewrite_output(self, node: nodes.Output) -> nodes.Node:
        self.generic_visit(node)
        children: list[Any] = []
        for child in node.nodes:
            if isinstance(child, nodes.TemplateData):
                constant = nodes.Const(child.data, lineno=child.lineno)
                children.append(nodes.MarkSafeIfAutoescape(constant, lineno=child.lineno))
            else:
                children.append(child)
        node.nodes = children
        return node


def rewrite_for_render_budget(template: nodes.Template) -> nodes.Template:
    """Rewrite a parsed template in place for the render budget, and return it."""
    rewritten = _RenderBudgetRewriter().visit(template)
    if not isinstance(rewritten, nodes.Template):
        msg = f"Rewriting a template for the render budget returned a '{type(rewritten).__name__}'"
        raise TypeError(msg)
    return rewritten
