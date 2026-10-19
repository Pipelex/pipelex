import re
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple, Protocol, TypeVar

from jinja2 import nodes
from jinja2.exceptions import (
    FilterArgumentError,
    SecurityError,
    TemplateAssertionError,
    TemplateError,
    TemplateNotFound,
    TemplateRuntimeError,
    TemplateSyntaxError,
    UndefinedError,
)
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError, PipelexUnexpectedError
from pipelex.system.exceptions import ToolError
from pipelex.tools.jinja2.exceptions import (
    Jinja2ContextError,
    Jinja2StuffError,
    Jinja2TemplateBudgetError,
    Jinja2TemplateInvalidError,
    Jinja2TemplateRenderError,
    Jinja2TemplateSecurityError,
    SandboxRefusalError,
)
from pipelex.tools.jinja2.jinja2_environment import (
    make_jinja2_env_from_registry,
    make_jinja2_env_without_loader,
)
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.jinja2_render_budget import RenderBudgetExceededError
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner
from pipelex.tools.templating.templating_style import TemplatingStyle

_TemplateError = TypeVar("_TemplateError", bound=PipelexError)


def _coded_by_owner(*, error: _TemplateError, template_owner: TemplateOwner) -> _TemplateError:
    """A failure of a template, coded by whose template it is.

    On a method's template the error keeps the code its raise site gave it, or its class's default; on Pipelex's own
    template the failure is ours, `runtime.unexpected`, whose message never reaches a caller, since a caller must not
    read that template's source. Every class it serves declares `runtime.unexpected` among its codes.
    """
    match template_owner:
        case TemplateOwner.METHOD:
            return error
        case TemplateOwner.PIPELEX:
            return error.with_error_code(CoreCode.RUNTIME_UNEXPECTED)


def _add_to_templating_context(
    templating_context: dict[str, Any], *, jinja2_context_key: Jinja2ContextKey, value: Any, template_owner: TemplateOwner
) -> None:
    if jinja2_context_key in templating_context:
        # On a method's template, a method variable named like the reserved key: `method.name_conflict`, the default.
        msg = f"Jinja2 context key '{jinja2_context_key}' already in templating_context"
        raise _coded_by_owner(error=Jinja2StuffError(msg), template_owner=template_owner)
    templating_context[jinja2_context_key] = value


class _Jinja2Template(Protocol):
    def render(self, **kwargs: Any) -> str: ...

    def render_async(self, **kwargs: Any) -> Awaitable[str]: ...


def _compile_jinja2_template(
    template_source: str,
    *,
    template_category: TemplateCategory,
    template_owner: TemplateOwner,
    use_registry: bool = False,
    enable_async: bool = True,
    finalize: Callable[[Any], Any] | None = None,
    is_undefined_strict: bool = False,
) -> _Jinja2Template:
    if use_registry:
        jinja2_env = make_jinja2_env_from_registry(
            template_category=template_category,
            enable_async=enable_async,
            finalize=finalize,
            is_undefined_strict=is_undefined_strict,
        )
    else:
        jinja2_env = make_jinja2_env_without_loader(
            template_category=template_category,
            enable_async=enable_async,
            finalize=finalize,
            is_undefined_strict=is_undefined_strict,
        )

    try:
        return jinja2_env.from_string(template_source)
    except TemplateSyntaxError as exc:
        # A filter or test the environment does not define, outside any branch, is a `TemplateAssertionError`
        # that compiling finds; a method's template is only parsed at load, so this is where it surfaces.
        raise _make_invalid_template_error(template_error=exc, template_source=template_source, template_owner=template_owner) from exc


