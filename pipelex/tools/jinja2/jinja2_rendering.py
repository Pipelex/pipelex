import re
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar

from jinja2.exceptions import (
    FilterArgumentError,
    SecurityError,
    TemplateError,
    TemplateNotFound,
    TemplateRuntimeError,
    TemplateSyntaxError,
    UndefinedError,
)
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.system.exceptions import ToolError
from pipelex.tools.jinja2.exceptions import (
    Jinja2ContextError,
    Jinja2StuffError,
    Jinja2TemplateBudgetError,
    Jinja2TemplateInvalidError,
    Jinja2TemplateRenderError,
    Jinja2TemplateSecurityError,
)
from pipelex.tools.jinja2.jinja2_environment import (
    make_jinja2_env_from_registry,
    make_jinja2_env_without_loader,
)
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.jinja2_render_budget import RenderBudgetExceededError
from pipelex.tools.jinja2.jinja2_sandbox import REFUSED_READ_PATTERN, SANDBOX_REFUSAL_PREFIX
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner
from pipelex.tools.templating.templating_style import TemplatingStyle

_TemplateError = TypeVar("_TemplateError", bound=ToolError)


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
        raise _make_invalid_template_error(template_error=exc, template_owner=template_owner) from exc


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


def undefined_variable_name(*, undefined_error: UndefinedError, template_source: str) -> str | None:
    """The name an undefined's error says is missing, when the template itself writes it, else ``None``.

    Jinja2 names what a template reached for, which is the template's own name for ``{{ invoice.total }}``, but the
    run's value for ``{{ notes[patient_id] }}``, a key of the data: a name is given only when it is an identifier the
    template's own source spells, so a key drawn from the data, which no message carries, never is.
    """
    match = _UNDEFINED_NAME_PATTERN.search(undefined_error.message or "")
    if match is None:
        return None
    name = match.group(1)
    return name if _is_spelled_in_template(name=name, template_source=template_source) else None


def _describe_render_error(*, description: str, render_error: BaseException) -> str:
    """A fixed description of a render's failure, with the class Jinja2 or Python raised and the template's line.

    Neither the exception's own text nor the template source is written: Jinja2's and Python's texts can quote a value
    the template reached, which is the run's data, or a name drawn from it, and the source is the method's own text, or
    for Pipelex's own templates the run's data they render.
    """
    template_line = template_line_of(render_error=render_error)
    where = f", at line {template_line} of the template" if template_line is not None else ""
    return f"{description} ({type(render_error).__name__}{where})"


def _is_spelled_in_template(*, name: str, template_source: str) -> bool:
    """Whether ``name`` is an identifier the template's own source spells, so that naming it quotes no run's data."""
    return name.isidentifier() and re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", template_source) is not None


def _make_security_error_msg(*, security_error: SecurityError, template_source: str) -> str:
    """The sandbox's refusal, its own wording kept where it quotes no run's data, a fixed description otherwise.

    A refused read names the attribute the template reached for, which a template reading ``obj[key]`` takes from the
    run's data: the attribute is named only when the template spells it. A refusal worded by Jinja2 itself, not by the
    sandbox, is written as a fixed description.
    """
    refusal = security_error.message or ""
    read_refusal = REFUSED_READ_PATTERN.match(refusal)
    if read_refusal is not None and not _is_spelled_in_template(name=read_refusal["attribute"], template_source=template_source):
        refusal = f"A template may not read an unsafe name on a '{read_refusal['type_name']}' value."
    elif not refusal.startswith(SANDBOX_REFUSAL_PREFIX):
        description = "the template reached for an attribute, a method or a call the sandbox does not allow"
        refusal = _describe_render_error(description=description, render_error=security_error)
    return f"Jinja2 render — refused by the template sandbox: {refusal}"


# A template nesting macro calls or recursive loops deep enough reaches Python's recursion limit before
# its budget, which is the same overspending by another name.
_RECURSION_MSG = "Jinja2 render — refused by the render budget: the template nests calls deeper than Python allows."


def _make_budget_error_msg(*, budget_error: RenderBudgetExceededError) -> str:
    # Like a refusal, the message names the operation and its size, never the template source or a value.
    return f"Jinja2 render — refused by the render budget: {budget_error}"


def _make_own_error_msg(*, error_label: str, error: Jinja2StuffError | Jinja2ContextError) -> str:
    # A refusal of Pipelex's own filters, whose message, like every raise site's of Pipelex, holds no run's data.
    return f"Jinja2 render — {error_label}: '{error}'"


def _make_undefined_error_msg(*, undefined_error: UndefinedError, template_source: str) -> str:
    variable_name = undefined_variable_name(undefined_error=undefined_error, template_source=template_source)
    description = f"the template reads '{variable_name}', which is not defined" if variable_name else "the template reads a value that is not defined"
    return f"Jinja2 render — undefined error: {_describe_render_error(description=description, render_error=undefined_error)}"


def _make_invalid_template_error(*, template_error: TemplateError, template_owner: TemplateOwner) -> Jinja2TemplateInvalidError:
    """The error of a template that cannot render as written, coded by its owner.

    Its message gives Jinja2's own finding (`TemplateError.message`, which names the filter, test or template the
    template reached for), never the template source nor the line Jinja2 would quote with it, so on a method's
    template it can be the ``finding`` parameter its problem shows the caller.
    """
    if isinstance(template_error, TemplateNotFound):
        # A template without a loader (every method template) has nothing to include or extend. The name is left out:
        # an include can name its template by a value of the run's data.
        fault = "template not found: the template includes, imports or extends a template it cannot reach."
    else:
        fault = template_error.message or type(template_error).__name__
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


def _make_render_failure(*, render_error: BaseException, template_source: str, template_owner: TemplateOwner) -> ToolError:
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
        budget_msg = _make_budget_error_msg(budget_error=render_error) if isinstance(render_error, RenderBudgetExceededError) else _RECURSION_MSG
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
        return _make_invalid_template_error(template_error=render_error, template_owner=template_owner)
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
