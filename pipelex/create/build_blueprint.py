from __future__ import annotations

from typing import Optional

from pipelex import pretty_print
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.libraries.pipelines.builder.builder import PipelexBundleBlueprint
from pipelex.pipeline.execute import execute_pipeline


async def do_build_blueprint(
    brief: str,
    output_path: Optional[str],
) -> None:
    pipe_output = await execute_pipeline(
        pipe_code="build_drafts_from_brief",
        input_memory={"brief": brief},
    )
    pretty_print(pipe_output, title="Pipe Output")
    blueprint = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_blueprint", content_type=PipelexBundleBlueprint)
    pretty_print(blueprint, title="Pipelex Bundle Blueprint")
    plx_content = PipelexInterpreter.make_plx_content(blueprint=blueprint.to_core_blueprint())
    pretty_print(plx_content, title="PLX Content")

    # Here, save the plx_content to a file
    if output_path:
        with open(output_path, "w") as f:
            f.write(plx_content)
