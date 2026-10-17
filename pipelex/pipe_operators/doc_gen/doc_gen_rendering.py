"""Rendering a `PipeDocGen` step's templates, in its compose stage and in its print stage alike.

Every template of a document renders with a strict undefined, so a value the template reads that does not exist fails
the step rather than printing as empty text. The compose stage renders the filename and an inline HTML template; the
print stage renders an HTML template file, which it reads through the method file store (`DocGenTemplateFileStage`).
Both raise the same errors, worded the same way.
"""

from typing import Any

from jinja2.exceptions import UndefinedError
from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.templating.template_preprocessor import rewrite_template_sigils
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenRunError, PipeDocGenUndefinedValueError
from pipelex.tools.jinja2.exceptions import Jinja2TemplateInvalidError, Jinja2TemplateRenderError
from pipelex.tools.jinja2.jinja2_rendering import template_line_of, undefined_variable_name
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
    except Jinja2TemplateInvalidError as exc:
        if not exc.template_owner.is_method:
            # One of Pipelex's own templates, reached from the method's render: ours, kept as it is.
            raise
        # The template is the method author's own: the message names the step, the template and what Jinja2 refused.
        msg = f"PipeDocGen '{pipe_code}' could not render its {label}: {exc.fault}"
        raise (
            PipeDocGenRunError(msg).with_error_code(CoreCode.METHOD_TEMPLATE_INVALID).with_params(pipe=pipe_code, template=label, finding=exc.fault)
        ) from exc
    except Jinja2TemplateRenderError as exc:
        undefined_error = exc.__cause__
        if isinstance(undefined_error, UndefinedError):
            # Raised from Jinja's own error, so that this is the root fault a verdict or a run's problem names. Its text
            # can quote a key of the run's data the template reached for, so the name is given only when the template
            # itself spells it, read off the source Jinja2 compiled, its sigils rewritten, and the line Jinja2 failed at
            # says where.
            variable_name = undefined_variable_name(undefined_error=undefined_error, template_source=rewrite_template_sigils(template))
            what = f"it reads '{variable_name}', which is not defined" if variable_name else "it reads a value that is not defined"
            template_line = template_line_of(render_error=undefined_error)
            where = f" (line {template_line})" if template_line is not None else ""
            msg = (
                f"PipeDocGen '{pipe_code}' could not render its {label}: {what}{where}. "
                "Every value a document's template reads must exist: check the name against the input's concept, "
                "or test an optional value first with {% if ... %}."
            )
            raise PipeDocGenUndefinedValueError(msg).with_params(pipe=pipe_code, variable=variable_name) from undefined_error
        msg = f"PipeDocGen '{pipe_code}' could not render its {label}: {exc}"
        raise PipeDocGenRunError(msg) from exc
