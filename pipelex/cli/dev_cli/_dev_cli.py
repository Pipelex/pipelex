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
from pipelex.cli.dev_cli.commands.check_hub_layering_cmd import check_hub_layering_cmd
from pipelex.cli.dev_cli.commands.check_keyword_only_cmd import check_keyword_only_cmd
from pipelex.cli.dev_cli.commands.check_ledger_cmd import check_ledger_cmd
from pipelex.cli.dev_cli.commands.check_migration_schemas_cmd import check_migration_schemas_cmd
from pipelex.cli.dev_cli.commands.check_mthds_schema_cmd import check_mthds_schema_cmd
from pipelex.cli.dev_cli.commands.check_rules_sync_cmd import check_rules_sync_cmd
from pipelex.cli.dev_cli.commands.check_urls_cmd import DEFAULT_TIMEOUT, check_urls_cmd
from pipelex.cli.dev_cli.commands.drift.drift_cmd import drift_app
from pipelex.cli.dev_cli.commands.generate_corpus_vocabulary_cmd import generate_corpus_vocabulary_cmd
from pipelex.cli.dev_cli.commands.generate_error_identity_cmd import generate_error_identity_cmd
from pipelex.cli.dev_cli.commands.generate_error_pages_cmd import generate_error_pages_cmd
from pipelex.cli.dev_cli.commands.generate_mthds_schema_cmd import generate_mthds_schema_cmd
from pipelex.cli.dev_cli.commands.generate_projection_corpus_cmd import generate_projection_corpus_cmd
from pipelex.cli.dev_cli.commands.kit_cmd import kit_app
from pipelex.cli.dev_cli.commands.preprocess_test_models_cmd import preprocess_test_models_cmd
from pipelex.cli.dev_cli.commands.refresh_graph_ui_sri_cmd import refresh_graph_ui_sri_cmd
from pipelex.cli.dev_cli.commands.store_test_durations_cmd import store_test_durations_cmd
from pipelex.cli.dev_cli.commands.subject_grant_cmd import subject_grant_cmd
from pipelex.cli.dev_cli.commands.sync_kit_configs_cmd import sync_kit_configs_cmd
from pipelex.cli.dev_cli.commands.sync_main_config_cmd import SyncTarget, sync_main_config_cmd
from pipelex.cli.dev_cli.commands.trace_input_semantics_cmd import trace_input_semantics_cmd
from pipelex.cli.dev_cli.commands.update_gateway_models_cmd import update_gateway_models_cmd
from pipelex.cli.dev_cli.commands.update_migration_schemas_cmd import update_migration_schemas_cmd
from pipelex.runtime_hub import get_console
from pipelex.tools.misc.package_utils import get_package_version


