from temporalio import activity

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import TemplatingAssignment
from pipelex.cogt.content_generation.templating_generate import templating_gen_text


@activity.defn
async def act_jinja2_gen_text(jinja2_assignment: TemplatingAssignment) -> str:
    log.dev("act_jinja2_gen_text")
    return await templating_gen_text(templating_assignment=jinja2_assignment)
