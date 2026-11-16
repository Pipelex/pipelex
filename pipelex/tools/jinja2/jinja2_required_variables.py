"""The variables a template reads from its inputs, and the references through which it attaches images and documents.

Both detectors are handlers on the read walk of `jinja2_scopes.py`, which follows Jinja's own scopes: a name the
template binds (a `{% set %}`, a loop target, a macro argument) is not reported where Jinja binds it, and is
reported as the input of that name everywhere else, such as after an `if` whose branches do not all set it.
"""

from dataclasses import field
from functools import lru_cache

from jinja2 import nodes
from jinja2.exceptions import (
    TemplateSyntaxError,
    UndefinedError,
)
from pydantic.dataclasses import dataclass

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError, Jinja2StuffError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_scopes import ScopeBindings, dotted_attribute_path, walk_template_reads
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


def _make_detect_variables_error(
    *, parse_error: Jinja2StuffError | TemplateSyntaxError | UndefinedError, template_category: TemplateCategory
) -> Jinja2DetectVariablesError:
    """The error of a template that could not be parsed to find its variables, naming the kind of fault and where.

    Neither the template source, the line of it Jinja2 quotes, nor Jinja2's own message is written: a syntax error's
    message quotes the token Jinja2 stopped at (``expected token 'end of print statement', got 'x'``) and its text ends
    with the line, both the template's text, which is the method's own, or for Pipelex's own templates the run's data
    they render.
    """
    if isinstance(parse_error, TemplateSyntaxError):
        where = f" at line {parse_error.lineno}" if parse_error.lineno else ""
        finding = f"syntax error{where} ({type(parse_error).__name__})"
    elif isinstance(parse_error, UndefinedError):
        finding = f"undefined error ({type(parse_error).__name__})"
    else:
        finding = f"stuff error: '{parse_error}'"
    msg = f"Jinja2 detect variables — {finding}, template_category: {template_category}"
    return Jinja2DetectVariablesError(msg)


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
    except (Jinja2StuffError, TemplateSyntaxError, UndefinedError) as parse_error:
        raise _make_detect_variables_error(parse_error=parse_error, template_category=template_category) from parse_error

    paths: set[str] = set()

    def collect_full_path(*, node: nodes.Node, bindings: ScopeBindings) -> bool:
        # Only the full path of an access chain is collected: `{{ foo.bar.baz }}` gives `foo.bar.baz`, not `foo.bar` or `foo`
        if not isinstance(node, (nodes.Name, nodes.Getattr)):
            return False
        full_path = dotted_attribute_path(node)
        if full_path is None:
            # An attribute on a subscript, a call or a filter (`items[0].text`) reads the path its chain starts from
            return False
        if get_root_from_dotted_path(full_path) not in bindings:
            paths.add(full_path)
        return True

    walk_template_reads(template=parsed_ast, global_names=set(jinja2_env.globals), handle_read=collect_full_path)
    return paths


def detect_jinja2_read_paths(
    *,
    template_category: TemplateCategory,
    template_source: str,
) -> set[str]:
    """Returns the dotted paths through which the Jinja2 template may read its inputs' values.

    It is the set `detect_jinja2_required_variables` returns, plus the object of every method the template calls: a
    call such as `{{ doc.get("a") }}` or `{% for key, value in doc.mapping.items() %}` reads values below `doc` or
    `doc.mapping` that no attribute path names, so the path the method is called on is a read path too. A value is read
    by the template when its path equals a read path, is a prefix of one, or is prefixed by one, compared segment by
    segment: `{{ doc.a.b }}` reads `doc.a.b` and everything under it, and nothing under `doc.a.c`.

    Args:
        template_category: Category of the template (HTML, MARKDOWN, etc.)
        template_source: Jinja2 template string

    Returns:
        Set of full dotted read paths

    Raises:
        Jinja2DetectVariablesError: If there is an error parsing the template
    """
    jinja2_env = make_jinja2_env_without_loader(
        template_category=template_category,
    )

    try:
        parsed_ast = jinja2_env.parse(template_source)
    except (Jinja2StuffError, TemplateSyntaxError, UndefinedError) as parse_error:
        raise _make_detect_variables_error(parse_error=parse_error, template_category=template_category) from parse_error

    paths: set[str] = set()

    def collect_read_path(*, node: nodes.Node, bindings: ScopeBindings) -> bool:
        if isinstance(node, nodes.Call) and isinstance(node.node, nodes.Getattr):
            # A method reads the object it is called on, whatever its arguments say: that object's path is read whole.
            # The walk goes on into the call, so the method's own path and its arguments are collected too.
            called_on_path = dotted_attribute_path(node.node.node)
            if called_on_path is not None and get_root_from_dotted_path(called_on_path) not in bindings:
                paths.add(called_on_path)
            return False
        if not isinstance(node, (nodes.Name, nodes.Getattr)):
            return False
        full_path = dotted_attribute_path(node)
        if full_path is None:
            return False
        if get_root_from_dotted_path(full_path) not in bindings:
            paths.add(full_path)
        return True

    walk_template_reads(template=parsed_ast, global_names=set(jinja2_env.globals), handle_read=collect_read_path)
    return paths


# How many distinct templates keep their parsed read paths in one process: every template of the methods a long-running
# worker serves, bounded so that the cache never grows with them.
_READ_PATHS_CACHE_SIZE = 4096


@lru_cache(maxsize=_READ_PATHS_CACHE_SIZE)
def parse_jinja2_read_paths(*, template_category: TemplateCategory, template_source: str) -> frozenset[str]:
    """The read paths of `detect_jinja2_read_paths`, parsed once per template source and category in a process.

    A pipe reads the paths of its templates at validation and again at every step it runs, so they are parsed once and
    shared. The cache is keyed on the template category and source and held outside every model: a path set cached on a pydantic
    instance would sit in its `__dict__`, which a host runtime's data converter (kajson) encodes the model from. A
    template that does not parse caches nothing, so each call raises again.

    Raises:
        Jinja2DetectVariablesError: If there is an error parsing the template
    """
    return frozenset(detect_jinja2_read_paths(template_category=template_category, template_source=template_source))


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
    except (Jinja2StuffError, TemplateSyntaxError, UndefinedError) as parse_error:
        raise _make_detect_variables_error(parse_error=parse_error, template_category=template_category) from parse_error

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
        full_path = dotted_attribute_path(base_node) if base_node is not None else None
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
