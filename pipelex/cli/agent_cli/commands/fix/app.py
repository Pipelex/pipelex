"""Agent CLI fix subcommand group."""

import typer

from pipelex.cli.agent_cli.commands.fix.bundle_cmd import fix_bundle_cmd
from pipelex.cli.agent_cli.commands.fix.function_names_cmd import fix_function_names_cmd

fix_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

fix_app.command(name="bundle", help="Fix a bundle file (.mthds) or a method's whole folder")(fix_bundle_cmd)
fix_app.command(name="function-names", help="Rewrite a method's flat PipeFunc function names as import paths")(fix_function_names_cmd)
