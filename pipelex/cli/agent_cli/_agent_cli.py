"""Main entry point for the agent CLI."""

from typing import Annotated

import typer
from click import Command, Context
from mthds.runners.types import RunnerType
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.agent_cli.commands.assemble_cmd import assemble_cmd
from pipelex.cli.agent_cli.commands.concept_cmd import concept_cmd
from pipelex.cli.agent_cli.commands.doctor_cmd import agent_doctor_cmd
from pipelex.cli.agent_cli.commands.fmt_cmd import fmt_cmd
from pipelex.cli.agent_cli.commands.inputs.app import inputs_app
from pipelex.cli.agent_cli.commands.lint_cmd import lint_cmd
from pipelex.cli.agent_cli.commands.models_cmd import agent_models_cmd
from pipelex.cli.agent_cli.commands.pipe_cmd import pipe_cmd
from pipelex.cli.agent_cli.commands.run.app import run_app
from pipelex.cli.agent_cli.commands.validate.app import validate_app
from pipelex.tools.misc.package_utils import get_package_version


class PipelexAgentCLI(TyperGroup):
    """Custom Typer group for pipelex-agent CLI."""

    @override
    def list_commands(self, ctx: Context) -> list[str]:
        """List commands in proper order."""
        return [
            "run",
            "validate",
            "fmt",
            "lint",
            "inputs",
            "concept",
            "pipe",
            "assemble",
            "models",
            "doctor",
        ]

    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        """Get command by name."""
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            from pipelex.cli.agent_cli.commands.agent_output import agent_error  # noqa: PLC0415

            valid_commands = super().list_commands(ctx)
            agent_error(
                f"Unknown command: {cmd_name}",
                "UnknownCommandError",
                valid_commands=valid_commands,
            )
        return cmd


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexAgentCLI,
)


def version_callback(value: bool) -> None:
    """Print version and exit when --version is passed."""
    if value:
        package_version = get_package_version()
        typer.echo(f"pipelex-agent {package_version}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def app_callback(
    ctx: typer.Context,
    version: Annotated[  # noqa: ARG001
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
    log_level: Annotated[
        str,
        typer.Option("--log-level", help="Log verbosity level (debug, verbose, info, warning, error, critical)."),
    ] = "warning",
    runner: Annotated[
        str,
        typer.Option("--runner", help="Runner to use: 'pipelex' (local) or 'api' (remote MTHDS API)."),
    ] = "pipelex",
) -> None:
    """Agent CLI callback - no logo, minimal output."""
    from pipelex.cli.agent_cli.commands.agent_output import agent_error  # noqa: PLC0415
    from pipelex.tools.log.log_levels import LogLevel  # noqa: PLC0415

    ctx.ensure_object(dict)
    try:
        ctx.obj["log_level"] = LogLevel(log_level.upper())
    except ValueError:
        valid_values = ", ".join(level.value.lower() for level in LogLevel)
        agent_error(
            f"Invalid log level '{log_level}'. Valid values: {valid_values}",
            "ArgumentError",
        )

    try:
        ctx.obj["runner"] = RunnerType(runner)
    except ValueError:
        valid_values = ", ".join(runner_type.value for runner_type in RunnerType)
        agent_error(
            f"Invalid runner '{runner}'. Valid values: {valid_values}",
            "ArgumentError",
        )


app.add_typer(run_app, name="run", help="Execute a pipeline and output JSON results")
app.add_typer(validate_app, name="validate", help="Validate a pipe, bundle, or all pipes and output JSON results")
app.command(name="fmt", help="Format a .mthds, .toml, or .plx file in-place")(fmt_cmd)
app.command(name="lint", help="Lint a .mthds, .toml, or .plx file")(lint_cmd)
app.add_typer(inputs_app, name="inputs", help="Generate example input JSON for a pipe")
app.command(name="concept", help="Structure a concept from JSON spec and output TOML")(concept_cmd)
app.command(name="pipe", help="Structure a pipe from JSON spec and output TOML")(pipe_cmd)
app.command(name="assemble", help="Assemble a complete .mthds bundle from TOML parts")(assemble_cmd)
app.command(name="models", help="List available model presets, aliases, and talent mappings")(agent_models_cmd)
app.command(name="doctor", help="Check Pipelex configuration health and auto-fix issues")(agent_doctor_cmd)