def _prepare_templating_context(
    templating_context: dict[str, Any],
    *,
    templating_style: TemplatingStyle | None,
    template_owner: TemplateOwner,
) -> dict[str, Any]:
    # Create a copy to avoid mutating the caller's original dictionary
    prepared_templating_context = templating_context.copy()
    if templating_style:
        _add_to_templating_context(
            templating_context=prepared_templating_context,
            jinja2_context_key=Jinja2ContextKey.TAG_STYLE,
            value=templating_style.tag_style,
            template_owner=template_owner,
        )
        _add_to_templating_context(
            templating_context=prepared_templating_context,
            jinja2_context_key=Jinja2ContextKey.TEXT_FORMAT,
            value=templating_style.text_format,
            template_owner=template_owner,
        )
    return prepared_templating_context


#: The file name Jinja2 gives a template compiled from a string, in the frames it rewrites into a render's traceback.
_TEMPLATE_FRAME_FILENAME = "<template>"

# The name a strict undefined's message says is missing: Jinja2 words it "'name' is undefined", "... has no attribute
# 'name'" or "... has no element 'name'", where what comes before the name can quote an object's class.
_UNDEFINED_NAME_PATTERN = re.compile(r"(?:has no (?:attribute|element) |^)'([^']+)'(?: is undefined)?$")


def template_line_of(*, render_error: BaseException) -> int | None:
    """The line of the template a render failed at, read off the frame Jinja2 writes for the template in its traceback.

    The innermost such frame is the one that raised. ``None`` when the traceback holds none, such as for a failure
    raised before the render ran.
    """
    template_line: int | None = None
    traceback = render_error.__traceback__
    while traceback is not None:
        if traceback.tb_frame.f_code.co_filename == _TEMPLATE_FRAME_FILENAME:
            template_line = traceback.tb_lineno
        traceback = traceback.tb_next
    return template_line


class SpelledNames(NamedTuple):
    """The names a template's own source spells, read off the template Jinja2 parses, never off its text.

    ``references`` are the names it reads, stores or reaches as a variable or an attribute: a variable (``invoice``), an
    attribute (``.total``), a key written as a literal (``['total']``, ``attr('total')``, ``{'total': ...}``), a
    keyword's name (``namespace(total=...)``), a namespace's attribute it sets and a macro's name. ``filters_and_tests``
    are the filters and tests it applies. A name the template reaches through a value, ``notes[patient_id]``, is none of
    them: that name is a value of the run's data.
    """

    references: frozenset[str]
    filters_and_tests: frozenset[str]


def template_spelled_names(*, template_source: str) -> SpelledNames:
    """The names ``template_source`` spells (see ``SpelledNames``), none when it does not parse.

    ``template_source`` is the source Jinja2 compiles, after Pipelex's sigils are rewritten into Jinja2's syntax. Parsing
    runs none of the template.
    """
    jinja2_env = make_jinja2_env_without_loader(template_category=TemplateCategory.BASIC, enable_async=False)
    try:
        parsed_template = jinja2_env.parse(template_source)
    except TemplateSyntaxError:
        return SpelledNames(references=frozenset(), filters_and_tests=frozenset())
    references: set[str] = set()
    filters_and_tests: set[str] = set()
    spelling_nodes = (nodes.Name, nodes.Getattr, nodes.NSRef, nodes.Keyword, nodes.Getitem, nodes.Pair, nodes.Macro, nodes.Filter, nodes.Test)
    for node in parsed_template.find_all(spelling_nodes):
        match node:
            case nodes.Name(name=str() as name) | nodes.Macro(name=str() as name):
                references.add(name)
            case nodes.Getattr(attr=str() as attribute) | nodes.NSRef(attr=str() as attribute):
                references.add(attribute)
            case nodes.Keyword(key=str() as key):
                references.add(key)
            case nodes.Getitem(arg=nodes.Const(value=str() as key)) | nodes.Pair(key=nodes.Const(value=str() as key)):
                references.add(key)
            case nodes.Filter(name=str() as filter_name):
                filters_and_tests.add(filter_name)
                # `attr('name')` reaches the attribute a literal names.
                if filter_name == "attr" and node.args and isinstance(node.args[0], nodes.Const) and isinstance(node.args[0].value, str):
                    references.add(node.args[0].value)
            case nodes.Test(name=str() as test_name):
                filters_and_tests.add(test_name)
            case _:
                pass
    return SpelledNames(references=frozenset(references), filters_and_tests=frozenset(filters_and_tests))


