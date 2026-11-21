from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
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

# The trees parsed for reading inside a `sharing_template_parses` scope, by what decides the parse; None outside every scope.
_shared_parses: ContextVar[dict[tuple[object, ...], nodes.Template] | None] = ContextVar("_shared_parses", default=None)
# Whether the authored templates built inside the current scope were judged already, by `trusting_authored_templates`.
_are_authored_templates_trusted: ContextVar[bool] = ContextVar("_are_authored_templates_trusted", default=False)


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


@contextmanager
def sharing_template_parses() -> Generator[None, None, None]:
    """Parse each template once for every reading of it inside, such as the checks and analyses of one library load.

    A pipe reads its templates several times while it is built, each reading for one purpose: the parse check, each
    template lint, the images and documents a prompt presents, the paths a template reads. Inside this scope,
    `read_jinja2_template` parses a template the first time it is read and hands every later reading the same tree.
    The trees are dropped when the scope ends. A scope opened inside another shares the outer one's trees.
    """
    if _shared_parses.get() is not None:
        yield
        return
    token = _shared_parses.set({})
    try:
        yield
    finally:
        _shared_parses.reset(token)


@contextmanager
def trusting_authored_templates() -> Generator[None, None, None]:
    """Build the pipes and blueprints inside this block from templates already judged, skipping the checks that only judge them.

    The judgments of an authored template, whether it parses, what the template lints refuse and whether it reads
    exactly the inputs its pipe declares, are made where its method is loaded and validated. A library crate that such
    a load produced, decoded and loaded again by the same pipelex for a run (the worker's handling of the crate its
    runner validated), holds templates that passed them, so they are not made again. Nothing a run reads is skipped:
    the analyses that build a pipe's state, such as the images and documents a prompt presents, still run, and the
    render refuses a template that does not parse or reads a private name. A scope opened inside another changes nothing.
    """
    token = _are_authored_templates_trusted.set(True)
    try:
        yield
    finally:
        _are_authored_templates_trusted.reset(token)


def are_authored_templates_trusted() -> bool:
    """Whether the authored templates of the pipes being built were judged already (`trusting_authored_templates`)."""
    return _are_authored_templates_trusted.get()


def _parse_key(*, jinja2_env: jinja2.Environment, template_source: str) -> tuple[object, ...]:
    """What decides the tree Jinja2 parses from a source: its environment's syntax settings and extensions, and the source.

    The syntax settings are those Jinja2 keys its own lexer cache on; the extensions add the tags a parse recognizes.
    """
    return (
        type(jinja2_env),
        jinja2_env.block_start_string,
        jinja2_env.block_end_string,
        jinja2_env.variable_start_string,
        jinja2_env.variable_end_string,
        jinja2_env.comment_start_string,
        jinja2_env.comment_end_string,
        jinja2_env.line_statement_prefix,
        jinja2_env.line_comment_prefix,
        jinja2_env.trim_blocks,
        jinja2_env.lstrip_blocks,
        jinja2_env.newline_sequence,
        jinja2_env.keep_trailing_newline,
        tuple(sorted(jinja2_env.extensions)),
        template_source,
    )


def read_jinja2_template(*, jinja2_env: jinja2.Environment, template_source: str) -> nodes.Template:
    """Parse a template to read it, as `parse_jinja2_template` does, once per `sharing_template_parses` scope.

    The tree may be shared with every other reading of the same template in the scope, so it must never be changed:
    a tree to compile or rewrite, as a render does, comes from `parse_jinja2_template`. A template that does not parse
    is not remembered, so each reading raises again.
    """
    shared_parses = _shared_parses.get()
    if shared_parses is None:
        return parse_jinja2_template(jinja2_env=jinja2_env, template_source=template_source)
    parse_key = _parse_key(jinja2_env=jinja2_env, template_source=template_source)
    parsed_template = shared_parses.get(parse_key)
    if parsed_template is None:
        parsed_template = parse_jinja2_template(jinja2_env=jinja2_env, template_source=template_source)
        shared_parses[parse_key] = parsed_template
    return parsed_template


def check_jinja2_parsing(
    template_source: str,
    *,
    template_category: TemplateCategory = TemplateCategory.LLM_PROMPT,
):
    """Refuse a template Jinja2 cannot parse, or one nested too deeply to parse, walk or compile, as the method's syntax.

    An authored template's judgment, so it is skipped inside `trusting_authored_templates`.
    """
    if are_authored_templates_trusted():
        return
    jinja2_env = make_jinja2_env_without_loader(template_category=template_category)
    try:
        read_jinja2_template(jinja2_env=jinja2_env, template_source=template_source)
    except TemplateNestingError as exc:
        # The nesting fault alone: the source of such a template can be very long, and quoting it says nothing more.
        msg = f"Could not parse Jinja2 template: {exc.message}"
        raise Jinja2TemplateSyntaxError(msg) from exc
    except jinja2.exceptions.TemplateSyntaxError as exc:
        msg = f"Could not parse Jinja2 template because of: {exc}. Template source:\n{template_source}"
        raise Jinja2TemplateSyntaxError(msg) from exc
