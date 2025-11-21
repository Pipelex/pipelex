from pipelex.system.exceptions import ToolError


class Jinja2TemplateSyntaxError(ToolError):
    pass


class Jinja2TemplateRenderError(ToolError):
    pass


class Jinja2StuffError(ToolError):
    pass


class Jinja2ContextError(ToolError):
    pass


class Jinja2DetectVariablesError(ToolError):
    pass
