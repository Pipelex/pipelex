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

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

# Test names that safely probe presence on an undefined variable.
_PRESENCE_TEST_NAMES = {"defined", "undefined", "none"}


@dataclass(frozen=True)
class UnguardedOptionalReference:
    """One unguarded template reference to a declared-optional variable."""

    variable_name: str
    path: str


def _build_full_path(node: nodes.Node) -> str | None:
    """Build the dotted path of a Name / Getattr chain, or None for unsupported shapes."""
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Getattr):
        parent_path = _build_full_path(node.node)
        if parent_path is not None:
            return f"{parent_path}.{node.attr}"
    return None


class _GuardWalker:
    """Recursive AST walk tracking which optional variables are currently guarded and which
    names are locally declared (loop targets, macro params, `{% set %}` assignments).
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

    def _walk_test(self, test_node: nodes.Node, *, guarded: frozenset[str], declared: frozenset[str]) -> None:
        """Walk a test position: bare names and presence tests are safe references there."""
        if isinstance(test_node, nodes.Name):
            return
        if isinstance(test_node, nodes.Test) and test_node.name in _PRESENCE_TEST_NAMES and isinstance(test_node.node, nodes.Name):
            return
        if isinstance(test_node, nodes.And):
            # `and` short-circuits: the right operand only evaluates when the left is truthy,
            # so the left operand's guard extends over the right (`{% if var and var.attr %}`).
            self._walk_test(test_node.left, guarded=guarded, declared=declared)
            self._walk_test(test_node.right, guarded=guarded | self._guard_vars(test_node.left), declared=declared)
            return
        if isinstance(test_node, nodes.Or):
            self._walk_test(test_node.left, guarded=guarded, declared=declared)
            self._walk_test(test_node.right, guarded=guarded, declared=declared)
            return
        if isinstance(test_node, nodes.Not):
            self._walk_test(test_node.node, guarded=guarded, declared=declared)
            return
        self.walk(test_node, guarded=guarded, declared=declared)

    def _walk_body(self, body_nodes: list[nodes.Node], *, guarded: frozenset[str], declared: frozenset[str]) -> None:
        """Walk a statement body sequentially: a `{% set %}` or `{% macro %}` declares its name
        for SUBSEQUENT statements only — a read occurring before the assignment still refers to
        the (possibly undefined) context value and must be classified against it.
        """
        for body_node in body_nodes:
            if isinstance(body_node, nodes.Assign):
                # The assignment's right-hand side is evaluated against the current scope.
                self.walk(body_node.node, guarded=guarded, declared=declared)
                declared |= self._assign_target_names(body_node.target)
                continue
            if isinstance(body_node, nodes.AssignBlock):
                # `{% set x %}...{% endset %}`: the body (and filter) evaluate against the
                # current scope; the target declares for subsequent statements only — and the
                # target itself is a store, never a read.
                self._walk_body(body_node.body, guarded=guarded, declared=declared)
                if body_node.filter is not None:
                    self.walk(body_node.filter, guarded=guarded, declared=declared)
                declared |= self._assign_target_names(body_node.target)
                continue
            if isinstance(body_node, nodes.Macro):
                declared |= {body_node.name}
            self.walk(body_node, guarded=guarded, declared=declared)

    @classmethod
    def _assign_target_names(cls, target: nodes.Node) -> frozenset[str]:
        """The names a `{% set %}` target declares — a plain Name or a Tuple of Names."""
        if isinstance(target, nodes.Name):
            return frozenset({target.name})
        if isinstance(target, nodes.Tuple):
            return frozenset(item.name for item in target.items if isinstance(item, nodes.Name))
        return frozenset()

    def walk(self, node: nodes.Node, *, guarded: frozenset[str], declared: frozenset[str]) -> None:
        if isinstance(node, nodes.Template):
            self._walk_body(node.body, guarded=guarded, declared=declared)
            return

        if isinstance(node, nodes.If):
            body_guarded = guarded | self._guard_vars(node.test)
            self._walk_test(node.test, guarded=guarded, declared=declared)
            self._walk_body(node.body, guarded=body_guarded, declared=declared)
            for elif_node in node.elif_:
                self.walk(elif_node, guarded=guarded, declared=declared)
            self._walk_body(node.else_, guarded=guarded, declared=declared)
            return

        if isinstance(node, nodes.For):
            # The iterable is evaluated before the loop targets bind.
            self.walk(node.iter, guarded=guarded, declared=declared)
            loop_declared: set[str] = {"loop"}
            if isinstance(node.target, nodes.Name):
                loop_declared.add(node.target.name)
            elif isinstance(node.target, nodes.Tuple):
                for item in node.target.items:
                    if isinstance(item, nodes.Name):
                        loop_declared.add(item.name)
            self._walk_body(node.body, guarded=guarded, declared=declared | loop_declared)
            self._walk_body(node.else_, guarded=guarded, declared=declared)
            return

        if isinstance(node, nodes.Macro):
            macro_declared = frozenset(arg.name for arg in node.args)
            self._walk_body(node.body, guarded=guarded, declared=declared | macro_declared)
            return

        if isinstance(node, nodes.CondExpr):
            expr1_guarded = guarded | self._guard_vars(node.test)
            self._walk_test(node.test, guarded=guarded, declared=declared)
            self.walk(node.expr1, guarded=expr1_guarded, declared=declared)
            if node.expr2 is not None:
                self.walk(node.expr2, guarded=guarded, declared=declared)
            return

        if isinstance(node, (nodes.Name, nodes.Getattr)):
            full_path = _build_full_path(node)
            if full_path is None:
                # Not a plain Name/Getattr chain (e.g. an attribute on a subscript or call
                # result): keep walking inward so inner references still get classified.
                for child in node.iter_child_nodes():
                    self.walk(child, guarded=guarded, declared=declared)
                return
            if self._is_unguarded_optional(full_path, guarded=guarded, declared=declared):
                self._record(full_path)
            # Never recurse into a resolvable Name/Getattr chain: the full path is the reference.
            return

        for child in node.iter_child_nodes():
            self.walk(child, guarded=guarded, declared=declared)


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
    walker.walk(parsed_ast, guarded=frozenset(), declared=frozenset())
    return walker.findings
