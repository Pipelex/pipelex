from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.builder.conventions import DEFAULT_INPUTS_FILE_NAME, DEFAULT_INPUTS_TOML_FILE_NAME
from pipelex.cli.commands.build.inputs._inputs_core import execute_generate_inputs
from pipelex.cli.method_resolver import resolve_method_target
from pipelex.core.pipes.rendering.input_renderer import InputsTemplateFormat


def build_inputs_method_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Name of the installed method"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code (overrides method's main_pipe)"),
    ] = None,
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
        typer.Option("--output", "-o", help="Path to save the generated inputs file"),
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
    """Generate an example inputs template for an installed method.

    Examples:
        pipelex build inputs method my-method
        pipelex build inputs method my-method --pipe custom_pipe
        pipelex build inputs method my-method --output custom_inputs.json
        pipelex build inputs method my-method --format toml
        pipelex build inputs method my-method --explicit
    """
    pipe_code, method_library_dirs, _ = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
        library_dirs=library_dir,
    )

    effective_library_dir = list(method_library_dirs)
    if library_dir:
        effective_library_dir.extend(library_dir)

    # Default output to a results/ folder inside the method's directory
    if output_path:
        output_path_path = Path(output_path)
    else:
        default_file_name: str
        match template_format:
            case InputsTemplateFormat.JSON:
                default_file_name = DEFAULT_INPUTS_FILE_NAME
            case InputsTemplateFormat.TOML:
                default_file_name = DEFAULT_INPUTS_TOML_FILE_NAME
        output_path_path = Path(method_library_dirs[0]) / "results" / default_file_name

    execute_generate_inputs(
        pipe_code=pipe_code,
        bundle_path=None,
        output_path=output_path_path,
        library_dir=effective_library_dir,
        template_format=template_format,
        explicit=explicit,
    )
