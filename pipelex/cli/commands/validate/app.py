import typer

from pipelex.cli.commands.validate.bundle_cmd import validate_bundle_cmd
from pipelex.cli.commands.validate.method_cmd import validate_method_cmd
from pipelex.cli.commands.validate.pipe_cmd import validate_pipe_cmd

validate_app = typer.Typer(help="Validate a method, pipe, or bundle", no_args_is_help=True)

validate_app.command("method", help="Validate an installed method by name")(validate_method_cmd)
validate_app.command("pipe", help="Validate a pipe by code, or all pipes")(validate_pipe_cmd)
validate_app.command("bundle", help="Validate a bundle file (.mthds) or pipeline directory")(validate_bundle_cmd)
