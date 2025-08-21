from typing import Optional

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


def make_jinja2_error_explanation(template_name: Optional[str], template_text: Optional[str]) -> str:
    explanation = ""
    if template_name:
        explanation += f"\nTemplate name: '{template_name}'\n"
    if template_text:
        explanation += f"\ntemplate:\n\n{template_text}'\n"
    if not explanation:
        explanation = "No template text or template name"
    return explanation
