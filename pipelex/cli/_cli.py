from typing import Optional

import typer
from click import Command, Context
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.commands import init_app, migrate_app, show_app, validate_app
from pipelex.cli.commands.build_cmd import build_app


class PipelexCLI(TyperGroup):
    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Optional[Command]:
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
app.add_typer(validate_app, name="validate", help="Validation and dry-run commands")
app.add_typer(show_app, name="show", help="Show and list commands")
app.add_typer(migrate_app, name="migrate", help="Migration commands")
app.add_typer(build_app, name="build", help="Build artifacts like pipeline blueprints")
