import typer
from click import Command, Context
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.commands.build_cmd import build_app
from pipelex.cli.commands.init_cmd import init_app
from pipelex.cli.commands.kit_cmd import kit_app
from pipelex.cli.commands.run_cmd import run_cmd
from pipelex.cli.commands.show_cmd import show_app
from pipelex.cli.commands.validate_cmd import validate_app


class PipelexCLI(TyperGroup):
    @override
    def list_commands(self, ctx: Context) -> list[str]:
        return ["init", "kit", "build", "validate", "run", "show"]

    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            typer.echo(f"Unknown command: {cmd_name}")
            typer.echo(ctx.get_help())
            ctx.exit(1)
        return cmd


def main() -> None:
    """Entry point for the pipelex CLI."""
    app()


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexCLI,
)


app.add_typer(init_app, name="init", help="Initialization commands")
app.add_typer(kit_app, name="kit", help="Manage kit assets")
app.add_typer(build_app, name="build", help="Build artifacts like pipeline blueprints")
app.add_typer(validate_app, name="validate", help="Validation and dry-run commands")
app.command(name="run", help="Execute a pipeline")(run_cmd)
app.add_typer(show_app, name="show", help="Show and list commands")