def undefined_variable_name(*, undefined_error: UndefinedError, template_source: str) -> str | None:
    """The name an undefined's error says is missing, when the template itself spells it, else ``None``.

    Jinja2 names what a template reached for, which is the template's own name for ``{{ invoice.total }}``, but the
    run's value for ``{{ notes[patient_id] }}``, a key of the data: a name is given only when the parsed template spells
    it as a variable or an attribute (see ``template_spelled_names``), so a key drawn from the data, which no message
    carries, never is, even when the same word appears elsewhere in the template's text. ``template_source`` is the
    source Jinja2 compiled, after Pipelex's sigils are rewritten.
    """
    match = _UNDEFINED_NAME_PATTERN.search(undefined_error.message or "")
    if match is None:
        return None
    name = match.group(1)
    return name if name in template_spelled_names(template_source=template_source).references else None


def _describe_render_error(*, description: str, render_error: BaseException) -> str:
    """A fixed description of a render's failure, with the class Jinja2 or Python raised and the template's line.

    Neither the exception's own text nor the template source is written: Jinja2's and Python's texts can quote a value
    the template reached, which is the run's data, or a name drawn from it, and the source is the method's own text, or
    for Pipelex's own templates the run's data they render.
    """
    template_line = template_line_of(render_error=render_error)
    where = f", at line {template_line} of the template" if template_line is not None else ""
    return f"{description} ({type(render_error).__name__}{where})"


def _spells_every_name(*, named: tuple[str, ...], template_source: str) -> bool:
    """Whether the parsed template spells every name a refusal quotes (see ``template_spelled_names``)."""
    if not named:
        return True
    spelled_references = template_spelled_names(template_source=template_source).references
    return all(name in spelled_references for name in named)


def _make_security_error_msg(*, security_error: SecurityError, template_source: str) -> str:
    """The sandbox's refusal, worded with the names it quotes where the template spells them all, without them otherwise.

    A refusal names what the template reached for, which a template reading ``obj[key]``, ``obj | attr(key)`` or
    storing ``namespace({key: value})`` takes from the run's data: the sandbox words each refusal twice
    (``SandboxRefusalError``), and the wording with the names is kept only when the parsed template spells every one.
    A refusal worded by Jinja2 itself, not by the sandbox, is written as a fixed description.
    """
    if isinstance(security_error, SandboxRefusalError):
        is_spelled = _spells_every_name(named=security_error.named, template_source=template_source)
        refusal = (security_error.message or "") if is_spelled else security_error.anonymous_message
    else:
        description = "the template reached for an attribute, a method or a call the sandbox does not allow"
        refusal = _describe_render_error(description=description, render_error=security_error)
    return f"Jinja2 render — refused by the template sandbox: {refusal}"


# A template nesting macro calls or recursive loops deep enough reaches Python's recursion limit before
# its budget, which is the same overspending by another name.
_RECURSION_MSG = "Jinja2 render — refused by the render budget: the template nests calls deeper than Python allows."


def _make_budget_error_msg(*, budget_error: RenderBudgetExceededError, template_source: str) -> str:
    """The budget's refusal, which names the operation and its size, never the template source or a value.

    A refused call names the callable it called, which a template reading it by ``obj[key]`` or ``obj | attr(key)`` names
    by a value of the run's data: as for the sandbox's refusals, the wording with the names is kept only when the parsed
    template spells every one (``RenderBudgetExceededError``).
    """
    is_spelled = _spells_every_name(named=budget_error.named, template_source=template_source)
    refusal = (budget_error.message or "") if is_spelled else budget_error.anonymous_message
    return f"Jinja2 render — refused by the render budget: {refusal}"


