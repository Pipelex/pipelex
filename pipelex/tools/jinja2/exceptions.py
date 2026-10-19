from typing import Any

from jinja2.exceptions import SecurityError as JinjaSecurityError
from mthds.protocol.problem.models import ProblemLocation
from mthds.protocol.problem.registry import CoreCode
from typing_extensions import Self, override

from pipelex.base_exceptions import SecurityError
from pipelex.errors.error_code_declaration import ErrorCodeSet
from pipelex.errors.problem import make_location
from pipelex.system.exceptions import ToolError
from pipelex.tools.jinja2.template_owner import TemplateOwner


class Jinja2TemplateSyntaxError(ToolError):
    """A template Jinja2 cannot parse; the blueprint validators report it as the method's syntax."""

    error_code = CoreCode.METHOD_SYNTAX


class Jinja2TemplateRenderError(ToolError):
    """A template failed to render.

    The render serves the method's templates and Pipelex's own, and the raise site chooses the code by the template's
    owner (`TemplateOwner`). On a method's template the failure can come from the template or from this run's data
    (a value that is absent or shaped otherwise this time), and nothing where it is raised tells the two apart, so it
    is `pipe.template_render_failed`, the default; a filter's own finding about the template, such as a format it does
    not know, is `method.template_invalid`. On Pipelex's own template it is ours: `runtime.unexpected`, whose message
    never reaches a caller, since a caller must not read that template's source.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.PIPE_TEMPLATE_RENDER_FAILED,
        others=(CoreCode.METHOD_TEMPLATE_INVALID, CoreCode.RUNTIME_UNEXPECTED),
    )


class Jinja2TemplateInvalidError(Jinja2TemplateRenderError):
    """A template that cannot render as written, whatever the data.

    It names a filter or a test its environment does not define, or another construct Jinja2 refuses when it compiles
    the template, or, for a filter or test inside a branch, only when that branch renders. Found at render, it is
    still the template's fault: `method.template_invalid` on a method's template, the default, whose message names
    the construct Jinja2 refused and never quotes the template source; `runtime.unexpected` on Pipelex's own.
    """

    error_code = ErrorCodeSet(default=CoreCode.METHOD_TEMPLATE_INVALID, others=(CoreCode.RUNTIME_UNEXPECTED,))

    def __init__(self, message: str, *, fault: str, template_owner: TemplateOwner):
        super().__init__(message)
        # Jinja2's own finding, such as "No filter named 'frob' found.", which names the construct and never the
        # template source: the part of the message a pipe that knows the template's field quotes in its own.
        self.fault = fault
        # Whose template it is. A pipe rendering a method's template can reach one of Pipelex's own inside the same
        # render, such as the deployment's structure prompt beside a PipeLLM's prompt: it reports a refusal of its
        # template only for the method's, and lets Pipelex's own go on as ours.
        self.template_owner = template_owner


class Jinja2TemplateSecurityError(SecurityError):
    """A template reached for something the sandbox policy refuses (`jinja2_sandbox.py`).

    That is an undeclared private name, or a call that is not a method of a plain value. Its message names the type
    the refused name was reached on, and the attribute or the callable only when the parsed template spells it, since
    a name reached by a value is the run's data; it never quotes the template source, since the same render serves
    Pipelex's own templates. On a method's template it is `security.template_refused`, the default; on
    Pipelex's own, our template tripping our sandbox is our bug, `runtime.unexpected`.

    The refused attribute or callable is a name the template's own source spells, as in ``{{ topic['_owner'] }}``, or a
    value of the run's data, as in ``{{ topic[topic.text] }}``. The render gives it as ``refused_name`` only in the first
    case, and the problem's ``name`` with it; in the second the problem carries no ``name``, the run's input never
    reaching the caller, and its sentences say that the template looked the name up from the run's data
    (`pipelex.errors.problem`). The pipe whose template it was locates it on the template's field, ``template_field``
    (`locating_template_refusal`).

    A `SecurityError`, not a `ToolError`, in the family of `UriReadRefusedError`, `SsrfBlockedError` and
    `UnsafeSchemaError`, so that a host catching that family never absorbs it into a domain answer and never retries
    it. A type of its own, apart from `Jinja2TemplateRenderError`, so that a refusal reads apart from a template that
    fails for any other reason.
    """

    error_code = ErrorCodeSet(default=CoreCode.SECURITY_TEMPLATE_REFUSED, others=(CoreCode.RUNTIME_UNEXPECTED,))

    def __init__(self, message: str, *, refused_name: str | None = None):
        super().__init__(message)
        # The attribute or the callable the template reached for, by its bare name, when the template's source spells it.
        self.refused_name = refused_name
        # The field of the pipe whose template was refused, such as `template` or `prompt`, which that pipe gives.
        self.template_field: str | None = None

    def with_template_field(self, *, template_field: str) -> Self:
        """Name, where the pipe that rendered the template catches the refusal, the field its template is written in.

        Returns:
            This error, so that the catch site can re-raise it.
        """
        self.template_field = template_field
        return self

    @override
    def problem_params(self) -> dict[str, Any]:
        if self.refused_name is None:
            return {}
        return {"name": self.refused_name}

    @override
    def problem_location(self) -> ProblemLocation | None:
        return make_location(field=self.template_field)


class Jinja2TemplateBudgetError(ToolError):
    """A render tried to spend more than its budget (`jinja2_render_budget.py`).

    Its template repeated, padded, joined, looped or recursed past what one render may allocate or compute. On a
    method's template that is the method's to fix, `pipe.template_budget_exceeded`, the default; a Pipelex template
    only gets there on data too large to display, which is the caller's input, `input.too_large`. The message names
    the operation and its size, never the template source or a value.
    """

    error_code = ErrorCodeSet(default=CoreCode.PIPE_TEMPLATE_BUDGET_EXCEEDED, others=(CoreCode.INPUT_TOO_LARGE,))


class Jinja2StuffError(ToolError):
    """A render context key is already taken, such as a method variable named like the reserved `tag_style`.

    A method naming a variable like a reserved key is `method.name_conflict`, the default; the same collision on a
    context Pipelex built for its own template is ours, `runtime.unexpected`.
    """

    error_code = ErrorCodeSet(default=CoreCode.METHOD_NAME_CONFLICT, others=(CoreCode.RUNTIME_UNEXPECTED,))


class Jinja2ContextError(ToolError):
    """A filter could not work with what the render context or the value gave it.

    A value the filter cannot take, such as an undefined one, is `pipe.template_render_failed`, the default; a format
    name the template wrote and the filter does not know is `method.template_invalid`; a render set up without the
    templating style or the image registry a filter needs is ours, `runtime.unexpected`. The render functions wrap it
    into `Jinja2TemplateRenderError`, which takes its code.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.PIPE_TEMPLATE_RENDER_FAILED,
        others=(CoreCode.METHOD_TEMPLATE_INVALID, CoreCode.RUNTIME_UNEXPECTED),
    )


