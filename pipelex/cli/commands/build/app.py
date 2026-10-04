import typer

from pipelex.cli.commands.build.inputs.app import build_inputs_app
from pipelex.cli.commands.build.output.app import build_output_app
from pipelex.cli.commands.build.structures_cmd import build_structures_command

build_app = typer.Typer(help="Generate example inputs, example outputs and structure classes for a pipe", no_args_is_help=True)

# inputs and output are Typer groups with bundle/method/pipe subcommands
build_app.add_typer(build_inputs_app, name="inputs", help="Generate example input JSON for a pipe")
build_app.add_typer(build_output_app, name="output", help="Generate example output representation for a pipe (JSON, Python, or JSON Schema)")
build_app.command("structures", help="Generate Python structure files from concept definitions in MTHDS files")(build_structures_command)
