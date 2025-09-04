from __future__ import annotations

from typing import Optional

from pipelex import pretty_print
from pipelex.create.helpers import get_support_file
from pipelex.libraries.pipelines.builder.builder import PipelexBundleBlueprint
from pipelex.pipeline.execute import execute_pipeline


async def do_build_blueprint(
    brief: str,
    output_path: Optional[str],
) -> None:
    pipe_output = await execute_pipeline(
        pipe_code="build_drafts_from_brief",
        input_memory={
            "brief": brief,
            "concept_rules": get_support_file(subpath="create/structures.md"),
        },
    )
    pretty_print(pipe_output, title="Pipe Output")
    blueprint = pipe_output.working_memory.main_stuff_as(content_type=PipelexBundleBlueprint)
    pretty_print(blueprint, title="Pipelex Bundle Blueprint")
