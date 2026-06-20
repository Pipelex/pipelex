"""Smoke test for the ``pipelex-temporal`` console-script Typer app.

The two operational Temporal commands ship as the standalone ``pipelex-temporal`` console
script (``pipelex.temporal.temporal_cli:app``) rather than being harvested onto the host
``pipelex`` CLI, so this pins that the app exposes both subcommands by name. Importing the
app stays import-light (no ``temporalio`` at module top); the boot import-light guard proves
that invariant separately.
"""

from pipelex.temporal.temporal_cli import app


class TestTemporalCli:
    def test_app_exposes_worker_and_setup_namespace(self) -> None:
        names = [command.name for command in app.registered_commands]
        assert "worker" in names, "pipelex-temporal must expose the 'worker' command"
        assert "setup-namespace" in names, "pipelex-temporal must expose the 'setup-namespace' command"
