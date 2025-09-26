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


def make_jinja2_error_explanation(jinja2_name: str | None, template_text: str | None) -> str:
    explanation = ""
    if jinja2_name:
        explanation += f"\nJinja2 name: '{jinja2_name}'\n"
    if template_text:
        explanation += f"\ntemplate:\n\n{template_text}'\n"
    if not explanation:
        explanation = "No template text or Jinja2 name"
    return explanation
