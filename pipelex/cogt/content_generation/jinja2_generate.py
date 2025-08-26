from pipelex.cogt.content_generation.assignment_models import Jinja2Assignment
from pipelex.hub import get_template_provider
from pipelex.tools.templating.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.templating.jinja2_rendering import render_jinja2
from pipelex.tools.templating.template_preprocessor import preprocess_template


# TODO: get rid of this intermediate call which seems useless, or explain why it stays
async def jinja2_gen_text(jinja2_assignment: Jinja2Assignment) -> str:
    if jinja2_assignment.jinja2:
        jinja2_assignment.jinja2 = preprocess_template(template=jinja2_assignment.jinja2)
        check_jinja2_parsing(jinja2_assignment.jinja2)

    jinja2_text: str = await render_jinja2(
        template_category=jinja2_assignment.template_category,
        template_provider=get_template_provider(),
        temlating_context=jinja2_assignment.context,
        jinja2_name=jinja2_assignment.jinja2_name,
        jinja2=jinja2_assignment.jinja2,
        prompting_style=jinja2_assignment.prompting_style,
    )

    return jinja2_text
