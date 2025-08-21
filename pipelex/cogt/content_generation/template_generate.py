from pipelex.cogt.content_generation.assignment_models import TemplateAssignment
from pipelex.hub import get_template_provider
from pipelex.tools.templating.template_rendering import render_template


# TODO: get rid of this intermediate call which seems useless, or explain why it stays
async def template_gen_text(template_assignment: TemplateAssignment) -> str:
    template_text: str = await render_template(
        template_category=template_assignment.template_category,
        template_provider=get_template_provider(),
        temlating_context=template_assignment.context,
        template_name=template_assignment.template_name,
        template=template_assignment.template,
        prompting_style=template_assignment.prompting_style,
    )

    return template_text
