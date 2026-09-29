from dataclasses import field
from typing import Protocol

from jinja2 import nodes
from jinja2.exceptions import (
    TemplateSyntaxError,
    UndefinedError,
)
from pydantic.dataclasses import dataclass

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError, Jinja2StuffError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


@dataclass
class VariableReference:
    """Represents a variable reference in a Jinja2 template with its applied filters.

    Mutated in place: ``detect_jinja2_variable_references`` extends ``.filters``
    on re-seen variables, so this is intentionally NOT frozen.

    Attributes:
        path: The full dotted path to the variable (e.g., "document.cover", "pages")
        filters: List of filter names applied to this variable (e.g., ["with_images", "tag"])
    """

    path: str
    filters: list[str] = field(default_factory=list[str])


def _build_full_path(node: nodes.Node) -> str | None:
    """Recursively build the full dotted path from a Getattr or Name node.

    Args:
        node: A Jinja2 AST node (Name or Getattr)

    Returns:
        The full dotted path as a string, or None if the node structure is not supported.
    """
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Getattr):
        parent_path = _build_full_path(node.node)
        if parent_path is not None:
            return f"{parent_path}.{node.attr}"
    return None


def _set_target_name(*, statement: nodes.Node) -> str | None:
    """The name a `{% set %}` or a `{% set %}…{% endset %}` block assigns, when it assigns a plain name."""
    if isinstance(statement, (nodes.Assign, nodes.AssignBlock)) and isinstance(statement.target, nodes.Name):
        return statement.target.name
    return None


class _ReadHandler(Protocol):
    """Deals with a node that may read a variable, given the names declared where it stands.

    Returns True when it has dealt with the node, which is then not walked into.
    """

    def __call__(self, *, node: nodes.Node, declared_names: set[str]) -> bool: ...


def _walk_reads(*, node: nodes.Node, declared_names: set[str], global_names: set[str], handle_read: _ReadHandler) -> None:
    """Walk a template's AST in Jinja's scopes, handing every node that may read a variable to ``handle_read``.

    Both detectors below walk through here, so the names they treat as declared cannot drift apart: the required
    variables the input check compares with the inputs, and the references that attach images and documents.

    Args:
        node: The current AST node
        declared_names: The names declared where the node stands (a `set` before it, a loop target, a macro argument)
        global_names: The environment's globals (`range`, `namespace`, `dict`...)
        handle_read: What to do with a node that may read a variable
    """
    if isinstance(node, nodes.Template):
        # A macro's name is never an input, and a macro body, which runs when the macro is called, sees every
        # top-level `set`. Elsewhere a `set` declares its name only from its own statement on:
        # `{% set topic = topic|trim %}` reads the incoming `topic`, and so does a read placed before the `set`
        top_level_set_names = {name for statement in node.body if (name := _set_target_name(statement=statement)) is not None}
        scope_declared = declared_names | {statement.name for statement in node.body if isinstance(statement, nodes.Macro)}
        for statement in node.body:
            statement_declared = scope_declared | top_level_set_names if isinstance(statement, nodes.Macro) else scope_declared
            _walk_reads(node=statement, declared_names=statement_declared, global_names=global_names, handle_read=handle_read)
            if (name := _set_target_name(statement=statement)) is not None:
                scope_declared.add(name)
        return

    if isinstance(node, nodes.For):
        # The iterable and the `else` branch are read outside the loop, the body and the loop filter inside it,
        # where the loop target and the special `loop` variable are declared
        loop_declared = declared_names | {"loop"}
        if isinstance(node.target, nodes.Name):
            loop_declared.add(node.target.name)
        elif isinstance(node.target, nodes.Tuple):
            loop_declared.update(item.name for item in node.target.items if isinstance(item, nodes.Name))
        # Walked in source order, which is the order the image references are attached in
        scoped_nodes = [
            (node.iter, declared_names),
            *((statement, loop_declared) for statement in node.body),
            *((statement, declared_names) for statement in node.else_),
            *([(node.test, loop_declared)] if node.test is not None else []),
        ]
        for scoped_node, scope_declared_names in scoped_nodes:
            _walk_reads(node=scoped_node, declared_names=scope_declared_names, global_names=global_names, handle_read=handle_read)
        return

    if isinstance(node, nodes.Macro):
        # Macro parameters, and the names Jinja provides inside a macro body, are locally declared
        declared_names = declared_names | {arg.name for arg in node.args} | {"caller", "varargs", "kwargs"}

    if isinstance(node, nodes.Name) and node.ctx != "load":
        # The target of a `set` or a `for` is written, not read
        return

    if isinstance(node, nodes.Call) and isinstance(node.node, nodes.Name) and node.node.name in global_names:
        # A call to a Jinja global (`range(count)`, `namespace()`) reads only its arguments. Any other read of the
        # name (`{{ range }}`, `range.low`) reads the input of that name, which shadows the global when rendered
        for child in node.iter_child_nodes():
            if child is not node.node:
                _walk_reads(node=child, declared_names=declared_names, global_names=global_names, handle_read=handle_read)
        return

    if handle_read(node=node, declared_names=declared_names):
        return

    for child in node.iter_child_nodes():
        _walk_reads(node=child, declared_names=declared_names, global_names=global_names, handle_read=handle_read)


