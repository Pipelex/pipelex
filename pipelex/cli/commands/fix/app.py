import typer

from pipelex.cli.commands.fix.bundle_cmd import fix_bundle_cmd
from pipelex.cli.commands.fix.function_names_cmd import fix_function_names_cmd

fix_app = typer.Typer(
    help="Apply deterministic safe fixes to a bundle and re-validate until valid, or migrate a method's function names",
    no_args_is_help=True,
)

fix_app.command("bundle", help="Fix a bundle file (.mthds) or pipeline directory in place")(fix_bundle_cmd)
fix_app.command("function-names", help="Rewrite a method's flat PipeFunc function names as import paths, without booting")(fix_function_names_cmd)
