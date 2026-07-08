import typer

from pipelex.cli.commands.fix.bundle_cmd import fix_bundle_cmd

fix_app = typer.Typer(
    help="Apply deterministic safe fixes to a bundle and re-validate until valid",
    no_args_is_help=True,
)

fix_app.command("bundle", help="Fix a bundle file (.mthds) or pipeline directory in place")(fix_bundle_cmd)
