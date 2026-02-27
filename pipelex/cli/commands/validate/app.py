import click
import typer
import typer.core
from typing_extensions import override

from pipelex.cli.commands.validate.bundle_cmd import validate_bundle_cmd
from pipelex.cli.commands.validate.method_cmd import validate_method_cmd
from pipelex.cli.commands.validate.pipe_cmd import validate_pipe_cmd


class _ValidateGroup(typer.core.TyperGroup):
    """Custom TyperGroup that defaults to the 'pipe' subcommand.

    When no recognized subcommand is given but there are arguments (like --all
    or a pipe code), prepends 'pipe' so that:
        pipelex validate --all        → pipelex validate pipe --all
        pipelex validate my_pipe      → pipelex validate pipe my_pipe
    """

    @override
    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not args:
            return super().parse_args(ctx, args)

        # Don't intercept --help
        if "--help" in args or "-h" in args:
            return super().parse_args(ctx, args)

        # Find the first non-option argument
        first_positional: str | None = None
        for arg in args:
            if not arg.startswith("-"):
                first_positional = arg
                break

        # If no positional arg (only flags like --all), or the first positional
        # is not a known subcommand, default to 'pipe'
        if first_positional is None or first_positional not in self.commands:
            args = ["pipe", *args]

        return super().parse_args(ctx, args)


validate_app = typer.Typer(
    help="Validate a method, pipe, or bundle",
    cls=_ValidateGroup,
    no_args_is_help=True,
)

validate_app.command("method", help="Validate an installed method by name")(validate_method_cmd)
validate_app.command("pipe", help="Validate a pipe by code, or all pipes")(validate_pipe_cmd)
validate_app.command("bundle", help="Validate a bundle file (.mthds) or pipeline directory")(validate_bundle_cmd)
