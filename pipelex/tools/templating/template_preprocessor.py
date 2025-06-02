import re
from re import Match
from typing import List

from pipelex.tools.templating.jinja2_errors import Jinja2TemplateError
from pipelex.tools.templating.jinja2_filters import ALLOWED_FILTERS


def _detect_non_existent_filters(template_str: str) -> None:
    """Check a template string for non-existent Jinja2 filters.

    Args:
        template_str: The template string to check

    Raises:
        Jinja2TemplateError: If any non-allowed filters are found
    """
    # Pattern to match Jinja2 filter syntax: {{ variable|filter() }} or {{ variable|filter(param) }}
    # This handles:
    # - {{ variable|filter }}
    # - {{ variable|filter() }}
    # - {{ variable|filter(param) }}
    # - {{ variable|filter(param1, param2) }}
    filter_pattern = r"\{\{\s*[^|}]+\|\s*([a-zA-Z0-9_]+)(?:\([^)]*\))?\s*\}\}"
    matches = re.finditer(filter_pattern, template_str)

    invalid_filters: List[str] = []
    for match in matches:
        filter_name = match.group(1)
        if filter_name not in ALLOWED_FILTERS:
            invalid_filters.append(filter_name)

    if invalid_filters:
        raise Jinja2TemplateError(f"Invalid Jinja2 filters found: {invalid_filters}. Only the following filters are allowed: {ALLOWED_FILTERS}")


# Handle @variable patterns
def replace_at_variable(match: Match[str]) -> str:
    variable: str = match.group(1)
    return f'{{{{ {variable}|tag("{variable}") }}}}'


# Handle @?variable patterns (optional insertion)
def replace_optional_at_variable(match: Match[str]) -> str:
    variable: str = match.group(1)
    return f'{{% if {variable} %}}{{{{ {variable}|tag("{variable}") }}}}{{% endif %}}'


# Handle $variable patterns
def replace_dollar_variable(match: Match[str]) -> str:
    variable: str = match.group(1)
    if variable.endswith("."):
        # trailing dot can't be in a variable name so it must be a punctuation in the template sentence, so we remove it
        variable = variable[:-1]
        return f"{{{{ {variable}|format() }}}}."
    return f"{{{{ {variable}|format() }}}}"


def preprocess_template(template: str) -> str:
    """
    Preprocess a template string to interpret our syntax patterns and convert them to Jinja2 syntax.
    Also, detect the use of non-existent filters.
    """
    _detect_non_existent_filters(template_str=template)

    processed_template = template
    changes_made = False

    # TODO: allow escape patterns

    # Replace @?variable patterns (optional insertion) - must come before @variable
    new_template = re.sub(r"@\?(?![0-9])([a-zA-Z0-9_.]+)", replace_optional_at_variable, processed_template)
    if new_template != processed_template:
        changes_made = True
        processed_template = new_template

    # Replace @variable patterns
    new_template = re.sub(r"@(?![0-9])([a-zA-Z0-9_.]+)", replace_at_variable, processed_template)
    if new_template != processed_template:
        changes_made = True
        processed_template = new_template

    # Replace $variable patterns
    new_template = re.sub(r"\$(?![0-9])([a-zA-Z0-9_.]+)", replace_dollar_variable, processed_template)
    if new_template != processed_template:
        changes_made = True
        processed_template = new_template

    if changes_made:
        pass

    return processed_template
