from jinja2 import nodes
from jinja2.exceptions import (
    TemplateSyntaxError,
    UndefinedError,
)

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_errors import Jinja2DetectVariablesError, Jinja2StuffError
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


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
