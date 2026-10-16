"""Rendering a `PipeDocGen` step's templates, in its compose stage and in its print stage alike.

Every template of a document renders with a strict undefined, so a value the template reads that does not exist fails
the step rather than printing as empty text. The compose stage renders the filename and an inline HTML template; the
print stage renders an HTML template file, which it reads through the method file store (`DocGenTemplateFileStage`).
Both raise the same errors, worded the same way.
"""

from typing import Any

from jinja2.exceptions import UndefinedError

from pipelex.cogt.templating.template_rendering import render_template
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenRunError, PipeDocGenUndefinedValueError
from pipelex.tools.jinja2.exceptions import Jinja2TemplateRenderError
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TemplatingStyle


async def render_doc_gen_template(
    *,
    pipe_code: str,
    template: str,
    category: TemplateCategory,
    context: dict[str, Any],
    label: str,
    templating_style: TemplatingStyle | None = None,
) -> str:
    """A template of the step `pipe_code` rendered with `context`, every value it reads required to exist.

    Raises:
        PipeDocGenUndefinedValueError: The template reads a value that does not exist.
        PipeDocGenRunError: The template could not be rendered for another reason.
    """
    try:
        return await render_template(
            template=template,
            category=category,
            context=context,
            templating_style=templating_style,
            is_undefined_strict=True,
        )
    except Jinja2TemplateRenderError as exc:
        undefined_error = exc.__cause__
        if isinstance(undefined_error, UndefinedError):
            # Raised from Jinja's own error rather than from the tools-layer wrapper, whose message quotes the
            # template and is not caller-facing, so that this is the root fault a verdict or a run report names.
            msg = (
                f"PipeDocGen '{pipe_code}' could not render its {label}: {undefined_error.message}. "
                "Every value a document's template reads must exist: check the name against the input's concept, "
                "or test an optional value first with {% if ... %}."
            )
            raise PipeDocGenUndefinedValueError(msg) from undefined_error
        msg = f"PipeDocGen '{pipe_code}' could not render its {label}: {exc}"
        raise PipeDocGenRunError(msg) from exc
