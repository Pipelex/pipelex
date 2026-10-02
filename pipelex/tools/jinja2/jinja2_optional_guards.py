"""Guard classification for declared-optional template variables (optionals design D7).

An absent optional input is simply undefined in the Jinja context: `{% if var %}` is falsy and
`@?var` renders nothing, but a bare `{{ var }}` silently renders empty and a deep `{{ var.x }}`
raises at render time. The static companion that makes this design safe is the guard-lint: every
template reference to a declared-optional input must be *guarded* — reachable only inside a
`{% if var %}`-style block, an inline presence conditional (`... if var is defined else ...`),
or via `@?var` (whose rewritten form is a `{% if var %}` block). This module classifies the
references; validation turns the unguarded ones into `OPTIONAL_INPUT_UNGUARDED` errors.

Recognized guard shapes (kept deliberately narrow — a conservative lint with a precise fix beats
a clever one that blesses subtly unsafe templates):

- an `{% if %}` / inline-conditional test that guards the variable: the bare variable name, a
  `var is defined` test, or an `and` combination containing one of those;
- inside a test position, a bare name or a presence test (`defined` / `undefined` / `none`) is
  itself a safe reference (truthiness of an undefined name is a legal presence probe); any other
  shape rooted at an unguarded optional (deep access, filters, other tests) is unguarded.

The `{% else %}` arm of a guard is NOT guarded — it is exactly the branch that runs when the
variable is absent.
"""

from jinja2 import nodes
from jinja2.exceptions import TemplateSyntaxError
from pydantic.dataclasses import dataclass

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_scopes import definitely_assigned_names, dotted_attribute_path, frame_bound_names, names_assigned_by_statements
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

# Test names that safely probe presence on an undefined variable.
_PRESENCE_TEST_NAMES = {"defined", "undefined", "none"}


@dataclass(frozen=True)
class UnguardedOptionalReference:
    """One unguarded template reference to a declared-optional variable."""

    variable_name: str
    path: str


