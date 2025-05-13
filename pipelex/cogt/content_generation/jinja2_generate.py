# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pipelex.cogt.content_generation.assignment_models import Jinja2Assignment
from pipelex.hub import get_template_provider
from pipelex.tools.templating.jinja2_rendering import render_jinja2


# TODO: get rid of this intermediate call which seems useless, or explain why it stays
async def jinja2_gen_text(jinja2_assignment: Jinja2Assignment) -> str:
    jinja2_text: str = await render_jinja2(
        template_category=jinja2_assignment.template_category,
        template_provider=get_template_provider(),
        temlating_context=jinja2_assignment.context,
        jinja2_name=jinja2_assignment.jinja2_name,
        jinja2=jinja2_assignment.jinja2,
        prompting_style=jinja2_assignment.prompting_style,
    )

    return jinja2_text
