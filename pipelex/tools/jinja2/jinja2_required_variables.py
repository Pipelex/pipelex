from dataclasses import dataclass, field

from jinja2 import nodes
from jinja2.exceptions import (
    TemplateSyntaxError,
    UndefinedError,
)

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_errors import Jinja2DetectVariablesError, Jinja2StuffError
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


@dataclass
class VariableReference:
    """Represents a variable reference in a Jinja2 template with its applied filters.

    Attributes:
        path: The full dotted path to the variable (e.g., "document.cover", "pages")
        filters: List of filter names applied to this variable (e.g., ["with_images", "tag"])
    """

    path: str
    filters: list[str] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]


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


def _collect_declarations_from_body(body: list[nodes.Node]) -> set[str]:
    """Pre-scan a list of nodes to collect all declarations made at this scope level.

    This handles {% set %} and {% macro %} declarations that should be visible
    to all subsequent nodes in the same scope.
    """
    declarations: set[str] = set()
    for node in body:
        if isinstance(node, nodes.Assign):
            if isinstance(node.target, nodes.Name):
                declarations.add(node.target.name)
        elif isinstance(node, nodes.Macro):
            declarations.add(node.name)
    return declarations


def _collect_full_variable_paths(node: nodes.Node, paths: set[str], declared_names: set[str]) -> None:
    """Recursively walk the AST and collect full variable paths.

    This function collects only the FULL (leaf) paths for each variable access chain.
    For example, `{{ foo.bar.baz }}` will only return `foo.bar.baz`, not intermediate
    paths like `foo.bar` or `foo`.

    Args:
        node: The current AST node
        paths: Set to collect discovered paths
        declared_names: Set of locally declared names (loop variables, macro params, etc.)
    """
    # Track locally declared variables that apply to this node's children
    local_declared: set[str] = set()

    # For Template nodes, pre-scan body to find all declarations at this scope
    if isinstance(node, nodes.Template):
        local_declared.update(_collect_declarations_from_body(node.body))

    if isinstance(node, nodes.For):
        # Loop variable is locally declared
        if isinstance(node.target, nodes.Name):
            local_declared.add(node.target.name)
        elif isinstance(node.target, nodes.Tuple):
            for item in node.target.items:
                if isinstance(item, nodes.Name):
                    local_declared.add(item.name)
        # The special 'loop' variable is available inside for loops
        local_declared.add("loop")

    if isinstance(node, nodes.Macro):
        # Macro parameters are locally declared (within the macro body)
        local_declared.update(arg.name for arg in node.args)

    # Merge local declarations
    new_declared = declared_names | local_declared

    # Check if this is a Name or Getattr node that represents a variable access
    # We only add the path and DON'T recurse into Name/Getattr children to avoid
    # adding intermediate paths (e.g., for `foo.bar`, we only want `foo.bar`, not also `foo`)
    if isinstance(node, (nodes.Name, nodes.Getattr)):
        full_path = _build_full_path(node)
        if full_path:
            root_name = get_root_from_dotted_path(full_path)
            # Only add if the root is not a declared local variable
            if root_name not in new_declared:
                paths.add(full_path)
        # Don't recurse into Name/Getattr children - we've captured the full path
        return

    # Recurse into child nodes (only for non-Name/Getattr nodes)
    for child in node.iter_child_nodes():
        _collect_full_variable_paths(child, paths, new_declared)


def detect_jinja2_required_variables(
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
    _collect_full_variable_paths(parsed_ast, paths, set())
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


def _collect_variable_references(
    node: nodes.Node,
    references: dict[str, VariableReference],
    declared_names: set[str],
) -> None:
    """Recursively walk the AST and collect variable references with their filters.

    This function collects VariableReference objects containing the full path
    and any filters applied to each variable. If the same variable is referenced
    multiple times with different filters, all filters are combined.

    Args:
        node: The current AST node
        references: Dict to collect discovered references (path -> VariableReference)
        declared_names: Set of locally declared names (loop variables, macro params, etc.)
    """
    local_declared: set[str] = set()

    if isinstance(node, nodes.Template):
        local_declared.update(_collect_declarations_from_body(node.body))

    if isinstance(node, nodes.For):
        if isinstance(node.target, nodes.Name):
            local_declared.add(node.target.name)
        elif isinstance(node.target, nodes.Tuple):
            for item in node.target.items:
                if isinstance(item, nodes.Name):
                    local_declared.add(item.name)
        local_declared.add("loop")

    if isinstance(node, nodes.Macro):
        local_declared.update(arg.name for arg in node.args)

    new_declared = declared_names | local_declared

    # Handle Filter nodes - extract filters and find the base variable
    if isinstance(node, nodes.Filter):
        filters, base_node = _extract_filters_and_variable(node)
        if base_node is None:
            return
        full_path = _build_full_path(base_node)
        if full_path:
            root_name = get_root_from_dotted_path(full_path)
            if root_name not in new_declared:
                if full_path in references:
                    # Extend existing filters (avoid duplicates)
                    for filter_name in filters:
                        if filter_name not in references[full_path].filters:
                            references[full_path].filters.append(filter_name)
                else:
                    references[full_path] = VariableReference(path=full_path, filters=filters)
        # Don't recurse into the Filter chain - we've already processed it
        return

    # Handle plain Name or Getattr nodes (no filter applied)
    if isinstance(node, (nodes.Name, nodes.Getattr)):
        full_path = _build_full_path(node)
        if full_path:
            root_name = get_root_from_dotted_path(full_path)
            if root_name not in new_declared:
                if full_path not in references:
                    references[full_path] = VariableReference(path=full_path, filters=[])
        return

    # Recurse into child nodes
    for child in node.iter_child_nodes():
        _collect_variable_references(child, references, new_declared)


def detect_jinja2_variable_references(
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
    _collect_variable_references(parsed_ast, references, set())
    return list(references.values())
