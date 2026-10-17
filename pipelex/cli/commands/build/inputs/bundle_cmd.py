from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from pipelex.cli.commands.build.inputs._inputs_core import execute_generate_inputs
from pipelex.cli.commands.bundle_path_resolver import resolve_build_bundle_target
from pipelex.pipe_machinery.rendering.input_renderer import InputsTemplateFormat

_NOT_A_BUNDLE_HINT = (
    "  To generate inputs for a pipe by code, use: pipelex build inputs pipe <code>\n"
    "  To use a bundle, pass a .mthds file or directory: pipelex build inputs bundle <path>"
)


def build_inputs_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file, or a method's folder, which starts at its entry pipe unless --pipe names one"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code (overrides bundle's main_pipe)"),
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
        typer.Option("--output", "-o", help="Path to save the generated inputs file (defaults to bundle's directory)"),
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
    """Generate an example inputs template from a bundle file or pipeline directory.

    Examples:
        pipelex build inputs bundle my_bundle.mthds
        pipelex build inputs bundle pipeline_01/
        pipelex build inputs bundle my_bundle.mthds --pipe my_pipe
        pipelex build inputs bundle pipeline_01/ --output custom_inputs.json
        pipelex build inputs bundle pipeline_01/ --format toml
        pipelex build inputs bundle pipeline_01/ --explicit
    """
    output_path_path = Path(output_path) if output_path else None
    # A folder is read as its method tree and acts on the pipe a run of it starts at, as `run bundle` reads it.
    target = resolve_build_bundle_target(
        path=path, library_dir=library_dir, pipe_override=pipe, command="build inputs", not_a_bundle_hint=_NOT_A_BUNDLE_HINT
    )

    execute_generate_inputs(
        pipe_code=target.pipe_code,
        bundle_path=target.bundle_path,
        output_path=output_path_path,
        default_output_dir=target.default_output_dir,
        library_dir=target.library_dir,
        template_format=template_format,
        explicit=explicit,
    )
