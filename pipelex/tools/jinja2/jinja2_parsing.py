from typing import Final

import jinja2
from jinja2 import nodes

from pipelex.tools.jinja2.exceptions import TEMPLATE_NESTING_ERRORS, Jinja2TemplateSyntaxError, TemplateNestingError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.template_category import TemplateCategory

# How deep a parsed template's tree may nest. Jinja2 parses, walks and compiles a template recursively, and so do the
# template lints of this package, so a template that parses at the depth Python's recursion limit allows can still
# exhaust it in a walk, or fail Python's compiler (`IndentationError` on deeply nested blocks). This bound is far
# deeper than any template written by hand, and far shallower than what exhausts the recursion limit.
MAX_TEMPLATE_NESTING_DEPTH: Final[int] = 100


def _nesting_depth(*, parsed_template: nodes.Template, limit: int) -> tuple[int, int]:
    """The depth of the parsed tree, counted without recursion and stopping past `limit`, and the line where it peaks."""
    deepest = 0
    deepest_line = 1
    stack: list[tuple[nodes.Node, int]] = [(parsed_template, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > deepest:
            deepest = depth
            deepest_line = getattr(node, "lineno", None) or deepest_line
            if deepest > limit:
                break
        stack.extend((child, depth + 1) for child in node.iter_child_nodes())
    return deepest, deepest_line


def parse_jinja2_template(*, jinja2_env: jinja2.Environment, template_source: str) -> nodes.Template:
    """Parse a template, refusing one nested too deeply as a `TemplateNestingError`, a `TemplateSyntaxError`.

    Jinja2's parser is recursive: a template nested past what Python's recursion limit allows raises `RecursionError`
    (or another of `TEMPLATE_NESTING_ERRORS`), and one that parses but nests deeper than `MAX_TEMPLATE_NESTING_DEPTH`
    would exhaust it in the walk that follows. Every site that parses a template goes through here, so that both are
    the template's syntax error, never an unexpected failure.
    """
    try:
        parsed_template = jinja2_env.parse(template_source)
    except TEMPLATE_NESTING_ERRORS as exc:
        raise TemplateNestingError(lineno=1) from exc
    depth, line = _nesting_depth(parsed_template=parsed_template, limit=MAX_TEMPLATE_NESTING_DEPTH)
    if depth > MAX_TEMPLATE_NESTING_DEPTH:
        raise TemplateNestingError(lineno=line)
    return parsed_template


def check_jinja2_parsing(
    template_source: str,
    *,
    template_category: TemplateCategory = TemplateCategory.LLM_PROMPT,
):
    """Refuse a template Jinja2 cannot parse, or one nested too deeply to parse, walk or compile, as the method's syntax."""
    jinja2_env = make_jinja2_env_without_loader(template_category=template_category)
    try:
        parse_jinja2_template(jinja2_env=jinja2_env, template_source=template_source)
    except TemplateNestingError as exc:
        # The nesting fault alone: the source of such a template can be very long, and quoting it says nothing more.
        msg = f"Could not parse Jinja2 template: {exc.message}"
        raise Jinja2TemplateSyntaxError(msg) from exc
    except jinja2.exceptions.TemplateSyntaxError as exc:
        msg = f"Could not parse Jinja2 template because of: {exc}. Template source:\n{template_source}"
        raise Jinja2TemplateSyntaxError(msg) from exc
