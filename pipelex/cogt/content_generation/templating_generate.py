from pipelex.cogt.content_generation.assignment_models import TemplatingAssignment
from pipelex.cogt.content_generation.dry_mock import dry_templating_gen_text
from pipelex.cogt.content_generation.read_authorization import authorize_assignment_reads
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.pipes.declared_item_count import dry_leaf_limits


async def templating_gen_text(templating_assignment: TemplatingAssignment) -> str:
    authorize_assignment_reads(job_metadata=templating_assignment.job_metadata, uri_references=templating_assignment.referenced_uris())
    if templating_assignment.cogt_run_params.run_mode.is_dry:
        # A worker's activity runs this leaf with no scope open: its run's limits come from its job's metadata.
        with dry_leaf_limits(run_max_declared_item_count=templating_assignment.job_metadata.run_metadata.max_declared_item_count):
            return dry_templating_gen_text(templating_assignment)
    templated_text: str = await render_template(
        template=templating_assignment.template,
        category=templating_assignment.category,
        context=templating_assignment.context,
        templating_style=templating_assignment.templating_style,
    )

    return templated_text
