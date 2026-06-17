"""Main entry point for the agent CLI."""

from typing import Annotated

import typer
from click import Command, Context
from mthds.runners.types import RunnerType
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.agent_cli.commands.accept_gateway_terms_cmd import agent_accept_gateway_terms_cmd
from pipelex.cli.agent_cli.commands.agent_cli_factory import silence_logging_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, agent_error, set_agent_cli_error_format
from pipelex.cli.agent_cli.commands.check_model_cmd import agent_check_model_cmd
from pipelex.cli.agent_cli.commands.concept_cmd import concept_cmd
from pipelex.cli.agent_cli.commands.doctor_cmd import agent_doctor_cmd
from pipelex.cli.agent_cli.commands.fmt_cmd import fmt_cmd
from pipelex.cli.agent_cli.commands.init_cmd import agent_init_cmd
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
            "init",
            "run",
            "validate",
            "fmt",
            "lint",
            "inputs",
            "concept",
            "pipe",
            "models",
            "check-model",
            "accept-gateway-terms",
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
                error_type="UnknownCommandError",
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
    runner: Annotated[
        str,
        typer.Option("--runner", help="Runner to use: 'pipelex' (local) or 'api' (remote MTHDS API)."),
    ] = "pipelex",
) -> None:
    """Agent CLI callback - no logo, minimal output.

    Note: there is no ``--log-level`` flag. ``pipelex-agent`` is machine-consumed:
    stdout is reserved for the success envelope and stderr for the error envelope.
    Free-floating logs would corrupt those channels, so Python's logging system is
    cut off process-wide via ``silence_logging_for_agent_cli`` as the very first
    action in this callback — covering every subcommand invocation (including ones
    like ``init`` and ``accept-gateway-terms`` that bypass
    ``make_pipelex_for_agent_cli``). The ``--version`` eager option short-circuits
    before this body runs, but its callback only does ``typer.echo`` + ``Exit`` and
    touches no log path. For verbose debugging, use the human ``pipelex`` CLI instead.
    """
    # Process-global logging cutoff, armed BEFORE any command body runs and BEFORE any
    # error-format / runner-validation code below can route through ``log.*``. This is the
    # primary armor for the stdout/stderr discipline; the per-call invocations inside
    # ``make_pipelex_for_agent_cli`` and ``agent_doctor_cmd`` are kept as defense-in-depth
    # for direct library callers that bypass this Typer entry point.
    silence_logging_for_agent_cli()
    # Reset the error-format ContextVar at the single choke point every command passes through, so
    # a markdown command cannot leak markdown into a later JSON-only command in the same process.
    # --format / --error-format commands override this afterwards; JSON-only commands keep the JSON default.
    set_agent_cli_error_format(CliOutputFormat.JSON)

    ctx.ensure_object(dict)
    try:
        ctx.obj["runner"] = RunnerType(runner)
    except ValueError:
        valid_values = ", ".join(runner_type.value for runner_type in RunnerType)
        agent_error(
            f"Invalid runner '{runner}'. Valid values: {valid_values}",
            error_type="ArgumentError",
        )


app.command(name="init", help="Initialize Pipelex configuration (non-interactive)")(agent_init_cmd)
app.add_typer(run_app, name="run", help="Execute a pipeline and output JSON results")
app.add_typer(validate_app, name="validate", help="Validate a pipe, bundle, or all pipes and output JSON results")
app.command(name="fmt", help="Format a .mthds, .toml, or .plx file in-place")(fmt_cmd)
app.command(name="lint", help="Lint a .mthds, .toml, or .plx file")(lint_cmd)
app.add_typer(inputs_app, name="inputs", help="Generate example input JSON for a pipe")
app.command(name="concept", help="Structure a concept from JSON spec and output TOML")(concept_cmd)
app.command(name="pipe", help="Structure a pipe from JSON spec and output TOML")(pipe_cmd)
app.command(name="models", help="List available model presets, aliases, and waterfalls")(agent_models_cmd)
app.command(name="check-model", help="Check if a model reference is valid and suggest alternatives")(agent_check_model_cmd)
app.command(name="accept-gateway-terms", help="Accept Pipelex Gateway terms and mark inference setup complete")(agent_accept_gateway_terms_cmd)
app.command(name="doctor", help="Check Pipelex configuration health and auto-fix issues")(agent_doctor_cmd)