class Jinja2DetectVariablesError(ToolError):
    """A template whose variables cannot be read because it does not parse; its callers report the method's syntax."""

    error_code = CoreCode.METHOD_SYNTAX


class SandboxRefusalError(JinjaSecurityError):
    """A refusal of the template sandbox (`jinja2_sandbox.py`), worded with the names it quotes and without them.

    It is Jinja2's ``SecurityError``, the carrier Jinja2 expects a refusal by, raised at the point of access. Its message
    names what the template reached for: an attribute it read, the name it stored a callable under in a namespace, the
    method or function it called. A template reaching ``obj[key]``, ``obj | attr(key)`` or ``namespace({key: value})``
    takes that name from the run's data, so the refusal also carries the names its message quotes, ``named``, and its
    wording without them, ``anonymous_message``: the render reporting it keeps the message only when the template's own
    source spells every name it quotes (`pipelex.tools.jinja2.jinja2_rendering`). ``refused_name`` is the bare name of
    the attribute or the callable it refused, which the render passes on as the ``name`` of `security.template_refused`
    under the same rule, and withholds otherwise.
    """

    def __init__(self, message: str, *, named: tuple[str, ...], anonymous_message: str, refused_name: str):
        super().__init__(message)
        self.named = named
        self.anonymous_message = anonymous_message
        self.refused_name = refused_name
