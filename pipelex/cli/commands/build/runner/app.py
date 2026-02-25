import typer

from pipelex.cli.commands.build.runner.method_cmd import build_runner_method_cmd
from pipelex.cli.commands.build.runner.pipe_cmd import build_runner_pipe_cmd

build_runner_app = typer.Typer(help="Build Python code to run a pipe", no_args_is_help=True)

build_runner_app.command("method", help="Build runner for an installed method")(build_runner_method_cmd)
build_runner_app.command("pipe", help="Build runner for a pipe from a bundle file")(build_runner_pipe_cmd)
