"""Main entry point for the agent CLI."""

from typing import Annotated

import typer
from click import Command, Context
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.agent_cli.commands.assemble_cmd import assemble_cmd
from pipelex.cli.agent_cli.commands.build_cmd import build_cmd
from pipelex.cli.agent_cli.commands.concept_cmd import concept_cmd
from pipelex.cli.agent_cli.commands.doctor_cmd import agent_doctor_cmd
from pipelex.cli.agent_cli.commands.fmt_cmd import fmt_cmd
from pipelex.cli.agent_cli.commands.graph_cmd import graph_cmd
from pipelex.cli.agent_cli.commands.inputs_cmd import inputs_cmd
from pipelex.cli.agent_cli.commands.lint_cmd import lint_cmd
from pipelex.cli.agent_cli.commands.models_cmd import agent_models_cmd
from pipelex.cli.agent_cli.commands.mthds_add_cmd import mthds_add_cmd
from pipelex.cli.agent_cli.commands.mthds_init_cmd import mthds_init_cmd
from pipelex.cli.agent_cli.commands.mthds_install_cmd import mthds_install_cmd
from pipelex.cli.agent_cli.commands.mthds_list_cmd import mthds_list_cmd
from pipelex.cli.agent_cli.commands.mthds_lock_cmd import mthds_lock_cmd
from pipelex.cli.agent_cli.commands.mthds_publish_cmd import mthds_publish_cmd
from pipelex.cli.agent_cli.commands.mthds_update_cmd import mthds_update_cmd
from pipelex.cli.agent_cli.commands.mthds_validate_cmd import mthds_validate_cmd
from pipelex.cli.agent_cli.commands.pipe_cmd import pipe_cmd
from pipelex.cli.agent_cli.commands.run_cmd import run_cmd
from pipelex.cli.agent_cli.commands.validate_cmd import validate_cmd
from pipelex.tools.misc.package_utils import get_package_version


class PipelexAgentCLI(TyperGroup):
    """Custom Typer group for pipelex-agent CLI."""

    @override
    def list_commands(self, ctx: Context) -> list[str]:
        """List commands in proper order."""
        return [
            "build",
            "run",
            "validate",
            "fmt",
            "lint",
            "inputs",
            "concept",
            "pipe",
            "assemble",
            "graph",
            "models",
            "doctor",
            "mthds-init",
            "mthds-list",
            "mthds-add",
            "mthds-lock",
            "mthds-install",
            "mthds-update",
            "mthds-publish",
            "mthds-validate",
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


app.command(name="build", help="Build a pipeline from a prompt")(build_cmd)
app.command(name="run", help="Execute a pipeline and output JSON results")(run_cmd)
app.command(name="validate", help="Validate a pipe, bundle, or all pipes and output JSON results")(validate_cmd)
app.command(name="fmt", help="Format a .mthds, .toml, or .plx file in-place")(fmt_cmd)
app.command(name="lint", help="Lint a .mthds, .toml, or .plx file")(lint_cmd)
app.command(name="inputs", help="Generate example input JSON for a pipe")(inputs_cmd)
app.command(name="concept", help="Structure a concept from JSON spec and output TOML")(concept_cmd)
app.command(name="pipe", help="Structure a pipe from JSON spec and output TOML")(pipe_cmd)
app.command(name="assemble", help="Assemble a complete .mthds bundle from TOML parts")(assemble_cmd)
app.command(name="graph", help="Generate graph visualization from a .mthds bundle")(graph_cmd)
app.command(name="models", help="List available model presets, aliases, and talent mappings")(agent_models_cmd)
app.command(name="doctor", help="Check Pipelex configuration health and auto-fix issues")(agent_doctor_cmd)
app.command(name="mthds-init", help="Initialize a METHODS.toml package manifest")(mthds_init_cmd)
app.command(name="mthds-list", help="Display the package manifest (METHODS.toml)")(mthds_list_cmd)
app.command(name="mthds-add", help="Add a dependency to METHODS.toml")(mthds_add_cmd)
app.command(name="mthds-lock", help="Resolve dependencies and generate methods.lock")(mthds_lock_cmd)
app.command(name="mthds-install", help="Install dependencies from methods.lock")(mthds_install_cmd)
app.command(name="mthds-update", help="Re-resolve dependencies and update methods.lock")(mthds_update_cmd)
app.command(name="mthds-publish", help="Publish package for distribution")(mthds_publish_cmd)
app.command(name="mthds-validate", help="Validate METHODS.toml via runner")(mthds_validate_cmd)
