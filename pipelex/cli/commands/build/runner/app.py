import typer

from pipelex.cli.commands.build.runner.bundle_cmd import build_runner_bundle_cmd
from pipelex.cli.commands.build.runner.method_cmd import build_runner_method_cmd

build_runner_app = typer.Typer(help="Build Python code to run a pipe", no_args_is_help=True)

build_runner_app.command("bundle", help="Build runner from a bundle file or directory")(build_runner_bundle_cmd)
build_runner_app.command("method", help="Build runner for an installed method")(build_runner_method_cmd)
