from pipelex.tools.exceptions import ToolException


class TemplateSyntaxError(ToolException):
    pass


class Jinja2StuffError(ToolException):
    pass


class Jinja2ContextError(ToolException):
    pass


class Jinja2RenderError(ToolException):
    pass


class Jinja2DetectVariablesError(ToolException):
    pass
