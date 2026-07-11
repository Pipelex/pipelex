import typer

from pipelex.cli.commands.codegen.check_cmd import codegen_check_cmd
from pipelex.cli.commands.codegen.inputs_cmd import codegen_inputs_cmd
from pipelex.cli.commands.codegen.types_cmd import codegen_types_cmd

codegen_app = typer.Typer(
    help="Project the normalized library crate into typed, runnable artifacts (two axes: kind + --target)",
    no_args_is_help=True,
)

codegen_app.command("types", help="Project the crate's concept set into typed artifacts (--target)")(codegen_types_cmd)
codegen_app.command("inputs", help="Project a runnable inputs template for a pipe (--pipe, defaults to main_pipe)")(codegen_inputs_cmd)
codegen_app.command("check", help="Verify generated artifacts are current — offline, no engine or network")(codegen_check_cmd)
