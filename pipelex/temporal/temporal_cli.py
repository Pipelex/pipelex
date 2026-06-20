"""The ``pipelex-temporal`` console script — operational commands for the Temporal runtime.

Exposed via ``[project.scripts]`` as ``pipelex-temporal = "pipelex.temporal.temporal_cli:app"``,
materialized by pip into its own executable. Temporal's operational commands live here rather than
on the host ``pipelex`` CLI: ``worker`` and ``setup-namespace`` are how an operator runs a worker
daemon and bootstraps a namespace, not how a pipeline *runs* on Temporal (distributed execution goes
through the orchestrator registry by ``execution_mode``, untouched by this module).

Import-light at module top: ``worker_cmd`` / ``setup_namespace_cmd`` pull ``temporalio`` lazily inside
their bodies, so importing this module to build the CLI imports no ``temporalio``. When Temporal
externalizes to ``pipelex-temporal`` (Phase 5), that dist owns this console script natively.
"""

import typer

from pipelex.temporal.setup_namespace_cmd import setup_namespace_cmd
from pipelex.temporal.worker_cmd import worker_cmd

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    help="Operational commands for the Pipelex Temporal runtime (worker daemon, namespace bootstrap).",
)

app.command(name="worker", help="Start a Temporal worker for distributed workflow execution")(worker_cmd)
app.command(
    name="setup-namespace",
    help="Register Pipelex's custom search attributes on the configured Temporal namespace",
)(setup_namespace_cmd)