def detect_jinja2_required_variables(
    *,
    template_category: TemplateCategory,
    template_source: str,
) -> set[str]:
    """Returns the set of full variable paths required by the Jinja2 template.

    For example, `{{ user.profile.name }}` returns a set containing `user.profile.name`.

    Args:
        template_category: Category of the template (HTML, MARKDOWN, etc.)
        template_source: Jinja2 template string

    Returns:
        Set of full dotted variable paths required by the template

    Raises:
        Jinja2DetectVariablesError: If there is an error parsing the template
    """
    jinja2_env = make_jinja2_env_without_loader(
        template_category=template_category,
    )

    try:
        parsed_ast = jinja2_env.parse(template_source)
    except Jinja2StuffError as stuff_error:
        msg = f"Jinja2 detect variables — stuff error: '{stuff_error}', template_category: {template_category}, template_source:\n{template_source}"
        raise Jinja2DetectVariablesError(msg) from stuff_error
    except TemplateSyntaxError as syntax_error:
        msg = f"Jinja2 detect variables — syntax error: '{syntax_error}', template_category: {template_category}, template_source:\n{template_source}"
        raise Jinja2DetectVariablesError(msg) from syntax_error
    except UndefinedError as undef_error:
        msg = (
            f"Jinja2 detect variables — undefined error: '{undef_error}', template_category: {template_category}, template_source:\n{template_source}"
        )
        raise Jinja2DetectVariablesError(msg) from undef_error

    paths: set[str] = set()

    def collect_full_path(*, node: nodes.Node, declared_names: set[str]) -> bool:
        # Only the full path of an access chain is collected: `{{ foo.bar.baz }}` gives `foo.bar.baz`, not `foo.bar` or `foo`
        if not isinstance(node, (nodes.Name, nodes.Getattr)):
            return False
        full_path = _build_full_path(node)
        if full_path is None:
            # An attribute on a subscript, a call or a filter (`items[0].text`) reads the path its chain starts from
            return False
        if get_root_from_dotted_path(full_path) not in declared_names:
            paths.add(full_path)
        return True

    _walk_reads(node=parsed_ast, declared_names=set(), global_names=set(jinja2_env.globals), handle_read=collect_full_path)
    return paths


def _extract_filters_and_variable(node: nodes.Node) -> tuple[list[str], nodes.Node | None]:
    """Extract filter names and the base variable from a filter chain.

    For `{{ foo | bar | baz }}`, returns (["bar", "baz"], Name("foo")).
    The filters are returned in application order (innermost first).

    Args:
        node: A Jinja2 AST node (possibly a Filter node)

    Returns:
        Tuple of (list of filter names, base variable node or None)
    """
    filters: list[str] = []
    current_node: nodes.Node | None = node

    while isinstance(current_node, nodes.Filter):
        filters.append(current_node.name)
        current_node = current_node.node

    return filters, current_node


def detect_jinja2_variable_references(
    *,
    template_category: TemplateCategory,
    template_source: str,
) -> list[VariableReference]:
    """Returns variable references in the Jinja2 template with their applied filters.

    For example, `{{ user.profile | tag }}` returns a VariableReference with
    path="user.profile" and filters=["tag"].

    Args:
        template_category: Category of the template (HTML, MARKDOWN, etc.)
        template_source: Jinja2 template string

    Returns:
        List of VariableReference objects found in the template

    Raises:
        Jinja2DetectVariablesError: If there is an error parsing the template
    """
    jinja2_env = make_jinja2_env_without_loader(
        template_category=template_category,
    )

    try:
        parsed_ast = jinja2_env.parse(template_source)
    except Jinja2StuffError as stuff_error:
        msg = f"Jinja2 detect variables — stuff error: '{stuff_error}', template_category: {template_category}, template_source:\n{template_source}"
        raise Jinja2DetectVariablesError(msg) from stuff_error
    except TemplateSyntaxError as syntax_error:
        msg = f"Jinja2 detect variables — syntax error: '{syntax_error}', template_category: {template_category}, template_source:\n{template_source}"
        raise Jinja2DetectVariablesError(msg) from syntax_error
    except UndefinedError as undef_error:
        msg = (
            f"Jinja2 detect variables — undefined error: '{undef_error}', template_category: {template_category}, template_source:\n{template_source}"
        )
        raise Jinja2DetectVariablesError(msg) from undef_error

    references: dict[str, VariableReference] = {}

    def collect_reference(*, node: nodes.Node, declared_names: set[str]) -> bool:
        # A filter chain is taken whole, with its filter names; a chain or a path that stops at a subscript or a
        # call (`items[0].image`) gives no reference, since no image or document can be resolved from it
        if isinstance(node, nodes.Filter):
            filters, base_node = _extract_filters_and_variable(node)
        elif isinstance(node, (nodes.Name, nodes.Getattr)):
            filters, base_node = [], node
        else:
            return False
        full_path = _build_full_path(base_node) if base_node is not None else None
        if full_path is None or get_root_from_dotted_path(full_path) in declared_names:
            return True
        if full_path in references:
            # The same variable referenced several times combines its filters
            for filter_name in filters:
                if filter_name not in references[full_path].filters:
                    references[full_path].filters.append(filter_name)
        else:
            references[full_path] = VariableReference(path=full_path, filters=filters)
        return True

    _walk_reads(node=parsed_ast, declared_names=set(), global_names=set(jinja2_env.globals), handle_read=collect_reference)
    return list(references.values())
