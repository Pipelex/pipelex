from pipelex.base_exceptions import ErrorDomain
from pipelex.system.exceptions import ToolError


class Jinja2TemplateSyntaxError(ToolError):
    pass


class Jinja2TemplateRenderError(ToolError):
    # Not classified as the caller's fault, although a run reaches it with the caller's own template:
    # a failure of that template can come from the template (a reference or an expression its values
    # never support, which validation's dry run also refuses) or from this run's data (a value that is
    # absent or shaped otherwise this time), and nothing where it is raised tells the two apart. The
    # same render also serves Pipelex's own templates, whose source a caller must not read.
    pass


class Jinja2TemplateSecurityError(ToolError):
    # A template reached for something the sandbox policy refuses (`jinja2_sandbox.py`): an undeclared
    # private name, or a call that is not a method of a plain value. Its message names the attribute or
    # the callable and the type it was reached on, and never quotes the template source, since the same
    # render serves Pipelex's own templates. A type of its own, apart from `Jinja2TemplateRenderError`,
    # so that the classification of render-time template failures can tell a refusal from the rest,
    # although for now both are classified alike: runtime domain, message not caller-facing.
    pass


class Jinja2TemplateBudgetError(ToolError):
    # A render tried to spend more than its budget (`jinja2_render_budget.py`): its template repeated,
    # padded, joined, looped or recursed past what one render may allocate or compute. The template is
    # the caller's own, and a Pipelex template can only get there on data too large to display, which
    # is still the caller's input, so it is the caller's to fix. The message names the operation and
    # its size, never the template source or a value.
    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True
    _declared_title = "Template render budget exceeded"


class Jinja2StuffError(ToolError):
    pass


class Jinja2ContextError(ToolError):
    pass


class Jinja2DetectVariablesError(ToolError):
    pass