def _make_own_error_msg(*, error_label: str, error: Jinja2StuffError | Jinja2ContextError) -> str:
    # A refusal of Pipelex's own filters, whose message, like every raise site's of Pipelex, holds no run's data: no
    # argument the template handed the filter, which can be a value of the run's, and no value it refused.
    return f"Jinja2 render — {error_label}: '{error}'"


def _make_undefined_error_msg(*, undefined_error: UndefinedError, template_source: str) -> str:
    variable_name = undefined_variable_name(undefined_error=undefined_error, template_source=template_source)
    description = f"the template reads '{variable_name}', which is not defined" if variable_name else "the template reads a value that is not defined"
    return f"Jinja2 render — undefined error: {_describe_render_error(description=description, render_error=undefined_error)}"


# How Jinja2 words a filter or a test its environment does not define: "No filter named 'frob'." when it compiles the
# template, "No filter named 'frob' found." when it renders a branch that applies it.
_UNKNOWN_FILTER_OR_TEST_PATTERN = re.compile(r"^No (?P<kind>filter|test) named '(?P<name>[^']+)'")


def _describe_template_fault(*, template_error: TemplateError, template_source: str) -> str:
    """What Jinja2 refused in a template, as a fixed description and the template's line, never Jinja2's own text.

    A syntax error's text quotes the token Jinja2 stopped at (``expected token 'end of print statement', got 'x'``),
    which is the template's text, and the template can be the run's data, as Pipelex's own templates render it: the
    description names the kind of fault and where it is. A filter or a test the environment does not define is named,
    as the author reads it best, when the parsed template applies it by that name.
    """
    unknown = _UNKNOWN_FILTER_OR_TEST_PATTERN.match(template_error.message or "")
    if unknown is not None:
        kind = unknown["kind"]
        if unknown["name"] in template_spelled_names(template_source=template_source).filters_and_tests:
            description = f"No {kind} named '{unknown['name']}'"
        else:
            description = f"the template applies a {kind} its environment does not define"
    elif isinstance(template_error, TemplateAssertionError):
        description = "the template uses a construct Jinja2 refuses where it stands"
    elif isinstance(template_error, TemplateSyntaxError):
        description = "syntax error"
    else:
        description = "the template uses a construct Jinja2 cannot render"
    template_line = template_error.lineno if isinstance(template_error, TemplateSyntaxError) else template_line_of(render_error=template_error)
    where = f" at line {template_line}" if template_line else ""
    return f"{description}{where}."


def _make_invalid_template_error(*, template_error: TemplateError, template_source: str, template_owner: TemplateOwner) -> Jinja2TemplateInvalidError:
    """The error of a template that cannot render as written, coded by its owner.

    Its message gives what Jinja2 refused as a fixed description and the template's line (see
    ``_describe_template_fault``), never Jinja2's own text, the template source nor the line Jinja2 would quote with
    it, so on a method's template it can be the ``finding`` parameter its problem shows the caller.
    """
    if isinstance(template_error, TemplateNotFound):
        # A template without a loader (every method template) has nothing to include or extend. The name is left out:
        # an include can name its template by a value of the run's data.
        fault = "template not found: the template includes, imports or extends a template it cannot reach."
    else:
        fault = _describe_template_fault(template_error=template_error, template_source=template_source)
    msg = f"Jinja2 render — the template cannot render as written: {fault}"
    invalid_error = _coded_by_owner(error=Jinja2TemplateInvalidError(msg, fault=fault, template_owner=template_owner), template_owner=template_owner)
    if template_owner.is_method:
        # The fault names the construct Jinja2 refused and never the source, so the method's author reads it as the finding.
        invalid_error.with_params(finding=fault)
    return invalid_error


def _make_data_render_error(*, msg: str, template_owner: TemplateOwner) -> Jinja2TemplateRenderError:
    """The error of a render that failed on this run's data or on the template, which nothing here tells apart."""
    return _coded_by_owner(error=Jinja2TemplateRenderError(msg), template_owner=template_owner)


