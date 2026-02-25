import typer

from pipelex.cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.commands.run.pipe_cmd import run_pipe_cmd

run_app = typer.Typer(help="Run a method or pipe", no_args_is_help=True)

run_app.command("method", help="Run an installed method by name")(run_method_cmd)
run_app.command("pipe", help="Run a pipe by code, bundle file (.mthds), or pipeline directory")(run_pipe_cmd)
