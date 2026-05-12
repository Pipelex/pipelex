"""pipelex setup-temporal-namespace — Register Pipelex's custom search
attributes on the configured Temporal namespace.

Wraps the same ``ensure_required_search_attributes_registered`` helper used by
the test infrastructure so operators get a one-shot CLI fix for the otherwise
opaque ``Namespace ... has no mapping defined for search attribute ...`` error
the cluster raises when a workflow start references an unregistered attribute.

Reads the same ``[temporal.search_attributes].attributes`` block the worker
populates, so the names registered here can never drift from the names the
worker will dispatch with. ``--dry-run`` prints the equivalent raw ``temporal``
CLI invocation without touching the cluster — useful when a namespace admin
needs to register on the operator's behalf.

Optional-dependency contract: this module must not import ``pipelex.temporal``
at module level so ``pipelex --help`` works without the ``temporal`` extra
installed. Deferred imports inside the function body carry the ``PLC0415``
ruff-ignore, matching the ``worker_cmd`` precedent. We deliberately do NOT
wrap the deferred imports in ``try/except ImportError`` — that would silently
relabel real bugs in the imported chain as "install the temporal extra";
``ModuleNotFoundError: No module named 'temporalio'`` from the raw chain is
already actionable.
"""

import asyncio
from typing import Annotated

import typer

from pipelex import log
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.config import get_config
from pipelex.pipelex import Pipelex


def setup_temporal_namespace_cmd(
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Print the equivalent `temporal operator search-attribute create` command without executing.",
        ),
    ] = False,
    server: Annotated[
        str | None,
        typer.Option(
            "--server",
            help="Target a non-default server profile from [temporal.temporal_config.temporal_server_configs] (defaults to selected_server).",
        ),
    ] = None,
) -> None:
    """Register Pipelex's custom search attributes on the Temporal namespace.

    Examples:
        pipelex setup-temporal-namespace
        pipelex setup-temporal-namespace --dry-run
        pipelex setup-temporal-namespace --server testing
    """
    make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_PIPE_RUN, temporal_enabled=True)

    try:
        from temporalio.service import RPCError  # noqa: PLC0415

        from pipelex.temporal.temporal_connect import connect_to_temporal_selected_server  # noqa: PLC0415
        from pipelex.temporal.tprl.namespace_check import (  # noqa: PLC0415
            RegistrationFailure,
            ensure_required_search_attributes_registered,
            format_tcld_cli_command,
            format_temporal_cli_command,
        )

        search_attributes_config = get_config().temporal.search_attributes
        if not search_attributes_config.enabled:
            typer.secho(
                "[temporal.search_attributes].enabled = false — nothing to register. "
                "Set enabled = true in your pipelex.toml to opt in to custom search attributes.",
                fg=typer.colors.YELLOW,
                err=True,
            )
            return

        configured = list(search_attributes_config.attributes)
        if not configured:
            typer.secho(
                "[temporal.search_attributes].attributes is empty — nothing to register.",
                fg=typer.colors.YELLOW,
                err=True,
            )
            return

        temporal_config = get_config().temporal.temporal_config
        selected_profile = server or temporal_config.selected_server
        server_config = temporal_config.temporal_server_configs.get(selected_profile)
        if server_config is None:
            typer.secho(
                f"Unknown server profile '{selected_profile}'. Known: {sorted(temporal_config.temporal_server_configs.keys())}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        namespace = server_config.namespace

        if dry_run:
            typer.echo(f"# Equivalent Temporal CLI invocation for namespace '{namespace}' (server profile '{selected_profile}'):")
            typer.echo(format_temporal_cli_command(configured, namespace=namespace))
            typer.echo(
                "\n# For Temporal Cloud, the namespace admin can also use:\n"
                f"#   {format_tcld_cli_command(configured, namespace=namespace)}\n"
                "# or the Cloud UI: Namespace → Custom Search Attributes."
            )
            return

        async def _connect_and_register() -> RegistrationFailure | None:
            # Single event loop for both awaits: the Temporal SDK binds the
            # Client to the loop it was created on, so the registration call
            # must run on the same loop as the connect.
            temporal_client = await connect_to_temporal_selected_server(selected_server_config=selected_profile)
            return await ensure_required_search_attributes_registered(
                temporal_client=temporal_client,
                namespace=namespace,
                configured_attributes=configured,
            )

        log.info(f"Connecting to Temporal server profile '{selected_profile}' (namespace='{namespace}')...")
        try:
            outcome = asyncio.run(_connect_and_register())
        except RPCError as exc:
            # The helper propagates non-PERMISSION_DENIED RPC errors (e.g.
            # NOT_FOUND when the namespace doesn't exist, UNAVAILABLE when the
            # control plane is down). Frame these for the operator instead of
            # leaking a raw traceback.
            typer.secho(
                f"Could not reach Temporal namespace '{namespace}' on profile '{selected_profile}': {exc}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1) from exc

        if isinstance(outcome, RegistrationFailure):
            typer.secho(
                "Permission denied: this Temporal API key cannot call "
                "OperatorService.AddSearchAttributes. Ask a namespace admin to register "
                "the missing attributes manually:\n",
                fg=typer.colors.RED,
                err=True,
            )
            typer.echo(format_temporal_cli_command(outcome.missing, namespace=namespace), err=True)
            typer.echo(
                "\nFor Temporal Cloud:\n"
                f"  {format_tcld_cli_command(outcome.missing, namespace=namespace)}\n"
                "  or the Cloud UI: Namespace → Custom Search Attributes.\n"
                f"\n(Underlying RPC error: {outcome.rpc_error_message})",
                err=True,
            )
            raise typer.Exit(1)

        typer.secho(
            f"Registered {len(configured)} custom search attribute(s) on namespace '{namespace}'.",
            fg=typer.colors.GREEN,
        )
    finally:
        Pipelex.teardown_if_needed()
