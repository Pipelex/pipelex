from __future__ import annotations

from typing import Optional

from pipelex import log, pretty_print
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.create.helpers import get_support_file
from pipelex.libraries.pipelines.meta.pipeline_draft import PipelexBundleBlueprint
from pipelex.pipeline.execute import execute_pipeline
from pipelex.tools.misc.file_utils import save_text_to_path
from pipelex.tools.misc.json_utils import save_as_json_to_path


async def do_build_blueprint(
    domain: str,
    pipeline_name: str,
    requirements: str,
    output_path: Optional[str],
    validate: bool,
) -> None:
    pipe_output = await execute_pipeline(
        pipe_code="build_blueprint",
        input_memory={
            "domain": domain,
            "pipeline_name": pipeline_name,
            "requirements": requirements,
            "draft_pipeline_rules": get_support_file(subpath="create/draft_pipelines.md"),
            "build_pipeline_rules": get_support_file(subpath="create/build_pipelines.md"),
            "create_structured_output_rules": get_support_file(subpath="create/structures.md"),
        },
    )
    pretty_print(pipe_output, title="Pipe Output")

    blueprint = pipe_output.main_stuff_as(content_type=PipelexBundleBlueprint)
    pipeline_draft = pipe_output.working_memory.get_stuff_as_str(name="pipeline_draft")

    # Save or display result
    output_path_base = output_path or "pipelex/libraries/pipelines/temp/gen_blueprint"
    draft_path = f"{output_path_base}_draft.md"
    save_text_to_path(text=pipeline_draft, path=draft_path, create_directory=True)
    rough_plx_path = f"{output_path_base}_rough.plx"
    save_text_to_path(text=PipelexInterpreter.make_plx_content(blueprint=blueprint), path=rough_plx_path)
    rough_json_path = f"{output_path_base}_rough.json"
    save_as_json_to_path(object_to_save=blueprint, path=rough_json_path)
    log.info(f"✅ Rough blueprint saved to '{output_path_base}'")
