import typer

from pipelex.cli.commands.build.output.bundle_cmd import build_output_bundle_cmd
from pipelex.cli.commands.build.output.method_cmd import build_output_method_cmd
from pipelex.cli.commands.build.output.pipe_cmd import build_output_pipe_cmd

build_output_app = typer.Typer(help="Generate example output representation for a pipe", no_args_is_help=True)

build_output_app.command("bundle", help="Generate output from a bundle file or directory")(build_output_bundle_cmd)
build_output_app.command("method", help="Generate output for an installed method")(build_output_method_cmd)
build_output_app.command("pipe", help="Generate output for a pipe by code")(build_output_pipe_cmd)
