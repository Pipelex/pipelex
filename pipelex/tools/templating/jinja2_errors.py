from pipelex.tools.exceptions import ToolException


class Jinja2TemplateError(ToolException):
    pass


class Jinja2StuffError(ToolException):
    pass


class Jinja2ContextError(ToolException):
    pass


class Jinja2RenderError(ToolException):
    pass


class Jinja2DetectVariablesError(ToolException):
    pass