def _make_context_render_error(*, msg: str, context_error: Jinja2ContextError, template_owner: TemplateOwner) -> Jinja2TemplateRenderError:
    """The error of a render whose filter refused the context or the value: on a method's template, the filter's code."""
    render_error = Jinja2TemplateRenderError(msg)
    if context_error.own_error_code is not None:
        render_error.with_error_code(context_error.own_error_code)
    return _coded_by_owner(error=render_error, template_owner=template_owner)


# What a render can raise, each translated by `_make_render_failure`. `SecurityError`, `UndefinedError` and
# `FilterArgumentError` are `TemplateRuntimeError`s, and `RenderBudgetExceededError` a `TemplateError`; they are named
# for the reader.
_RENDER_FAILURES: tuple[type[BaseException], ...] = (
    SecurityError,
    RenderBudgetExceededError,
    RecursionError,
    Jinja2StuffError,
    Jinja2ContextError,
    TemplateSyntaxError,
    UndefinedError,
    FilterArgumentError,
    TemplateNotFound,
    TemplateRuntimeError,
    ArithmeticError,
    TypeError,
)


def _make_render_failure(
    *, render_error: BaseException, template_source: str, template_owner: TemplateOwner
) -> ToolError | Jinja2TemplateSecurityError:
    """Translate what a render raised into the error the render reports, coded by the template's owner.

    The order of the arms matters: a refusal of the sandbox, an undefined value and a filter refusing its argument are
    `TemplateRuntimeError`s too, and only what is left of that family, the plain `TemplateRuntimeError` Jinja2 raises
    for the template's own constructs, such as a filter or a test inside a branch that the environment does not define,
    is the template's fault on any input.

    What Jinja2 or Python raised while rendering is written as a fixed description, its class and the template's line,
    never its own text, which can quote a value the template reached, such as a key of the run's data
    (``'dict object' has no attribute '<the key>'``) or a type error's operands.
    """
    if isinstance(render_error, SecurityError):
        security_msg = _make_security_error_msg(security_error=render_error, template_source=template_source)
        return _coded_by_owner(error=Jinja2TemplateSecurityError(security_msg), template_owner=template_owner)
    if isinstance(render_error, (RenderBudgetExceededError, RecursionError)):
        budget_msg = (
            _make_budget_error_msg(budget_error=render_error, template_source=template_source)
            if isinstance(render_error, RenderBudgetExceededError)
            else _RECURSION_MSG
        )
        match template_owner:
            case TemplateOwner.METHOD:
                return Jinja2TemplateBudgetError(budget_msg)
            case TemplateOwner.PIPELEX:
                # Pipelex's own template only overspends on data too large to display.
                return Jinja2TemplateBudgetError(budget_msg).with_error_code(CoreCode.INPUT_TOO_LARGE)
    if isinstance(render_error, Jinja2ContextError):
        msg = _make_own_error_msg(error_label="context error", error=render_error)
        return _make_context_render_error(msg=msg, context_error=render_error, template_owner=template_owner)
    if isinstance(render_error, Jinja2StuffError):
        msg = _make_own_error_msg(error_label="stuff error", error=render_error)
        return _make_data_render_error(msg=msg, template_owner=template_owner)
    if isinstance(render_error, UndefinedError):
        msg = _make_undefined_error_msg(undefined_error=render_error, template_source=template_source)
        return _make_data_render_error(msg=msg, template_owner=template_owner)
    if isinstance(render_error, FilterArgumentError):
        # A filter refusing its argument may be refusing this run's value (`reverse` on a value that is not iterable)
        # as well as the template's own literal, which nothing here tells apart, so it is not the template's alone.
        description = "a filter refused its argument"
        msg = f"Jinja2 render — filter argument error: {_describe_render_error(description=description, render_error=render_error)}"
        return _make_data_render_error(msg=msg, template_owner=template_owner)
    if isinstance(render_error, (TemplateSyntaxError, TemplateNotFound, TemplateRuntimeError)):
        return _make_invalid_template_error(template_error=render_error, template_source=template_source, template_owner=template_owner)
    if isinstance(render_error, ArithmeticError):
        # The template's own arithmetic, the sandbox's range cap included: `range` raises OverflowError past it.
        description = "the template's arithmetic failed, or a range overran the sandbox's limit"
        msg = f"Jinja2 render — arithmetic error: {_describe_render_error(description=description, render_error=render_error)}"
        return _make_data_render_error(msg=msg, template_owner=template_owner)
    if isinstance(render_error, TypeError):
        # Often an iteration over a method, or an attribute reached the wrong way.
        description = "the template applied an operation to a value of a type that does not support it"
        msg = f"Jinja2 render — type error: {_describe_render_error(description=description, render_error=render_error)}"
        return _make_data_render_error(msg=msg, template_owner=template_owner)
    msg = f"Jinja2 render — {type(render_error).__name__} is not a failure the render translates"
    raise PipelexUnexpectedError(msg) from render_error


