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


class Jinja2StuffError(ToolError):
    pass


class Jinja2ContextError(ToolError):
    pass


class Jinja2DetectVariablesError(ToolError):
    pass
