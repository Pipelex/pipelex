import typer

from pipelex.cli.commands.build.output.method_cmd import build_output_method_cmd
from pipelex.cli.commands.build.output.pipe_cmd import build_output_pipe_cmd

build_output_app = typer.Typer(help="Generate example output representation for a pipe", no_args_is_help=True)

build_output_app.command("method", help="Generate output for an installed method")(build_output_method_cmd)
build_output_app.command("pipe", help="Generate output for a pipe by code or bundle")(build_output_pipe_cmd)