def _render_template_sync(
    *, template: _Jinja2Template, template_source: str, templating_context: dict[str, Any], template_owner: TemplateOwner
) -> str:
    try:
        generated_text: str = template.render(**templating_context)
    except _RENDER_FAILURES as exc:
        raise _make_render_failure(render_error=exc, template_source=template_source, template_owner=template_owner) from exc
    return generated_text


async def _render_template_async(
    *, template: _Jinja2Template, template_source: str, templating_context: dict[str, Any], template_owner: TemplateOwner
) -> str:
    try:
        generated_text: str = await template.render_async(**templating_context)
    except _RENDER_FAILURES as exc:
        raise _make_render_failure(render_error=exc, template_source=template_source, template_owner=template_owner) from exc
    return generated_text


def render_jinja2_sync(
    template_source: str,
    *,
    template_category: TemplateCategory,
    templating_context: dict[str, Any],
    templating_style: TemplatingStyle | None = None,
    use_registry: bool = False,
    template_owner: TemplateOwner = TemplateOwner.PIPELEX,
) -> str:
    """Render a template; `template_owner` decides whose fault a failure is, Pipelex's own unless said otherwise."""
    template = _compile_jinja2_template(
        template_source=template_source,
        template_category=template_category,
        template_owner=template_owner,
        use_registry=use_registry,
        enable_async=False,
    )
    prepared_templating_context = _prepare_templating_context(
        templating_context=templating_context,
        templating_style=templating_style,
        template_owner=template_owner,
    )
    return _render_template_sync(
        template=template,
        template_source=template_source,
        templating_context=prepared_templating_context,
        template_owner=template_owner,
    )


async def render_jinja2_async(
    template_source: str,
    *,
    template_category: TemplateCategory,
    templating_context: dict[str, Any],
    templating_style: TemplatingStyle | None = None,
    use_registry: bool = False,
    finalize: Callable[[Any], Any] | None = None,
    is_undefined_strict: bool = False,
    template_owner: TemplateOwner = TemplateOwner.PIPELEX,
) -> str:
    """Render a template; `template_owner` decides whose fault a failure is, Pipelex's own unless said otherwise.

    A method's template is rendered through `pipelex.cogt.templating.template_rendering.render_template`, which says so.
    """
    template = _compile_jinja2_template(
        template_source=template_source,
        template_category=template_category,
        template_owner=template_owner,
        use_registry=use_registry,
        finalize=finalize,
        is_undefined_strict=is_undefined_strict,
    )
    prepared_templating_context = _prepare_templating_context(
        templating_context=templating_context,
        templating_style=templating_style,
        template_owner=template_owner,
    )
    return await _render_template_async(
        template=template,
        template_source=template_source,
        templating_context=prepared_templating_context,
        template_owner=template_owner,
    )
