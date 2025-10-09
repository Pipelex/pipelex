from pipelex.cogt.content_generation.assignment_models import TemplatingAssignment
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2


async def templating_gen_text(templating_assignment: TemplatingAssignment) -> str:
    # Intermediate call to preprocess the template with our syntax patterns (@, $, @?, etc.)
    if templating_assignment.template:
        templating_assignment.template = preprocess_template(template=templating_assignment.template)
        check_jinja2_parsing(templating_assignment.template)

    templated_text: str = await render_jinja2(
        template_category=templating_assignment.category,
        temlating_context=templating_assignment.context,
        template_source=templating_assignment.template,
        templating_style=templating_assignment.templating_style,
    )

    return templated_text
