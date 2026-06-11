from pipelex.cogt.content_generation.assignment_models import TemplatingAssignment
from pipelex.cogt.content_generation.dry_mock import dry_templating_gen_text
from pipelex.cogt.templating.template_rendering import render_template


async def templating_gen_text(templating_assignment: TemplatingAssignment) -> str:
    if templating_assignment.cogt_run_params.run_mode.is_dry:
        return dry_templating_gen_text(templating_assignment)
    templated_text: str = await render_template(
        template=templating_assignment.template,
        category=templating_assignment.category,
        context=templating_assignment.context,
        templating_style=templating_assignment.templating_style,
    )

    return templated_text
