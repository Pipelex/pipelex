from pipelex.cogt.content_generation.assignment_models import Jinja2Assignment
from pipelex.tools.templating.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.templating.jinja2_rendering import render_jinja2
from pipelex.tools.templating.template_preprocessor import preprocess_template


async def jinja2_gen_text(jinja2_assignment: Jinja2Assignment) -> str:
    # Intermediate call to preprocess the template with our syntax patterns (@, $, @?, etc.)
    if jinja2_assignment.source:
        jinja2_assignment.source = preprocess_template(template=jinja2_assignment.source)
        check_jinja2_parsing(jinja2_assignment.source)

    jinja2_text: str = await render_jinja2(
        template_category=jinja2_assignment.category,
        temlating_context=jinja2_assignment.context,
        template_source=jinja2_assignment.source,
        templating_style=jinja2_assignment.templating_style,
    )

    return jinja2_text
