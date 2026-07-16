"""Agent CLI fix subcommand group."""

import typer

from pipelex.cli.agent_cli.commands.fix.bundle_cmd import fix_bundle_cmd

fix_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
)

fix_app.command(name="bundle", help="Fix a bundle file (.mthds) or pipeline directory")(fix_bundle_cmd)