class _GuardWalker:
    """Recursive AST walk tracking which optional variables are currently guarded and which
    names are locally declared (loop targets, macro params, `{% set %}` assignments).

    Where a name is declared follows Jinja's scopes, from the rules `jinja2_scopes.py` states for
    every template walker: after an `if`, only a name every branch sets is declared, so an optional
    that only some branches rebind may still be read absent; a loop, a macro, a call, filter or set
    block, a `with`, an `autoescape` and a block keep what they set to their own body; a macro sees
    what its whole body binds; and a block without `scoped` reads only the template context, so
    none of the names, nor the guards on them, that the frames around it bind reach it.
    """

    def __init__(self, *, optional_variable_names: set[str]) -> None:
        self.optional_variable_names = optional_variable_names
        self.findings: list[UnguardedOptionalReference] = []
        self._seen_paths: set[str] = set()

    def _record(self, full_path: str) -> None:
        root_name = get_root_from_dotted_path(full_path)
        if full_path in self._seen_paths:
            return
        self._seen_paths.add(full_path)
        self.findings.append(UnguardedOptionalReference(variable_name=root_name, path=full_path))

    def _is_unguarded_optional(self, full_path: str, *, guarded: frozenset[str], declared: frozenset[str]) -> bool:
        """Whether the dotted path references an optional variable that is neither guarded
        nor shadowed by a local declaration.
        """
        root_name = get_root_from_dotted_path(full_path)
        return root_name in self.optional_variable_names and root_name not in guarded and root_name not in declared

    def _guard_vars(self, test_node: nodes.Node) -> frozenset[str]:
        """Variables positively guaranteed present inside the body guarded by `test_node`."""
        if isinstance(test_node, nodes.Name):
            return frozenset({test_node.name})
        if isinstance(test_node, nodes.Test) and test_node.name == "defined" and isinstance(test_node.node, nodes.Name):
            return frozenset({test_node.node.name})
        if isinstance(test_node, nodes.And):
            return self._guard_vars(test_node.left) | self._guard_vars(test_node.right)
        return frozenset()

    def _walk_test(
        self,
        test_node: nodes.Node,
        *,
        guarded: frozenset[str],
        declared: frozenset[str],
        context_declared: frozenset[str] | None,
    ) -> None:
        """Walk a test position: bare names and presence tests are safe references there."""
        if isinstance(test_node, nodes.Name):
            return
        if isinstance(test_node, nodes.Test) and test_node.name in _PRESENCE_TEST_NAMES and isinstance(test_node.node, nodes.Name):
            return
        if isinstance(test_node, nodes.And):
            # `and` short-circuits: the right operand only evaluates when the left is truthy,
            # so the left operand's guard extends over the right (`{% if var and var.attr %}`).
            self._walk_test(test_node.left, guarded=guarded, declared=declared, context_declared=context_declared)
            right_guarded = guarded | self._guard_vars(test_node.left)
            self._walk_test(test_node.right, guarded=right_guarded, declared=declared, context_declared=context_declared)
            return
        if isinstance(test_node, nodes.Or):
            self._walk_test(test_node.left, guarded=guarded, declared=declared, context_declared=context_declared)
            self._walk_test(test_node.right, guarded=guarded, declared=declared, context_declared=context_declared)
            return
        if isinstance(test_node, nodes.Not):
            self._walk_test(test_node.node, guarded=guarded, declared=declared, context_declared=context_declared)
            return
        self.walk(test_node, guarded=guarded, declared=declared, context_declared=context_declared)

    def _walk_body(
        self,
        body_nodes: list[nodes.Node],
        *,
        guarded: frozenset[str],
        declared: frozenset[str],
        context_declared: frozenset[str] | None,
    ) -> frozenset[str]:
        """Walk a statement body sequentially, and return the names declared after it.

        What a statement binds for certain (a `{% set %}`, a `{% macro %}`, a name every branch of an
        `if` sets) is declared for SUBSEQUENT statements only — a read occurring before the assignment
        still refers to the (possibly undefined) context value and must be classified against it. A
        macro runs where it is called, so it sees what the whole body binds for certain.
        `context_declared` is what the template context holds where the body runs, and None at the top
        level, whose names the context takes on as they are set.
        """
        names_bound_by_the_body = frozenset(names_assigned_by_statements(body_nodes))
        for body_node in body_nodes:
            if isinstance(body_node, nodes.Assign):
                # The assignment's right-hand side is evaluated against the current scope; the
                # target is a store, never a read.
                self.walk(body_node.node, guarded=guarded, declared=declared, context_declared=context_declared)
            elif isinstance(body_node, nodes.AssignBlock):
                # `{% set x %}...{% endset %}`: the body runs in a frame of its own, so what it sets
                # stays in it, and the filter is applied in that frame once the body has run; the
                # target is a store, never a read.
                frame_context = declared if context_declared is None else context_declared
                body_declared = self._walk_body(body_node.body, guarded=guarded, declared=declared, context_declared=frame_context)
                if body_node.filter is not None:
                    self.walk(body_node.filter, guarded=guarded, declared=body_declared, context_declared=frame_context)
            elif isinstance(body_node, nodes.Macro):
                self.walk(body_node, guarded=guarded, declared=declared | names_bound_by_the_body, context_declared=context_declared)
            else:
                self.walk(body_node, guarded=guarded, declared=declared, context_declared=context_declared)
            declared |= definitely_assigned_names(body_node)
        return declared

    def walk(
        self,
        node: nodes.Node,
        *,
        guarded: frozenset[str],
        declared: frozenset[str],
        context_declared: frozenset[str] | None,
    ) -> None:
        # What the template context holds in a frame opened here: from the top level, what is declared where it opens
        frame_context = declared if context_declared is None else context_declared

        if isinstance(node, nodes.Template):
            self._walk_body(node.body, guarded=guarded, declared=declared, context_declared=context_declared)
            return

        if isinstance(node, nodes.If):
            body_guarded = guarded | self._guard_vars(node.test)
            self._walk_test(node.test, guarded=guarded, declared=declared, context_declared=context_declared)
            self._walk_body(node.body, guarded=body_guarded, declared=declared, context_declared=context_declared)
            for elif_node in node.elif_:
                self.walk(elif_node, guarded=guarded, declared=declared, context_declared=context_declared)
            self._walk_body(node.else_, guarded=guarded, declared=declared, context_declared=context_declared)
            return

        if isinstance(node, nodes.For):
            # The iterable is evaluated before the loop targets bind.
            self.walk(node.iter, guarded=guarded, declared=declared, context_declared=context_declared)
            loop_declared = declared | frame_bound_names(node)
            if node.test is not None:
                # The loop filter evaluates after the target binds per item, so a shadowing
                # target stays a local while an optional read in the filter gets classified.
                # Its guard vars deliberately do NOT bless the body (same conservative stance
                # as else-arms and inverted guards).
                self._walk_test(node.test, guarded=guarded, declared=loop_declared, context_declared=frame_context)
            self._walk_body(node.body, guarded=guarded, declared=loop_declared, context_declared=frame_context)
            self._walk_body(node.else_, guarded=guarded, declared=declared, context_declared=frame_context)
            return

        if isinstance(node, nodes.With):
            # The bound values are evaluated before the targets bind; the body then reads the
            # locals, never the shadowed optionals. Walking the targets as children would
            # miscount the store-context Names as reads.
            for value in node.values:
                self.walk(value, guarded=guarded, declared=declared, context_declared=context_declared)
            with_declared = declared | frame_bound_names(node)
            self._walk_body(node.body, guarded=guarded, declared=with_declared, context_declared=frame_context)
            return

        if isinstance(node, (nodes.Macro, nodes.CallBlock)):
            if isinstance(node, nodes.CallBlock):
                # The call is made from the enclosing scope; the block's body is the macro it passes as `caller`.
                self.walk(node.call, guarded=guarded, declared=declared, context_declared=context_declared)
            # The arguments are locals of the macro, and a default is evaluated where they are bound.
            macro_declared = declared | frame_bound_names(node)
            for default in node.defaults:
                self.walk(default, guarded=guarded, declared=macro_declared, context_declared=frame_context)
            self._walk_body(node.body, guarded=guarded, declared=macro_declared, context_declared=frame_context)
            return

        if isinstance(node, nodes.FilterBlock):
            # The body runs in a frame of its own, so what it sets stays in it, and the filter is
            # applied in that frame once the body has run.
            body_declared = self._walk_body(node.body, guarded=guarded, declared=declared, context_declared=frame_context)
            self.walk(node.filter, guarded=guarded, declared=body_declared, context_declared=frame_context)
            return

        if isinstance(node, nodes.Scope):
            # `{% autoescape %}` parses into a scope: a frame of its own.
            self._walk_body(node.body, guarded=guarded, declared=declared, context_declared=frame_context)
            return

        if isinstance(node, nodes.OverlayScope):
            self.walk(node.context, guarded=guarded, declared=declared, context_declared=context_declared)
            self._walk_body(node.body, guarded=guarded, declared=declared, context_declared=frame_context)
            return

        if isinstance(node, nodes.ScopedEvalContextModifier):
            # Its statements run in the frame it stands in.
            for option in node.options:
                self.walk(option, guarded=guarded, declared=declared, context_declared=context_declared)
            self._walk_body(node.body, guarded=guarded, declared=declared, context_declared=context_declared)
            return

        if isinstance(node, nodes.Block):
            if node.scoped:
                # Called with a context derived from the names declared where it stands, which is
                # then the context of the blocks nested in it.
                self._walk_body(node.body, guarded=guarded, declared=declared, context_declared=declared)
            else:
                # Called with the template context alone: a guard on a name a frame around it binds
                # tested that local, not the context's value the block reads.
                block_guarded = guarded - (declared - frame_context)
                self._walk_body(node.body, guarded=block_guarded, declared=frame_context, context_declared=frame_context)
            return

        if isinstance(node, nodes.CondExpr):
            expr1_guarded = guarded | self._guard_vars(node.test)
            self._walk_test(node.test, guarded=guarded, declared=declared, context_declared=context_declared)
            self.walk(node.expr1, guarded=expr1_guarded, declared=declared, context_declared=context_declared)
            if node.expr2 is not None:
                self.walk(node.expr2, guarded=guarded, declared=declared, context_declared=context_declared)
            return

        if isinstance(node, nodes.Name) and node.ctx != "load":
            # The target of a `set` or a `for`, and a macro argument, are written, not read.
            return

        if isinstance(node, (nodes.Name, nodes.Getattr)):
            full_path = dotted_attribute_path(node)
            if full_path is None:
                # Not a plain Name/Getattr chain (e.g. an attribute on a subscript or call
                # result): keep walking inward so inner references still get classified.
                for child in node.iter_child_nodes():
                    self.walk(child, guarded=guarded, declared=declared, context_declared=context_declared)
                return
            if self._is_unguarded_optional(full_path, guarded=guarded, declared=declared):
                self._record(full_path)
            # Never recurse into a resolvable Name/Getattr chain: the full path is the reference.
            return

        for child in node.iter_child_nodes():
            self.walk(child, guarded=guarded, declared=declared, context_declared=context_declared)


