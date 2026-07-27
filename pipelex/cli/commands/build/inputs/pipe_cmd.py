from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.build.inputs._inputs_core import execute_generate_inputs
from pipelex.core.pipes.rendering.input_renderer import InputsTemplateFormat


def build_inputs_pipe_cmd(
    pipe_code: Annotated[
        str,
        typer.Argument(help="Pipe code (e.g. my_domain.my_pipe)"),
    ],
    library_dir: Annotated[
        list[str] | None,
        typer.Option(
            "--library-dir",
            "-L",
            help="Directory to search for pipe definitions (.mthds files). Can be specified multiple times.",
        ),
    ] = None,
    output_path: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save the generated inputs file (defaults to 'results/')"),
    ] = None,
    template_format: Annotated[
        InputsTemplateFormat,
        typer.Option("--format", help="Format of the generated inputs template (json or toml)"),
    ] = InputsTemplateFormat.JSON,
    explicit: Annotated[
        bool,
        typer.Option("--explicit", help="Emit the ceremonial {concept, content} envelope form instead of the light values"),
    ] = False,
) -> None:
    """Generate an example inputs template for a pipe by code.

    Examples:
        pipelex build inputs pipe my_domain.my_pipe
        pipelex build inputs pipe my_pipe -L ./my_library/
        pipelex build inputs pipe my_pipe --output custom_inputs.json
        pipelex build inputs pipe my_pipe --format toml
        pipelex build inputs pipe my_pipe --explicit
    """
    output_path_path = Path(output_path) if output_path else None

    execute_generate_inputs(
        pipe_code=pipe_code,
        bundle_path=None,
        output_path=output_path_path,
        library_dir=library_dir,
        template_format=template_format,
        explicit=explicit,
    )
