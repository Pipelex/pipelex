"""The variables a template reads from its inputs, and the references through which it attaches images and documents.

Both detectors are handlers on the read walk of `jinja2_scopes.py`, which follows Jinja's own scopes: a name the
template binds (a `{% set %}`, a loop target, a macro argument) is not reported where Jinja binds it, and is
reported as the input of that name everywhere else, such as after an `if` whose branches do not all set it.
"""

from dataclasses import field

from jinja2 import nodes
from jinja2.exceptions import (
    TemplateSyntaxError,
    UndefinedError,
)
from pydantic.dataclasses import dataclass

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError, Jinja2StuffError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_scopes import ScopeBindings, attribute_chain, walk_template_reads
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


def _dotted_path(node: nodes.Node) -> str | None:
    """The dotted path of a pure attribute chain (`user.profile.name`), or None for any other shape."""
    chain = attribute_chain(node)
    if chain is None:
        return None
    name, attributes = chain
    return ".".join([name, *attributes])


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

    def collect_full_path(*, node: nodes.Node, bindings: ScopeBindings) -> bool:
        # Only the full path of an access chain is collected: `{{ foo.bar.baz }}` gives `foo.bar.baz`, not `foo.bar` or `foo`
        if not isinstance(node, (nodes.Name, nodes.Getattr)):
            return False
        full_path = _dotted_path(node)
        if full_path is None:
            # An attribute on a subscript, a call or a filter (`items[0].text`) reads the path its chain starts from
            return False
        if get_root_from_dotted_path(full_path) not in bindings:
            paths.add(full_path)
        return True

    walk_template_reads(template=parsed_ast, global_names=set(jinja2_env.globals), handle_read=collect_full_path)
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

    def collect_reference(*, node: nodes.Node, bindings: ScopeBindings) -> bool:
        # A filter chain is taken whole, with its filter names; a chain or a path that stops at a subscript or a
        # call (`items[0].image`) gives no reference, since no image or document can be resolved from it
        if isinstance(node, nodes.Filter):
            filters, base_node = _extract_filters_and_variable(node)
        elif isinstance(node, (nodes.Name, nodes.Getattr)):
            filters, base_node = [], node
        else:
            return False
        full_path = _dotted_path(base_node) if base_node is not None else None
        if full_path is None or get_root_from_dotted_path(full_path) in bindings:
            return True
        if full_path in references:
            # The same variable referenced several times combines its filters
            for filter_name in filters:
                if filter_name not in references[full_path].filters:
                    references[full_path].filters.append(filter_name)
        else:
            references[full_path] = VariableReference(path=full_path, filters=filters)
        return True

    walk_template_reads(template=parsed_ast, global_names=set(jinja2_env.globals), handle_read=collect_reference)
    return list(references.values())
