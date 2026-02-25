import typer

from pipelex.cli.commands.build.inputs.method_cmd import build_inputs_method_cmd
from pipelex.cli.commands.build.inputs.pipe_cmd import build_inputs_pipe_cmd

build_inputs_app = typer.Typer(help="Generate example input JSON for a pipe", no_args_is_help=True)

build_inputs_app.command("method", help="Generate inputs for an installed method")(build_inputs_method_cmd)
build_inputs_app.command("pipe", help="Generate inputs for a pipe by code or bundle")(build_inputs_pipe_cmd)
