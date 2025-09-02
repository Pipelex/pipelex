from __future__ import annotations

from typing import Optional

import typer

from pipelex import pretty_print
from pipelex.create.helpers import get_support_file
from pipelex.libraries.pipelines.meta.pipeline_draft import PipelineDraft
from pipelex.pipeline.execute import execute_pipeline
from pipelex.tools.misc.file_utils import save_text_to_path
from pipelex.tools.misc.toml_utils import dict_to_toml, save_toml_to_path


async def do_draft_pipeline_text(
    domain: str,
    pipeline_name: str,
    requirements: str,
    output_path: Optional[str],
) -> None:
    pipe_output = await execute_pipeline(
        pipe_code="draft_pipeline_text",
        input_memory={
            "domain": domain,
            "pipeline_name": pipeline_name,
            "requirements": requirements,
            "rules": get_support_file(subpath="create/draft_pipelines.md"),
        },
    )
    draft_text = pipe_output.main_stuff_as_str
    pretty_print(draft_text, title="Pipeline Draft Text")

    # Save or display result
    output_path = output_path or "pipelex/libraries/pipelines/temp/pipeline_draft.md"
    save_text_to_path(text=draft_text, path=output_path)
    typer.echo(f"✅ Pipeline draft text saved to '{output_path}'")


async def do_draft_pipeline(
    pipeline_name: str,
    requirements: str,
    output_path: Optional[str],
) -> None:
    pipe_output = await execute_pipeline(
        pipe_code="draft_pipeline",
        input_memory={
            "pipeline_name": pipeline_name,
            "requirements": requirements,
            "draft_pipeline_rules": get_support_file(subpath="create/draft_pipelines.md"),
        },
    )
    draft = pipe_output.main_stuff_as(content_type=PipelineDraft)
    pretty_print(draft, title="Pipeline Draft")
    draft_dict = draft.smart_dump()
    pretty_print(dict_to_toml(data=draft_dict), title="Pipeline Draft (PLX)")

    # Save or display result
    output_path = output_path or "pipelex/libraries/pipelines/temp/generated_blueprint.plx"
    save_toml_to_path(data=draft_dict, path=output_path)
    typer.echo(f"✅ Blueprint saved to '{output_path}'")
