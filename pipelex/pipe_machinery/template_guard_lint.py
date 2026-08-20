"""Shared template guard-lint (optionals design D7), applied by every pipe that renders
authored templates over its inputs (PipeLLM prompts, PipeCompose templates, PipeCondition
expressions): each reference to a declared-optional (`?`) input must be guarded, otherwise
validation fails with `OPTIONAL_INPUT_UNGUARDED` and the precise fix.
"""

from pipelex.cogt.templating.template_preprocessor import rewrite_template_sigils
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_optional_guards import detect_unguarded_optional_references
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.validation_error_types import PipeValidationErrorType


def lint_optional_input_guards(
    *,
    pipe_code: str,
    domain_code: str | None,
    inputs: InputStuffSpecs,
    template_source: str,
    template_category: TemplateCategory,
    template_label: str,
) -> None:
    """Raise `OPTIONAL_INPUT_UNGUARDED` when the template references a declared-optional input
    without a guard.

    The template is given in authored form: sigils (`@var`, `@?var`, `$var`) are rewritten to
    their Jinja2 form before the walk, so `@?var` counts as a guard and a plain `@var` on an
    optional input counts as an unguarded reference (the `tag` filter raises on an undefined
    value at render time).

    Args:
        pipe_code: The pipe being validated (for the error).
        domain_code: The pipe's domain (for the error).
        inputs: The pipe's declared inputs — optional (`?`) ones drive the lint.
        template_source: The authored template source.
        template_category: The template's category (LLM_PROMPT, EXPRESSION, ...).
        template_label: Which template this is, for the message ("prompt", "system_prompt",
            "template", "expression").
    """
    optional_variable_names = {input_name for input_name, stuff_spec in inputs.root.items() if stuff_spec.presence.is_optional}
    if not optional_variable_names:
        return
    try:
        findings = detect_unguarded_optional_references(
            template_category=template_category,
            template_source=rewrite_template_sigils(template_source),
            optional_variable_names=optional_variable_names,
        )
    except Jinja2DetectVariablesError:
        # An unparseable template is not this lint's concern: the template-parsing gates
        # (blueprint validation, the dry-run variable detection) report syntax errors through
        # their own typed channels. Raising here — often inside a pydantic model validator —
        # would leak an internal exception type past callers expecting ValidationError.
        return
    if not findings:
        return
    finding = findings[0]
    msg = (
        f"In the {template_label} of pipe '{pipe_code}', the reference '{{{{ {finding.path} }}}}' uses the optional input "
        f"'{finding.variable_name}' unguarded — when the value is absent, the variable is undefined in the template. "
        f"Guard every use: write `@?{finding.variable_name}` instead of `@{finding.variable_name}`, wrap the block in "
        f"`{{% if {finding.variable_name} %}}...{{% endif %}}`, or use an inline conditional "
        f"(`... if {finding.variable_name} is defined else ...`)."
    )
    raise PipeValidationError(
        message=msg,
        error_type=PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED,
        domain_code=domain_code,
        pipe_code=pipe_code,
        variable_names=[finding.variable_name],
        explanation=f"Unguarded reference '{finding.path}' to optional input '{finding.variable_name}' in the {template_label}.",
    )