def detect_unguarded_optional_references(
    *,
    template_category: TemplateCategory,
    template_source: str,
    optional_variable_names: set[str],
) -> list[UnguardedOptionalReference]:
    """Return every unguarded reference to a declared-optional variable in the template.

    Args:
        template_category: Category of the template (LLM_PROMPT, EXPRESSION, etc.)
        template_source: Jinja2 template source (sigils already rewritten to Jinja2).
        optional_variable_names: Root names of the pipe's declared-optional (`?`) inputs.

    Returns:
        One entry per distinct unguarded dotted path, in template order.

    Raises:
        Jinja2DetectVariablesError: If the template cannot be parsed.
    """
    if not optional_variable_names:
        return []
    jinja2_env = make_jinja2_env_without_loader(template_category=template_category)
    try:
        parsed_ast = jinja2_env.parse(template_source)
    except TemplateSyntaxError as syntax_error:
        msg = f"Jinja2 guard lint — syntax error: '{syntax_error}', template_category: {template_category}, template_source:\n{template_source}"
        raise Jinja2DetectVariablesError(msg) from syntax_error

    walker = _GuardWalker(optional_variable_names=optional_variable_names)
    walker.walk(parsed_ast, guarded=frozenset(), declared=frozenset(), context_declared=None)
    return walker.findings
