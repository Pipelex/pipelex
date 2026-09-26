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


class Jinja2StuffError(ToolError):
    pass


class Jinja2ContextError(ToolError):
    pass


class Jinja2DetectVariablesError(ToolError):
    pass
