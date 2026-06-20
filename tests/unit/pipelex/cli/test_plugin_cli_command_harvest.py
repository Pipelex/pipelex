"""The CLI harvests plugin-contributed commands at CLI-build (D3).

The Temporal plugin contributes ``worker`` and ``setup-temporal-namespace`` by declaring an
``import_path`` (not by importing the callable), so they appear in the CLI without core naming any
integration — and without constructing a Temporal impl (D5 thunks keep the harvest temporalio-free,
proven separately by the import-light guard).
"""

from pytest_mock import MockerFixture

from pipelex.cli._cli import _config_for_cli_harvest, app  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.tools.misc.exceptions import TomlError


class TestPluginCliCommandHarvest:
    def test_temporal_commands_are_registered_on_the_app(self) -> None:
        """The Temporal plugin's commands are registered on the Typer app, in discovery order."""
        names = [command.name for command in app.registered_commands]
        assert "worker" in names, "Temporal plugin did not contribute the 'worker' command"
        assert "setup-temporal-namespace" in names, "Temporal plugin did not contribute 'setup-temporal-namespace'"
        # Discovery order: worker is registered before setup-temporal-namespace.
        assert names.index("worker") < names.index("setup-temporal-namespace")

    def test_plugin_commands_registered_after_core_commands(self) -> None:
        """Harvested plugin commands are appended after the statically-registered core commands.

        Anchored on the harvest running last (the plugin commands are the final registrations),
        so it survives any reordering of the core command block.
        """
        names = [command.name for command in app.registered_commands]
        assert names[-2:] == ["worker", "setup-temporal-namespace"]

    def test_harvest_config_falls_back_to_base_on_broken_user_config(self, mocker: MockerFixture) -> None:
        """A broken user config must not brick the CLI: the harvest falls back to package defaults.

        ``_config_for_cli_harvest`` runs at CLI-build on every ``pipelex`` invocation (including
        ``--help`` / ``init``), so a malformed override TOML must degrade to the shipped defaults
        rather than raising — otherwise the very commands that fix config become unreachable.
        """
        mocker.patch(
            "pipelex.system.configuration.config_loader.ConfigLoader.load_config",
            side_effect=TomlError(message="boom", doc="", pos=0, lineno=1, colno=1),
        )

        config = _config_for_cli_harvest()

        assert isinstance(config, PipelexConfig)
        # Package defaults loaded (no user overrides applied).
        assert config.plugins.disabled == []