class PipelexDevCLI(TyperGroup):
    """Custom Typer group for pipelex-dev CLI."""

    @override
    def list_commands(self, ctx: Context) -> list[str]:
        """List commands in proper order."""
        return [
            "check-config-sync",
            "check-gateway-models",
            "check-hub-layering",
            "check-keyword-only",
            "check-ledger",
            "check-migration-schemas",
            "check-mthds-schema",
            "check-rules",
            "check-urls",
            "drift",
            "generate-corpus-vocabulary",
            "generate-error-identity",
            "generate-error-pages",
            "generate-mthds-schema",
            "kit",
            "preprocess-test-models",
            "refresh-graph-ui-sri",
            "store-test-durations",
            "subject-grant",
            "sync-kit-configs",
            "sync-main-config",
            "trace-input-semantics",
            "update-gateway-models",
            "update-migration-schemas",
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

app.add_typer(drift_app, name="drift", help="Drift contracts: deterministic review obligations between code, docs, and tests")
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
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
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
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
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
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="generate-corpus-vocabulary", help="Regenerate the MTHDS Test Corpus tag vocabulary from the runtime registries")
def generate_corpus_vocabulary_command(
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single status line")] = False,
) -> None:
    """Regenerate the committed corpus tag vocabulary."""
    try:
        generate_corpus_vocabulary_cmd(quiet=quiet)
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="generate-error-identity", help="Regenerate the committed (error_type, title, type_uri) snapshot of every PipelexError subclass")
def generate_error_identity_command(
    output: Annotated[str | None, typer.Option("--output", "-o", help="Custom output path for the snapshot file")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single status line")] = False,
) -> None:
    """Regenerate the PipelexError wire-identity snapshot."""
    try:
        output_path = Path(output) if output else None
        generate_error_identity_cmd(output=output_path, quiet=quiet)
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="generate-error-pages", help="Generate one docs page per PipelexError subclass under docs/errors/")
def generate_error_pages_command(
    output: Annotated[str | None, typer.Option("--output", "-o", help="Custom output directory for the error pages")] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single status line")] = False,
) -> None:
    """Generate per-class error documentation pages under ``docs/errors/``."""
    try:
        output_path = Path(output) if output else None
        generate_error_pages_cmd(output=output_path, quiet=quiet)
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
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
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
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
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
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
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="check-ledger", help="Verify that every migration ledger is legal and replays harmlessly over current documents")
def check_ledger_command(
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Light output on success (single line); the full issue list still prints on failure")
    ] = False,
) -> None:
    """Verify that every configuration surface's migration ledger is legal and converges."""
    try:
        check_ledger_cmd(quiet=quiet)
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="check-migration-schemas", help="Verify that every configuration surface has accounted for its schema changes")
def check_migration_schemas_command(
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Light output on success (single line); the full issue list still prints on failure")
    ] = False,
) -> None:
    """Verify that every configuration surface's schema changes are accounted for in its ledger."""
    try:
        check_migration_schemas_cmd(quiet=quiet)
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="update-migration-schemas", help="Regenerate the migration fingerprint and defaults goldens")
def update_migration_schemas_command(
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single status line")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite a head golden that records material the models lost")] = False,
) -> None:
    """Regenerate the migration golden chain for every configuration surface."""
    try:
        update_migration_schemas_cmd(quiet=quiet, force=force)
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="check-hub-layering", help="Enforce the runtime_hub / interpreter_hub layering boundary")
def check_hub_layering_command(
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Light output on success (single line); the full violation list still prints on failure")
    ] = False,
) -> None:
    """Enforce the runtime_hub / interpreter_hub layering boundary."""
    try:
        check_hub_layering_cmd(quiet=quiet)
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="check-keyword-only", help="Enforce the keyword-only-arguments convention across pipelex/ source")
def check_keyword_only_command(
    report: Annotated[bool, typer.Option("--report", help="Print the full violation inventory grouped by package")] = False,
    fix: Annotated[
        bool,
        typer.Option(
            "--fix",
            help=(
                "Auto-fix by inserting a bare `*` as far left as possible "
                "(every non-self/cls parameter becomes keyword-only); reports any that need a manual fix"
            ),
        ),
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Light output on success (single line); the full violation list still prints on failure")
    ] = False,
) -> None:
    """Enforce the keyword-only-arguments convention across pipelex/ source."""
    try:
        check_keyword_only_cmd(report=report, fix=fix, quiet=quiet)
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="subject-grant", help="Record a subject grant in subject_grants.toml (keyword-only convention)")
def subject_grant_command(
    func_key: Annotated[
        str | None,
        typer.Argument(help='The def to grant, keyed "<relative_path>::<qualified_name>" (e.g. "pipelex/graph/render.py::render_node")'),
    ] = None,
    rationale: Annotated[
        str | None,
        typer.Option("--rationale", help="The on-the-record review decision — an honest, def-specific sentence"),
    ] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single status line")] = False,
) -> None:
    """Record a subject grant — the explicit permission for a def's positional subject parameter."""
    try:
        subject_grant_cmd(func_key=func_key, rationale=rationale, quiet=quiet)
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
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
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="sync-kit-configs", help="Mirror .pipelex/ into pipelex/kit/configs/")
def sync_kit_configs_command(
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview changes without applying")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single status line")] = False,
) -> None:
    """Mirror the .pipelex/ directory into pipelex/kit/configs/."""
    try:
        sync_kit_configs_cmd(quiet=quiet, dry_run=dry_run)
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="generate-projection-corpus", help="Write the shared inputs-template projection fixture corpus")
def generate_projection_corpus_command(
    bundles: Annotated[list[Path], typer.Argument(help="MTHDS bundle file(s) to load as one batch — order fixes the emitted key order")],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o", help="Directory receiving the corpus")],
) -> None:
    """Write the descriptors, the expected inputs templates, and the divergence record."""
    generate_projection_corpus_cmd(bundle_paths=bundles, output_dir=output_dir)


@app.command(name="trace-input-semantics", help="Dump one artifact per hop of the input-schema emission chain for a bundle")
def trace_input_semantics_command(
    bundles: Annotated[list[Path], typer.Argument(help="MTHDS bundle file(s) to load as one batch")],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o", help="Directory receiving the per-hop artifacts")],
    allow_signatures: Annotated[bool, typer.Option("--allow-signatures", help="Tolerate unimplemented pipe signatures")] = False,
) -> None:
    """Trace what each hop of the emission chain does to every authored input fact."""
    trace_input_semantics_cmd(bundle_paths=bundles, output_dir=output_dir, allow_signatures=allow_signatures)


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
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(
    name="refresh-graph-ui-sri",
    help="Refetch the pinned graph viewer assets from jsDelivr and rewrite SRI hashes in standalone_assets.py",
)
def refresh_graph_ui_sri_command(
    mthds_ui_version: Annotated[
        str | None,
        typer.Option("--mthds-ui-version", help="Target @pipelex/mthds-ui version (default: currently pinned)"),
    ] = None,
    elkjs_version: Annotated[
        str | None,
        typer.Option("--elkjs-version", help="Target elkjs version (default: currently pinned)"),
    ] = None,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single status line")] = False,
) -> None:
    """Refetch the pinned graph viewer assets and rewrite `standalone_assets.py`."""
    try:
        refresh_graph_ui_sri_cmd(
            mthds_ui_version=mthds_ui_version,
            elkjs_version=elkjs_version,
            quiet=quiet,
        )
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
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
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)


@app.command(name="store-test-durations", help="Refresh the .test_durations map pytest-split uses to balance the CI shards")
def store_test_durations_command(
    markers: Annotated[
        str,
        typer.Option("--markers", "-m", help="The pytest marker expression the sharded CI job runs (threaded through from the Makefile)"),
    ],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Re-measure the whole suite instead of only the tests missing from the map"),
    ] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Output only a single status line on success")] = False,
) -> None:
    """Refresh the pytest-split duration map, measuring only what is missing unless --force is given."""
    try:
        store_test_durations_cmd(markers=markers, force=force, quiet=quiet)
    except (typer.Exit, typer.Abort):
        # Typer control-flow exits carry an intended exit code — not a failure. Let them through.
        raise
    except Exception:  # ruff: ignore[blind-except]
        # Dev CLI command root: print a traceback for any unexpected failure and exit non-zero.
        console = get_console()
        console.print()
        console.print("[bold red]Unexpected error occurred[/bold red]")
        console.print()
        console.print(Traceback())
        sys.exit(1)
