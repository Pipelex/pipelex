"""Main entry point for the internal development CLI."""

import sys
from pathlib import Path
from typing import Annotated

import typer
from click import Command, Context
from rich.traceback import Traceback
from typer.core import TyperGroup
from typing_extensions import override

from pipelex.cli.dev_cli.commands.check_config_sync_cmd import LeadingConfig, check_config_sync_cmd
from pipelex.cli.dev_cli.commands.check_gateway_models_cmd import check_gateway_models_cmd
from pipelex.cli.dev_cli.commands.check_mthds_schema_cmd import check_mthds_schema_cmd
from pipelex.cli.dev_cli.commands.check_rules_sync_cmd import check_rules_sync_cmd
from pipelex.cli.dev_cli.commands.check_urls_cmd import DEFAULT_TIMEOUT, check_urls_cmd
from pipelex.cli.dev_cli.commands.generate_mthds_schema_cmd import generate_mthds_schema_cmd
from pipelex.cli.dev_cli.commands.kit_cmd import kit_app
from pipelex.cli.dev_cli.commands.preprocess_test_models_cmd import preprocess_test_models_cmd
from pipelex.cli.dev_cli.commands.sync_main_config_cmd import SyncTarget, sync_main_config_cmd
from pipelex.cli.dev_cli.commands.update_gateway_models_cmd import update_gateway_models_cmd
from pipelex.hub import get_console
from pipelex.tools.misc.package_utils import get_package_version


class PipelexDevCLI(TyperGroup):
    """Custom Typer group for pipelex-dev CLI."""

    @override
    def list_commands(self, ctx: Context) -> list[str]:
        """List commands in proper order."""
        return [
            "check-config-sync",
            "check-gateway-models",
            "check-mthds-schema",
            "check-rules",
            "check-urls",
            "generate-mthds-schema",
            "kit",
            "preprocess-test-models",
            "sync-main-config",
            "update-gateway-models",
        ]

    @override
    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        """Get command by name."""
        cmd = super().get_command(ctx, cmd_name)
        if cmd is None:
            typer.echo(f"Unknown command: {cmd_name}")
            typer.echo(ctx.get_help())
            ctx.exit(1)
        return cmd


def main() -> None:
    """Entry point for the pipelex-dev CLI."""
    app()


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PipelexDevCLI,
)

app.add_typer(kit_app, name="kit", help="Manage agent rules for the Pipelex repository")


@app.callback(invoke_without_command=True)
def app_callback(_ctx: typer.Context) -> None:
    # Skip banner if --quiet or -q flag is present
    if "--quiet" in sys.argv or "-q" in sys.argv:
        return

    console = get_console()
    package_version = get_package_version()
    console.print(
        f"""
[bold cyan]Pipelex Dev CLI[/bold cyan] [dim]v{package_version}[/dim]

[yellow]⚠️  Internal Development Tools Only[/yellow]
[dim]This CLI is for Pipelex development and is not distributed with the package.[/dim]
"""
    )


@app.command(name="check-config-sync", help="Verify that .pipelex and pipelex/kit/configs are in sync")
def check_config_sync_command(
    show_diff: Annotated[bool, typer.Option("--show-diff/--no-diff", help="Show differences if found")] = True,
    leading: Annotated[
        LeadingConfig,
        typer.Option(help="Which configuration is the leading (left) one: 'installed' (.pipelex) or 'kit' (pipelex/kit/configs)"),
    ] = LeadingConfig.KIT,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single validation line")] = False,
) -> None:
    """Verify that .pipelex and pipelex/kit/configs are in sync."""
    try:
        check_config_sync_cmd(show_diff=show_diff, leading=leading, quiet=quiet)
    except Exception:
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="check-rules", help="Verify that installed agent rules match kit templates")
def check_rules_command(
    show_diff: Annotated[bool, typer.Option("--show-diff/--no-diff", help="Show differences if found")] = True,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single validation line")] = False,
) -> None:
    """Verify that installed agent rules match kit templates."""
    try:
        check_rules_sync_cmd(show_diff=show_diff, quiet=quiet)
    except Exception:
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="check-urls", help="Check all URLs in pipelex/urls.py for broken links")
def check_urls_command(
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single validation line")] = False,
    timeout: Annotated[int, typer.Option("--timeout", "-t", help="Request timeout in seconds")] = DEFAULT_TIMEOUT,
) -> None:
    """Check all URLs in pipelex/urls.py for broken links."""
    try:
        check_urls_cmd(quiet=quiet, timeout=timeout)
    except Exception:
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="generate-mthds-schema", help="Generate JSON Schema for .mthds files (for Taplo validation)")
def generate_mthds_schema_command(
    output: Annotated[str | None, typer.Option("--output", "-o", help="Custom output path for the schema file")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single validation line")] = False,
) -> None:
    """Generate a Taplo-compatible JSON Schema from MTHDS blueprint classes."""
    try:
        output_path = Path(output) if output else None
        generate_mthds_schema_cmd(output=output_path, quiet=quiet)
    except Exception:
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="check-gateway-models", help="Verify that gateway models reference is up-to-date")
def check_gateway_models_command(
    show_diff: Annotated[bool, typer.Option("--show-diff/--no-diff", help="Show differences if found")] = True,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single validation line")] = False,
) -> None:
    """Verify that the Pipelex Gateway models reference file is up-to-date."""
    try:
        check_gateway_models_cmd(show_diff=show_diff, quiet=quiet)
    except Exception:
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="check-mthds-schema", help="Verify that MTHDS JSON Schema is up-to-date")
def check_mthds_schema_command(
    show_diff: Annotated[bool, typer.Option("--show-diff/--no-diff", help="Show differences if found")] = True,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single validation line")] = False,
) -> None:
    """Verify that the MTHDS JSON Schema file is up-to-date."""
    try:
        check_mthds_schema_cmd(show_diff=show_diff, quiet=quiet)
    except Exception:
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="sync-main-config", help="Sync main config values to kit and project configs")
def sync_main_config_command(
    target: Annotated[
        SyncTarget,
        typer.Option(help="Target to sync: 'kit', 'project', or 'all'"),
    ] = SyncTarget.ALL,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview changes without applying")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only minimal validation lines")] = False,
    show_diff: Annotated[bool, typer.Option("--show-diff/--no-diff", help="Show detailed changes")] = True,
) -> None:
    """Sync values from main config (pipelex/pipelex.toml) to kit and project configs."""
    try:
        sync_main_config_cmd(target=target, dry_run=dry_run, quiet=quiet, show_diff=show_diff)
    except Exception:
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="preprocess-test-models", help="Preprocess test models and generate fixture files")
def preprocess_test_models_command(
    profile: Annotated[str, typer.Option("--profile", "-p", help="Test profile to use (ci, dev, coverage, full)")] = "dev",
    generate_fixtures: Annotated[bool, typer.Option("--generate-fixtures", "-g", help="Generate Python fixtures file")] = False,
    output_json: Annotated[bool, typer.Option("--output-json", "-j", help="Output model availability JSON")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only minimal status lines")] = False,
) -> None:
    """Preprocess test models and generate fixture files for parametrized tests."""
    try:
        preprocess_test_models_cmd(profile=profile, generate_fixtures=generate_fixtures, output_json=output_json, quiet=quiet)
    except Exception:
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="update-gateway-models", help="Update the gateway models reference file")
def update_gateway_models_command(
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single validation line")] = False,
) -> None:
    """Update the Pipelex Gateway models reference file from remote config."""
    try:
        update_gateway_models_cmd(quiet=quiet)
    except Exception:
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)
