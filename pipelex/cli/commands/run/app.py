import typer

from pipelex.cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.commands.run.pipe_cmd import run_pipe_cmd

run_app = typer.Typer(help="Run a method, pipe, or bundle", no_args_is_help=True)

run_app.command("method", help="Run an installed method by name")(run_method_cmd)
run_app.command("pipe", help="Run a pipe by code")(run_pipe_cmd)
run_app.command("bundle", help="Run a pipeline from a bundle file (.mthds) or directory")(run_bundle_cmd)
