"""Main entry point for the agent CLI."""

import sys
from collections.abc import Sequence
from typing import Annotated, Any

import typer
from click import Command, Context
from mthds.protocol.problem.registry import CoreCode
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.agent_cli.commands.agent_cli_factory import silence_logging_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, start_agent_cli_error_format
from pipelex.cli.agent_cli.commands.check_model_cmd import agent_check_model_cmd
from pipelex.cli.agent_cli.commands.codegen.app import codegen_app
from pipelex.cli.agent_cli.commands.doctor_cmd import agent_doctor_cmd
from pipelex.cli.agent_cli.commands.fix.app import fix_app
from pipelex.cli.agent_cli.commands.fmt_cmd import fmt_cmd
from pipelex.cli.agent_cli.commands.init_cmd import agent_init_cmd
from pipelex.cli.agent_cli.commands.inputs.app import inputs_app
from pipelex.cli.agent_cli.commands.lint_cmd import lint_cmd
from pipelex.cli.agent_cli.commands.migrate_cmd import agent_migrate_cmd
from pipelex.cli.agent_cli.commands.models_cmd import agent_models_cmd
from pipelex.cli.agent_cli.commands.run.app import run_app
from pipelex.cli.agent_cli.commands.validate.app import validate_app
from pipelex.cli.usage_stats_cli import run_with_usage_stats
from pipelex.cli.version_report import version_report_lines
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsSurface


class PipelexAgentCLI(TyperGroup):
    """Custom Typer group for pipelex-agent CLI."""

    @override
    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        """Run the command between the start and the end of its usage statistics (`pipelex.cli.usage_stats_cli`)."""
        return run_with_usage_stats(
            root=self,
            args=list(args) if args is not None else sys.argv[1:],
            surface=UsageStatsSurface.PIPELEX_AGENT,
            strip_flags=frozenset(),
            invoke=lambda: super(PipelexAgentCLI, self).main(
                args=args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=standalone_mode,
                windows_expand_args=windows_expand_args,
                **extra,
            ),
        )

    @override
    def list_commands(self, ctx: Context) -> list[str]:
        """List commands in proper order."""
        return [
            "init",
            "run",
            "validate",
            "fix",
            "fmt",
            "lint",
            "inputs",
            "codegen",
            "models",
            "check-model",
            "migrate",
            "doctor",
        ]

    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        """Get command by name."""
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            from pipelex.cli.agent_cli.commands.agent_output import agent_error  # ruff: ignore[import-outside-top-level]

            # Click resolves the command before it runs the app callback, so the program's own --error-format, already
            # parsed, is read here.
            root_error_format = ctx.params.get("error_format")
            start_agent_cli_error_format(root_error_format=CliOutputFormat(root_error_format) if root_error_format else None)
            valid_commands = super().list_commands(ctx)
            agent_error(
                f"Unknown command: {cmd_name}",
                code=CoreCode.CLIENT_ARGUMENT_INVALID,
                params={"argument": cmd_name, "reason": "not a command of pipelex-agent"},
                valid_commands=valid_commands,
            )
        return cmd


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexAgentCLI,
)


def version_callback(value: bool) -> None:  # kw-only: ignore — click invokes Option callbacks positionally
    """Print the version handshake and exit when --version is passed."""
    if value:
        for line in version_report_lines(program_name="pipelex-agent"):
            typer.echo(line)
        raise typer.Exit


#: What `pipelex-agent --help` says of the program. Given explicitly, since Typer would otherwise print the callback's
#: docstring, which is written for this module's maintainers.
AGENT_CLI_HELP = (
    "The machine-oriented Pipelex CLI, for AI agents, IDE extensions and automation: no prompts and no logs, results on stdout "
    "(Markdown or JSON for most commands), and errors as a problem document on stderr (Markdown or JSON with --error-format)."
)


@app.callback(invoke_without_command=True, help=AGENT_CLI_HELP)
def app_callback(
    version: Annotated[  # ruff: ignore[unused-function-argument]
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
    error_format: Annotated[
        CliOutputFormat | None,
        typer.Option(
            "--error-format",
            help=(
                "Error output format for every command: markdown or json. "
                "A command's own --error-format wins; without either, a command's --format decides."
            ),
        ),
    ] = None,
) -> None:
    """Agent CLI callback - no logo, minimal output.

    Note: there is no ``--log-level`` flag. ``pipelex-agent`` is machine-consumed:
    stdout is reserved for the success envelope and stderr for the problem a failure reports.
    Free-floating logs would corrupt those channels, so Python's logging system is
    cut off process-wide via ``silence_logging_for_agent_cli`` as the very first
    action in this callback — covering every subcommand invocation (including ones
    like ``init`` that bypass
    ``make_pipelex_for_agent_cli``). The ``--version`` eager option short-circuits
    before this body runs, but its callback only does ``typer.echo`` + ``Exit`` and
    touches no log path. For verbose debugging, use the human ``pipelex`` CLI instead.
    """
    # Process-global logging cutoff, armed BEFORE any command body runs and BEFORE any
    # error-format code below can route through ``log.*``. This is the
    # primary armor for the stdout/stderr discipline; the per-call invocations inside
    # ``make_pipelex_for_agent_cli`` and ``agent_doctor_cmd`` are kept as defense-in-depth
    # for direct library callers that bypass this Typer entry point.
    silence_logging_for_agent_cli()
    # Start the error-format ContextVar at the single choke point every command passes through, from the program's own
    # --error-format, so a markdown command cannot leak markdown into a later JSON-only command in the same process.
    # A command's own --error-format, then this one, then its --format settle it afterwards; commands without either
    # keep this one, else JSON.
    start_agent_cli_error_format(root_error_format=error_format)


app.command(name="init", help="Initialize Pipelex configuration (non-interactive)")(agent_init_cmd)
app.add_typer(run_app, name="run", help="Execute a pipeline and output JSON results")
app.add_typer(validate_app, name="validate", help="Validate a pipe, bundle, or all pipes and output JSON results")
app.add_typer(fix_app, name="fix", help="Fix a bundle file or a method's folder in place, or migrate a method's function names")
app.command(name="fmt", help="Format a .mthds, .toml, or .plx file in-place")(fmt_cmd)
app.command(name="lint", help="Lint a .mthds, .toml, or .plx file")(lint_cmd)
app.add_typer(inputs_app, name="inputs", help="Generate example input JSON for a pipe")
app.add_typer(codegen_app, name="codegen", help="Project the crate into typed artifacts (types) and check drift offline (check)")
app.command(name="models", help="List available model presets, aliases, and waterfalls")(agent_models_cmd)
app.command(name="check-model", help="Check if a model reference is valid and suggest alternatives")(agent_check_model_cmd)
app.command(name="migrate", help="Migrate this machine's Pipelex configuration files to the current schema")(agent_migrate_cmd)
app.command(name="doctor", help="Check Pipelex configuration health and auto-fix issues")(agent_doctor_cmd)
