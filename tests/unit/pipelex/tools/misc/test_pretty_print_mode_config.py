"""The pretty-print mode is configuration: shipped as `rich`, applied at boot, and released at teardown."""

from __future__ import annotations

from pathlib import Path

import tomli

from pipelex.config import get_config
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.misc.pretty import PrettyPrinter, PrettyPrintMode

PIPELEX_REPO_ROOT = Path(__file__).resolve().parents[5]
PACKAGE_DEFAULT_TOML = PIPELEX_REPO_ROOT / "pipelex" / "pipelex.toml"


def _test_integration_mode() -> IntegrationMode:
    """The boot mode the session conftest uses, so a re-boot here matches the one it replaces."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestPrettyPrintModeConfig:
    def test_shipped_default_is_rich(self) -> None:
        """The packaged defaults carry the key, so an older user file inherits it without a migration."""
        with PACKAGE_DEFAULT_TOML.open("rb") as toml_file:
            shipped = tomli.load(toml_file)
        assert shipped["runtime"]["log"]["pretty_print_mode"] == PrettyPrintMode.RICH

    def test_boot_applies_the_configured_mode_and_teardown_releases_it(self) -> None:
        """Boot with a mode that is neither the class default nor the shipped one, so a boot that forgot to
        apply `[runtime.log]` fails here; then tear down, which must hand the process back the mode it held
        before that boot.

        Re-boots the process singleton, so it restores the module fixture's boot on the way out.
        """
        Pipelex.teardown_if_needed()
        try:
            Pipelex.make(
                integration_mode=_test_integration_mode(),
                needs_inference=False,
                config_overrides={"runtime": {"log": {"pretty_print_mode": PrettyPrintMode.SILENT}}},
            )
            assert get_config().runtime.log.pretty_print_mode is PrettyPrintMode.SILENT
            assert PrettyPrinter.mode is PrettyPrintMode.SILENT

            Pipelex.teardown_if_needed()
            assert PrettyPrinter.mode is PrettyPrintMode.RICH
        finally:
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())

    def test_teardown_restores_the_mode_held_before_boot_not_the_default(self) -> None:
        """A process that set a mode itself before booting gets that mode back at teardown, not `rich`.

        The pre-boot mode differs from the class default here, which the test above cannot tell apart from a
        hardcoded reset. Re-boots the process singleton, so it restores the module fixture's boot on the way out.
        """
        Pipelex.teardown_if_needed()
        try:
            PrettyPrinter.mode = PrettyPrintMode.POOR
            Pipelex.make(
                integration_mode=_test_integration_mode(),
                needs_inference=False,
                config_overrides={"runtime": {"log": {"pretty_print_mode": PrettyPrintMode.SILENT}}},
            )
            assert PrettyPrinter.mode is PrettyPrintMode.SILENT

            Pipelex.teardown_if_needed()
            assert PrettyPrinter.mode is PrettyPrintMode.POOR
        finally:
            Pipelex.teardown_if_needed()
            PrettyPrinter.mode = PrettyPrintMode.RICH
            Pipelex.make(integration_mode=_test_integration_mode())
