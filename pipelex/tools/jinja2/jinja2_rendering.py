from collections.abc import Awaitable
from typing import Any, Protocol

from jinja2.exceptions import (
    TemplateAssertionError,
    TemplateSyntaxError,
    UndefinedError,
)

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.tools.jinja2.jinja2_environment import (
    make_jinja2_env_from_registry,
    make_jinja2_env_without_loader,
)
from pipelex.tools.jinja2.jinja2_errors import (
    Jinja2ContextError,
    Jinja2StuffError,
    Jinja2TemplateRenderError,
)
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey


def _add_to_templating_context(temlating_context: dict[str, Any], jinja2_context_key: Jinja2ContextKey, value: Any) -> None:
    if jinja2_context_key in temlating_context:
        msg = f"Jinja2 context key '{jinja2_context_key}' already in temlating_context"
        raise Jinja2StuffError(msg)
    temlating_context[jinja2_context_key] = value


class _Jinja2Template(Protocol):
    def render(self, **kwargs: Any) -> str: ...

    def render_async(self, **kwargs: Any) -> Awaitable[str]: ...


def _compile_jinja2_template(
    template_source: str,
    template_category: TemplateCategory,
    *,
    use_registry: bool = False,
) -> _Jinja2Template:
    if use_registry:
        jinja2_env = make_jinja2_env_from_registry(template_category=template_category)
    else:
        jinja2_env = make_jinja2_env_without_loader(template_category=template_category)

    try:
        return jinja2_env.from_string(template_source)
    except TemplateAssertionError as exc:
        msg = f"Jinja2 render error: '{exc}', template_source:\n{template_source}"
        raise Jinja2TemplateRenderError(msg) from exc


def _prepare_templating_context(
    temlating_context: dict[str, Any],
    templating_style: TemplatingStyle | None,
) -> dict[str, Any]:
    # Create a copy to avoid mutating the caller's original dictionary
    prepared_templating_context = temlating_context.copy()
    if templating_style:
        _add_to_templating_context(
            temlating_context=prepared_templating_context,
            jinja2_context_key=Jinja2ContextKey.TAG_STYLE,
            value=templating_style.tag_style,
        )
        _add_to_templating_context(
            temlating_context=prepared_templating_context,
            jinja2_context_key=Jinja2ContextKey.TEXT_FORMAT,
            value=templating_style.text_format,
        )
    return prepared_templating_context


def _make_type_error_msg(template_source: str, temlating_context: dict[str, Any], type_error: TypeError) -> str:
    context_vars = ", ".join(f"'{key}'" for key in temlating_context)
    return (
        f"Jinja2 render — type error: '{type_error}'. "
        f"This often happens when trying to iterate over a method or accessing an attribute incorrectly. "
        f"Template source:\n{template_source}\n"
        f"Available context variables: {context_vars}"
    )


def _make_non_type_error_msg(
    template_source: str,
    error_label: str,
    error: Jinja2StuffError | TemplateSyntaxError | UndefinedError | Jinja2ContextError,
) -> str:
    return f"Jinja2 render — {error_label}: '{error}', template_source:\n{template_source}"


def _render_template_sync(template_source: str, template: _Jinja2Template, temlating_context: dict[str, Any]) -> str:
    try:
        generated_text: str = template.render(**temlating_context)
    except Jinja2StuffError as exc:
        msg = _make_non_type_error_msg(template_source=template_source, error_label="stuff error", error=exc)
        raise Jinja2TemplateRenderError(msg) from exc
    except TemplateSyntaxError as exc:
        msg = _make_non_type_error_msg(template_source=template_source, error_label="syntax error", error=exc)
        raise Jinja2TemplateRenderError(msg) from exc
    except UndefinedError as exc:
        msg = _make_non_type_error_msg(template_source=template_source, error_label="undefined error", error=exc)
        raise Jinja2TemplateRenderError(msg) from exc
    except Jinja2ContextError as exc:
        msg = _make_non_type_error_msg(template_source=template_source, error_label="context error", error=exc)
        raise Jinja2TemplateRenderError(msg) from exc
    except TypeError as exc:
        msg = _make_type_error_msg(template_source=template_source, temlating_context=temlating_context, type_error=exc)
        raise Jinja2TemplateRenderError(msg) from exc
    return generated_text


async def _render_template_async(template_source: str, template: _Jinja2Template, temlating_context: dict[str, Any]) -> str:
    try:
        generated_text: str = await template.render_async(**temlating_context)
    except Jinja2StuffError as exc:
        msg = _make_non_type_error_msg(template_source=template_source, error_label="stuff error", error=exc)
        raise Jinja2TemplateRenderError(msg) from exc
    except TemplateSyntaxError as exc:
        msg = _make_non_type_error_msg(template_source=template_source, error_label="syntax error", error=exc)
        raise Jinja2TemplateRenderError(msg) from exc
    except UndefinedError as exc:
        msg = _make_non_type_error_msg(template_source=template_source, error_label="undefined error", error=exc)
        raise Jinja2TemplateRenderError(msg) from exc
    except Jinja2ContextError as exc:
        msg = _make_non_type_error_msg(template_source=template_source, error_label="context error", error=exc)
        raise Jinja2TemplateRenderError(msg) from exc
    except TypeError as exc:
        msg = _make_type_error_msg(template_source=template_source, temlating_context=temlating_context, type_error=exc)
        raise Jinja2TemplateRenderError(msg) from exc
    return generated_text


def render_jinja2_sync(
    template_source: str,
    template_category: TemplateCategory,
    temlating_context: dict[str, Any],
    templating_style: TemplatingStyle | None = None,
    *,
    use_registry: bool = False,
) -> str:
    template = _compile_jinja2_template(
        template_source=template_source,
        template_category=template_category,
        use_registry=use_registry,
    )
    prepared_templating_context = _prepare_templating_context(
        temlating_context=temlating_context,
        templating_style=templating_style,
    )
    return _render_template_sync(
        template_source=template_source,
        template=template,
        temlating_context=prepared_templating_context,
    )


async def render_jinja2_async(
    template_source: str,
    template_category: TemplateCategory,
    temlating_context: dict[str, Any],
    templating_style: TemplatingStyle | None = None,
    *,
    use_registry: bool = False,
) -> str:
    template = _compile_jinja2_template(
        template_source=template_source,
        template_category=template_category,
        use_registry=use_registry,
    )
    prepared_templating_context = _prepare_templating_context(
        temlating_context=temlating_context,
        templating_style=templating_style,
    )
    return await _render_template_async(
        template_source=template_source,
        template=template,
        temlating_context=prepared_templating_context,
    )
