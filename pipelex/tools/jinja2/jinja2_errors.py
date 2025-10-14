from pipelex.system.exceptions import ToolException


class Jinja2TemplateSyntaxError(ToolException):
    pass


class Jinja2TemplateRenderError(ToolException):
    pass


class Jinja2StuffError(ToolException):
    pass


class Jinja2ContextError(ToolException):
    pass


class Jinja2DetectVariablesError(ToolException):
    pass
