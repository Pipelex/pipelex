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

from pipelex.base_exceptions import PipelexError, PipelexUnexpectedError
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


def _make_type_error_msg(template_source: str, *, templating_context: dict[str, Any], type_error: TypeError) -> str:
    context_vars = ", ".join(f"'{key}'" for key in templating_context)
    return (
        f"Jinja2 render — type error: '{type_error}'. "
        f"This often happens when trying to iterate over a method or accessing an attribute incorrectly. "
        f"Template source:\n{template_source}\n"
        f"Available context variables: {context_vars}"
    )


def _make_security_error_msg(*, security_error: SecurityError) -> str:
    # The template source is left out on purpose: the same render serves Pipelex's own templates.
    return f"Jinja2 render — refused by the template sandbox: {security_error}"


# A template nesting macro calls or recursive loops deep enough reaches Python's recursion limit before
# its budget, which is the same overspending by another name.
_RECURSION_MSG = "Jinja2 render — refused by the render budget: the template nests calls deeper than Python allows."


def _make_budget_error_msg(*, budget_error: RenderBudgetExceededError) -> str:
    # Like a refusal, the message names the operation and its size, never the template source or a value.
    return f"Jinja2 render — refused by the render budget: {budget_error}"


def _make_non_type_error_msg(
    template_source: str,
    *,
    error_label: str,
    error: Jinja2StuffError | UndefinedError | Jinja2ContextError | FilterArgumentError | ArithmeticError,
) -> str:
    return f"Jinja2 render — {error_label}: '{error}', template_source:\n{template_source}"


def _make_invalid_template_error(*, template_error: TemplateError, template_owner: TemplateOwner) -> Jinja2TemplateInvalidError:
    """The error of a template that cannot render as written, coded by its owner.

    Its message gives Jinja2's own finding (`TemplateError.message`, which names the filter, test or template the
    template reached for), never the template source nor the line Jinja2 would quote with it, so on a method's
    template it reaches the caller under every disclosure mode.
    """
    if isinstance(template_error, TemplateNotFound):
        # A template without a loader (every method template) has nothing to include or extend.
        fault = f"template not found: '{template_error.name}'."
    else:
        fault = template_error.message or type(template_error).__name__
    msg = f"Jinja2 render — the template cannot render as written: {fault}"
    invalid_error = _coded_by_owner(error=Jinja2TemplateInvalidError(msg, fault=fault, template_owner=template_owner), template_owner=template_owner)
    if template_owner.is_method:
        # The message names the construct Jinja2 refused and never the source, so the method's author reads it.
        invalid_error.as_caller_fault()
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
    *, template_source: str, render_error: BaseException, templating_context: dict[str, Any], template_owner: TemplateOwner
) -> ToolError | Jinja2TemplateSecurityError:
    """Translate what a render raised into the error the render reports, coded by the template's owner.

    The order of the arms matters: a refusal of the sandbox, an undefined value and a filter refusing its argument are
    `TemplateRuntimeError`s too, and only what is left of that family, the plain `TemplateRuntimeError` Jinja2 raises
    for the template's own constructs, such as a filter or a test inside a branch that the environment does not define,
    is the template's fault on any input.
    """
    if isinstance(render_error, SecurityError):
        security_msg = _make_security_error_msg(security_error=render_error)
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
        msg = _make_non_type_error_msg(template_source=template_source, error_label="context error", error=render_error)
        return _make_context_render_error(msg=msg, context_error=render_error, template_owner=template_owner)
    if isinstance(render_error, Jinja2StuffError):
        msg = _make_non_type_error_msg(template_source=template_source, error_label="stuff error", error=render_error)
        return _make_data_render_error(msg=msg, template_owner=template_owner)
    if isinstance(render_error, UndefinedError):
        msg = _make_non_type_error_msg(template_source=template_source, error_label="undefined error", error=render_error)
        return _make_data_render_error(msg=msg, template_owner=template_owner)
    if isinstance(render_error, FilterArgumentError):
        # A filter refusing its argument may be refusing this run's value (`reverse` on a value that is not iterable)
        # as well as the template's own literal, which nothing here tells apart, so it is not the template's alone.
        msg = _make_non_type_error_msg(template_source=template_source, error_label="filter argument error", error=render_error)
        return _make_data_render_error(msg=msg, template_owner=template_owner)
    if isinstance(render_error, (TemplateSyntaxError, TemplateNotFound, TemplateRuntimeError)):
        return _make_invalid_template_error(template_error=render_error, template_owner=template_owner)
    if isinstance(render_error, ArithmeticError):
        # The template's own arithmetic, the sandbox's range cap included: `range` raises OverflowError past it.
        msg = _make_non_type_error_msg(template_source=template_source, error_label="arithmetic error", error=render_error)
        return _make_data_render_error(msg=msg, template_owner=template_owner)
    if isinstance(render_error, TypeError):
        msg = _make_type_error_msg(template_source=template_source, templating_context=templating_context, type_error=render_error)
        return _make_data_render_error(msg=msg, template_owner=template_owner)
    msg = f"Jinja2 render — {type(render_error).__name__} is not a failure the render translates"
    raise PipelexUnexpectedError(msg) from render_error


def _render_template_sync(
    template_source: str, *, template: _Jinja2Template, templating_context: dict[str, Any], template_owner: TemplateOwner
) -> str:
    try:
        generated_text: str = template.render(**templating_context)
    except _RENDER_FAILURES as exc:
        raise _make_render_failure(
            template_source=template_source, render_error=exc, templating_context=templating_context, template_owner=template_owner
        ) from exc
    return generated_text


async def _render_template_async(
    template_source: str, *, template: _Jinja2Template, templating_context: dict[str, Any], template_owner: TemplateOwner
) -> str:
    try:
        generated_text: str = await template.render_async(**templating_context)
    except _RENDER_FAILURES as exc:
        raise _make_render_failure(
            template_source=template_source, render_error=exc, templating_context=templating_context, template_owner=template_owner
        ) from exc
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
        template_source=template_source,
        template=template,
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
        template_source=template_source,
        template=template,
        templating_context=prepared_templating_context,
        template_owner=template_owner,
    )
